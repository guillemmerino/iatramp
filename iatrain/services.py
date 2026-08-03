from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import CoachAthleteRelation, Person
from core.services import has_athlete_access

from .models import AthleteObservation, KnowledgeConcept, KnowledgeRelation


def person_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.person if user.person.is_active else None
    except Person.DoesNotExist:
        return None


def accessible_athletes(user, *, permission="can_view_training", organization=None):
    allowed_permissions = {"can_view_training", "can_edit_training"}
    if permission not in allowed_permissions:
        raise ValueError(f"Permís d'entrenament desconegut: {permission}")
    if not getattr(user, "is_authenticated", False):
        return Person.objects.none()
    if user.is_superuser:
        return Person.objects.filter(is_active=True)
    coach = person_for_user(user)
    if coach is None:
        return Person.objects.none()

    today = timezone.localdate()
    relations = CoachAthleteRelation.objects.filter(
        coach=coach,
        athlete__is_active=True,
        is_active=True,
        start_date__lte=today,
        **{permission: True},
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    if organization is not None:
        relations = relations.filter(organization=organization)
    return Person.objects.filter(coach_relations__in=relations).distinct()


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
