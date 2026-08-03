from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CoachAthleteRelation, Membership, Person


@transaction.atomic
def link_person_to_user(*, person, user):
    """Link an existing person to an auth user without replacing another link."""
    locked_person = Person.objects.select_for_update().get(pk=person.pk)
    if locked_person.user_id and locked_person.user_id != user.pk:
        raise ValidationError("La persona ja està vinculada a un altre compte.")
    if Person.objects.filter(user=user).exclude(pk=locked_person.pk).exists():
        raise ValidationError("El compte ja està vinculat a una altra persona.")
    locked_person.user = user
    locked_person.full_clean()
    locked_person.save(update_fields=("user", "updated_at"))
    return locked_person


@transaction.atomic
def grant_membership(
    *, person, organization, role, title="", start_date=None, end_date=None, is_active=True
):
    membership = Membership.objects.select_for_update().filter(
        person=person,
        organization=organization,
        role=role,
    ).first()
    if membership is None:
        membership = Membership(person=person, organization=organization, role=role)
    membership.title = title
    membership.start_date = start_date or timezone.localdate()
    membership.end_date = end_date
    membership.is_active = is_active
    membership.full_clean()
    membership.save()
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
    relation = CoachAthleteRelation.objects.select_for_update().filter(
        coach=coach,
        athlete=athlete,
        organization=organization,
        function=function,
    ).first()
    if relation is None:
        relation = CoachAthleteRelation(
            coach=coach,
            athlete=athlete,
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


def can_manage_organization(user, organization):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    person = getattr(user, "person", None)
    if person is None:
        return False
    today = timezone.localdate()
    return Membership.objects.filter(
        person=person,
        organization=organization,
        role__in=(Membership.Role.OWNER, Membership.Role.ADMIN),
        is_active=True,
        start_date__lte=today,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).exists()


def has_athlete_access(user, athlete, permission="can_view_profile", organization=None):
    """Return access granted by self-access or a current explicit coach relation."""
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
    person = getattr(user, "person", None)
    if person is None:
        return False
    if person.pk == athlete.pk:
        return True

    today = timezone.localdate()
    relations = CoachAthleteRelation.objects.filter(
        coach=person,
        athlete=athlete,
        is_active=True,
        start_date__lte=today,
        **{permission: True},
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    if organization is not None:
        relations = relations.filter(organization=organization)
    return relations.exists()
