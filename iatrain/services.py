from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import Person
from organizations.models import Membership, MembershipRole, Organization
from organizations.selectors import current_membership_filter

from .models import (
    AthleteObservation,
    AthleteProfile,
    CoachAthleteRelation,
    CoachProfile,
    Gym,
    GymEquipment,
    GymOrganization,
    KnowledgeConcept,
    KnowledgeRelation,
    TrainingGroup,
    TrainingGroupMembership,
)


def person_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.person if user.person.is_active else None
    except Person.DoesNotExist:
        return None


def accessible_athletes(user, *, permission="can_view_training", organization=None):
    allowed_permissions = {
        "can_view_profile",
        "can_view_training",
        "can_edit_training",
        "can_view_health_data",
    }
    if permission not in allowed_permissions:
        raise ValueError(f"Permís d'entrenament desconegut: {permission}")
    if not getattr(user, "is_authenticated", False):
        return Person.objects.none()
    coach = person_for_user(user)
    if coach is None:
        return Person.objects.none()

    today = timezone.localdate()
    relations = CoachAthleteRelation.objects.filter(
        coach_profile__person=coach,
        coach_profile__is_active=True,
        athlete_profile__person__is_active=True,
        athlete_profile__is_active=True,
        is_active=True,
        start_date__lte=today,
        **{permission: True},
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    if organization is not None:
        relations = relations.filter(organization=organization)
    return Person.objects.filter(athlete_profile__coach_relations__in=relations).distinct()


def activate_athlete_profile(*, person, settings=None):
    profile, _ = AthleteProfile.objects.get_or_create(person=person)
    if settings is not None:
        profile.settings = settings
    profile.is_active = True
    profile.full_clean()
    profile.save()
    return profile


def activate_coach_profile(*, person, settings=None):
    profile, _ = CoachProfile.objects.get_or_create(person=person)
    if settings is not None:
        profile.settings = settings
    profile.is_active = True
    profile.full_clean()
    profile.save()
    return profile


def set_sport_profile_active(*, person, profile_type, is_active):
    """Activate or suspend one of the person's IA Train profiles without deleting it."""
    activators = {
        "athlete": activate_athlete_profile,
        "coach": activate_coach_profile,
    }
    if profile_type not in activators:
        raise ValidationError("Tipus de perfil esportiu desconegut.")
    profile = activators[profile_type](person=person)
    if not is_active:
        profile.is_active = False
        profile.save(update_fields=("is_active", "updated_at"))
    return profile


def organizations_available_to_coach(user):
    """Organizations where a coach has an explicit sporting foothold.

    Administrative memberships never qualify. An active scoped athlete relation or an
    active organization membership carrying the explicit coach role does.
    """
    person = person_for_user(user)
    if person is None or not getattr(user, "is_authenticated", False):
        return Organization.objects.none()
    if user.is_superuser:
        return Organization.objects.filter(is_active=True)
    today = timezone.localdate()
    relation_orgs = CoachAthleteRelation.objects.filter(
        coach_profile__person=person,
        coach_profile__is_active=True,
        athlete_profile__is_active=True,
        is_active=True,
        organization__isnull=False,
        start_date__lte=today,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).values("organization_id")
    coach_memberships = Membership.objects.filter(person=person).filter(
        current_membership_filter()
    ).filter(
        roles__role=MembershipRole.Role.COACH,
        roles__is_active=True,
    ).values("organization_id")
    return Organization.objects.filter(
        is_active=True,
    ).filter(Q(pk__in=relation_orgs) | Q(pk__in=coach_memberships)).distinct()


def managed_groups(user):
    if not getattr(user, "is_authenticated", False):
        return TrainingGroup.objects.none()
    if user.is_superuser:
        return TrainingGroup.objects.all()
    person = person_for_user(user)
    if person is None:
        return TrainingGroup.objects.none()
    return TrainingGroup.objects.filter(
        managing_coaches__person=person,
        managing_coaches__is_active=True,
    ).distinct()


def accessible_gyms(user):
    """Gyms connected to an organization where the user coaches."""
    if not getattr(user, "is_authenticated", False):
        return Gym.objects.none()
    if user.is_superuser:
        return Gym.objects.filter(is_active=True)
    return Gym.objects.filter(
        is_active=True,
        organization_links__is_active=True,
        organization_links__organization__in=organizations_available_to_coach(user),
    ).distinct()


def can_manage_gym(user, gym):
    return accessible_gyms(user).filter(pk=gym.pk).exists()


@transaction.atomic
def create_gym(*, user, name, organizations, location="", notes=""):
    allowed = organizations_available_to_coach(user)
    organization_ids = {organization.pk for organization in organizations}
    if not organization_ids or allowed.filter(pk__in=organization_ids).count() != len(organization_ids):
        raise PermissionDenied("Només pots vincular el gimnàs a organitzacions on entrenes.")
    person = person_for_user(user)
    try:
        coach_profile = person.coach_profile
    except (AttributeError, CoachProfile.DoesNotExist):
        raise PermissionDenied("Cal un perfil d’entrenador actiu.")
    if not coach_profile.is_active:
        raise PermissionDenied("Cal un perfil d’entrenador actiu.")
    gym = Gym(name=name, location=location, notes=notes, created_by=coach_profile)
    gym.full_clean()
    gym.save()
    GymOrganization.objects.bulk_create(
        [GymOrganization(gym=gym, organization_id=organization_id) for organization_id in organization_ids]
    )
    return gym


@transaction.atomic
def update_gym(*, user, gym, name, organizations, location="", notes=""):
    if not can_manage_gym(user, gym):
        raise PermissionDenied("No pots gestionar aquest gimnàs.")
    allowed = organizations_available_to_coach(user)
    organization_ids = {organization.pk for organization in organizations}
    if not organization_ids or allowed.filter(pk__in=organization_ids).count() != len(organization_ids):
        raise PermissionDenied("Només pots vincular el gimnàs a organitzacions on entrenes.")
    gym.name = name
    gym.location = location
    gym.notes = notes
    gym.full_clean()
    gym.save(update_fields=("name", "location", "notes", "updated_at"))
    GymOrganization.objects.filter(gym=gym).exclude(organization_id__in=organization_ids).update(
        is_active=False
    )
    for organization_id in organization_ids:
        GymOrganization.objects.update_or_create(
            gym=gym,
            organization_id=organization_id,
            defaults={"is_active": True},
        )
    return gym


@transaction.atomic
def save_gym_equipment(*, user, gym, equipment=None, **values):
    if not can_manage_gym(user, gym):
        raise PermissionDenied("No pots gestionar el material d’aquest gimnàs.")
    if equipment is None:
        equipment = GymEquipment(gym=gym)
    elif equipment.gym_id != gym.pk:
        raise PermissionDenied("Aquest material no pertany al gimnàs seleccionat.")
    for field in ("name", "equipment_type", "quantity", "availability", "notes"):
        setattr(equipment, field, values[field])
    equipment.full_clean()
    equipment.save()
    return equipment


def can_manage_group(user, training_group):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    person = person_for_user(user)
    return bool(
        person
        and training_group.managing_coaches.filter(person=person, is_active=True).exists()
    )


@transaction.atomic
def create_training_group(*, user, organization, name, description=""):
    person = person_for_user(user)
    if person is None or not organizations_available_to_coach(user).filter(pk=organization.pk).exists():
        raise PermissionDenied("No pots crear grups en aquesta organització.")
    try:
        coach_profile = person.coach_profile
    except CoachProfile.DoesNotExist:
        raise PermissionDenied("Cal un perfil d’entrenador actiu per crear grups.")
    if not coach_profile.is_active:
        raise PermissionDenied("Cal un perfil d’entrenador actiu per crear grups.")
    group = TrainingGroup(organization=organization, name=name, description=description)
    group.full_clean()
    group.save()
    group.managing_coaches.add(coach_profile)
    return group


@transaction.atomic
def add_group_member(*, user, training_group, athlete_profile):
    if not can_manage_group(user, training_group):
        raise PermissionDenied("No gestiones aquest grup.")
    if not has_athlete_access(
        user, athlete_profile, permission="can_view_profile", organization=training_group.organization
    ):
        raise PermissionDenied("No tens una relació esportiva vàlida amb aquest gimnasta en l’organització.")
    membership = TrainingGroupMembership.objects.select_for_update().filter(
        training_group=training_group,
        athlete_profile=athlete_profile,
        is_active=True,
    ).first()
    if membership:
        return membership
    membership = TrainingGroupMembership(
        training_group=training_group,
        athlete_profile=athlete_profile,
    )
    membership.full_clean()
    membership.save()
    return membership


@transaction.atomic
def remove_group_member(*, user, membership):
    if not can_manage_group(user, membership.training_group):
        raise PermissionDenied("No gestiones aquest grup.")
    if membership.is_active:
        membership.is_active = False
        membership.end_date = timezone.localdate()
        membership.full_clean()
        membership.save(update_fields=("is_active", "end_date", "updated_at"))
    return membership


@transaction.atomic
def set_coach_athlete_relation(
    *,
    coach,
    athlete,
    function=CoachAthleteRelation.Function.PRIMARY_COACH,
    organization=None,
    start_date=None,
    end_date=None,
    is_active=True,
    can_view_profile=True,
    can_view_training=True,
    can_edit_training=False,
    can_view_health_data=False,
    notes="",
):
    coach_profile = (
        coach if isinstance(coach, CoachProfile) else activate_coach_profile(person=coach)
    )
    athlete_profile = (
        athlete
        if isinstance(athlete, AthleteProfile)
        else activate_athlete_profile(person=athlete)
    )
    relation = CoachAthleteRelation.objects.select_for_update().filter(
        coach_profile=coach_profile,
        athlete_profile=athlete_profile,
        organization=organization,
        function=function,
    ).first()
    if relation is None:
        relation = CoachAthleteRelation(
            coach_profile=coach_profile,
            athlete_profile=athlete_profile,
            organization=organization,
            function=function,
        )
    relation.start_date = start_date or timezone.localdate()
    relation.end_date = end_date
    relation.is_active = is_active
    relation.can_view_profile = can_view_profile
    relation.can_view_training = can_view_training
    relation.can_edit_training = can_edit_training
    relation.can_view_health_data = can_view_health_data
    relation.notes = notes
    relation.full_clean()
    relation.save()
    return relation


@transaction.atomic
def create_unclaimed_athlete(
    *,
    coach,
    first_name,
    last_name,
    preferred_name="",
    email="",
    organization=None,
    function=CoachAthleteRelation.Function.PRIMARY_COACH,
    invitation_expires_at=None,
):
    from core.services import create_person_claim_invitation

    coach_profile = (
        coach if isinstance(coach, CoachProfile) else activate_coach_profile(person=coach)
    )
    athlete = Person(
        first_name=str(first_name or "").strip(),
        last_name=str(last_name or "").strip(),
        preferred_name=str(preferred_name or "").strip(),
        email=str(email or "").strip().lower(),
    )
    athlete.full_clean()
    athlete.save()
    athlete_profile = activate_athlete_profile(person=athlete)
    relation = set_coach_athlete_relation(
        coach=coach_profile,
        athlete=athlete_profile,
        organization=organization,
        function=function,
    )
    invitation = None
    raw_token = None
    if athlete.email:
        invitation, raw_token = create_person_claim_invitation(
            person=athlete,
            email=athlete.email,
            created_by=coach_profile.person,
            expires_at=invitation_expires_at,
        )
    return athlete_profile, relation, invitation, raw_token


def has_athlete_access(user, athlete, permission="can_view_profile", organization=None):
    allowed_permissions = {
        "can_view_profile",
        "can_view_training",
        "can_edit_training",
        "can_view_health_data",
    }
    if permission not in allowed_permissions:
        raise ValueError(f"Permís desconegut: {permission}")
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    person = person_for_user(user)
    if person is None:
        return False
    athlete_person = athlete.person if isinstance(athlete, AthleteProfile) else athlete
    if person.pk == athlete_person.pk:
        return True

    today = timezone.localdate()
    relations = CoachAthleteRelation.objects.filter(
        coach_profile__person=person,
        coach_profile__is_active=True,
        athlete_profile__person=athlete_person,
        athlete_profile__is_active=True,
        is_active=True,
        start_date__lte=today,
        **{permission: True},
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    if organization is not None:
        relations = relations.filter(organization=organization)
    return relations.exists()


def can_consult_observations(user, athlete, *, organization=None):
    return has_athlete_access(
        user,
        athlete,
        permission="can_view_training",
        organization=organization,
    )


def can_record_observations(user, athlete, *, organization=None):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    author = person_for_user(user)
    if author is None or author.pk == athlete.pk:
        return False
    return has_athlete_access(
        user,
        athlete,
        permission="can_edit_training",
        organization=organization,
    )


def _observation_author(user):
    author = person_for_user(user)
    if author is None:
        raise ValidationError("El compte ha d'estar vinculat a una Person activa per crear observacions.")
    return author


@transaction.atomic
def record_athlete_observation(
    *,
    user,
    athlete,
    narrative,
    category=AthleteObservation.Category.NOTE,
    status=AthleteObservation.Status.OBSERVED,
    training_context=None,
    concept=None,
    evidence="",
    confidence=None,
    intensity=None,
    observed_at=None,
    supersedes=None,
):
    organization = training_context.organization if training_context else None
    if not can_record_observations(user, athlete, organization=organization):
        raise PermissionDenied("No tens una relació activa amb permís d'edició per a aquest gimnasta.")

    observation = AthleteObservation(
        athlete=athlete,
        training_context=training_context,
        concept=concept,
        category=category,
        narrative=narrative,
        evidence=evidence,
        status=status,
        confidence=confidence,
        intensity=intensity,
        observed_at=observed_at or timezone.now(),
        authored_by=_observation_author(user),
        supersedes=supersedes,
    )
    observation.full_clean()
    observation.save()
    return observation


@transaction.atomic
def revise_athlete_observation(*, user, observation, **changes):
    if "athlete" in changes and changes["athlete"].pk != observation.athlete_id:
        raise ValidationError("Una revisió no pot canviar de gimnasta.")
    values = {
        "athlete": observation.athlete,
        "training_context": observation.training_context,
        "concept": observation.concept,
        "category": observation.category,
        "narrative": observation.narrative,
        "evidence": observation.evidence,
        "status": observation.status,
        "confidence": observation.confidence,
        "intensity": observation.intensity,
        "supersedes": observation,
    }
    values.update(changes)
    values.pop("athlete", None)
    values["supersedes"] = observation
    return record_athlete_observation(user=user, athlete=observation.athlete, **values)


@transaction.atomic
def create_knowledge_concept(
    *,
    author,
    name,
    kind,
    description="",
    discipline="trampoline",
    editorial_status=KnowledgeConcept.EditorialStatus.DRAFT,
    attributes=None,
):
    concept = KnowledgeConcept(
        name=name,
        description=description,
        kind=kind,
        discipline=discipline,
        editorial_status=editorial_status,
        authored_by=author,
        attributes={} if attributes is None else attributes,
    )
    concept.full_clean()
    concept.save()
    return concept


@transaction.atomic
def create_knowledge_relation(
    *,
    author,
    source,
    target,
    relation_type,
    rationale="",
    editorial_status=KnowledgeRelation.EditorialStatus.DRAFT,
):
    relation = KnowledgeRelation(
        source=source,
        target=target,
        relation_type=relation_type,
        rationale=rationale,
        editorial_status=editorial_status,
        authored_by=author,
    )
    relation.full_clean()
    relation.save()
    return relation
