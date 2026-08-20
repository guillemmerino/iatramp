from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from iatrain.models import AthleteProfile
from iatrain.services import can_record_observations, has_athlete_access, person_for_user

from .models import (
    AthleteCondition,
    AthleteInsight,
    AthleteInsightEvidence,
    AthleteMeasurement,
    AthleteSportProfile,
)


SENSITIVE_MEASUREMENT_DOMAINS = {
    AthleteMeasurement.Domain.ANTHROPOMETRY,
    AthleteMeasurement.Domain.RECOVERY,
}


def _profile(value):
    if isinstance(value, AthleteProfile):
        return value
    try:
        return value.athlete_profile
    except (AttributeError, AthleteProfile.DoesNotExist):
        raise ValidationError("La persona necessita un perfil de gimnasta actiu.")


def _actor(user):
    person = person_for_user(user)
    if person is None:
        raise PermissionDenied("El compte ha d'estar vinculat a una persona activa.")
    return person


def _assert_can_edit(user, athlete_profile, organization=None, *, health=False):
    if not can_record_observations(
        user, athlete_profile.person, organization=organization
    ):
        raise PermissionDenied("No pots modificar el perfil d'aquest gimnasta.")
    if health and not has_athlete_access(
        user,
        athlete_profile,
        permission="can_view_health_data",
        organization=organization,
    ):
        raise PermissionDenied("Aquesta informació requereix accés explícit a dades de salut.")
    return _actor(user)


@transaction.atomic
def set_athlete_sport_profile(
    *,
    user,
    athlete,
    discipline,
    organization=None,
    level_code="",
    training_started_on=None,
    preferred_laterality=AthleteSportProfile.Laterality.UNKNOWN,
    notes="",
    is_active=True,
):
    athlete_profile = _profile(athlete)
    actor = _assert_can_edit(user, athlete_profile, organization)
    profile, _ = AthleteSportProfile.objects.select_for_update().get_or_create(
        athlete_profile=athlete_profile,
        discipline=discipline,
        defaults={"updated_by": actor},
    )
    profile.level_code = level_code
    profile.training_started_on = training_started_on
    profile.preferred_laterality = preferred_laterality
    profile.notes = notes
    profile.is_active = is_active
    profile.updated_by = actor
    profile.save()
    return profile


@transaction.atomic
def record_athlete_measurement(
    *,
    user,
    athlete,
    domain,
    metric_code,
    metric_label,
    value,
    unit,
    source,
    organization=None,
    side=AthleteMeasurement.Side.NOT_APPLICABLE,
    protocol="",
    uncertainty=None,
    measured_at=None,
    valid_until=None,
    notes="",
    supersedes=None,
):
    athlete_profile = _profile(athlete)
    actor = _assert_can_edit(
        user,
        athlete_profile,
        organization,
        health=domain in SENSITIVE_MEASUREMENT_DOMAINS,
    )
    measurement = AthleteMeasurement(
        athlete_profile=athlete_profile,
        organization=organization,
        domain=domain,
        metric_code=metric_code,
        metric_label=metric_label,
        value=value,
        unit=unit,
        side=side,
        protocol=protocol,
        source=source,
        uncertainty=uncertainty,
        measured_at=measured_at or timezone.now(),
        valid_until=valid_until,
        notes=notes,
        recorded_by=actor,
        supersedes=supersedes,
    )
    measurement.save()
    return measurement


@transaction.atomic
def invalidate_athlete_measurement(*, user, measurement):
    _assert_can_edit(
        user,
        measurement.athlete_profile,
        measurement.organization,
        health=measurement.domain in SENSITIVE_MEASUREMENT_DOMAINS,
    )
    measurement = AthleteMeasurement.objects.select_for_update().get(pk=measurement.pk)
    if measurement.status == measurement.Status.INVALIDATED:
        return measurement
    measurement.status = measurement.Status.INVALIDATED
    measurement.save(update_fields=("status", "updated_at"))
    return measurement


@transaction.atomic
def propose_athlete_condition(
    *,
    user,
    athlete,
    category,
    title,
    narrative,
    source,
    organization=None,
    evidence="",
    body_region=None,
    laterality=AthleteCondition.Laterality.NOT_APPLICABLE,
    severity=None,
    training_impact=AthleteCondition.TrainingImpact.MONITOR,
    started_at=None,
    valid_until=None,
    supersedes=None,
):
    athlete_profile = _profile(athlete)
    actor = _assert_can_edit(user, athlete_profile, organization, health=True)
    condition = AthleteCondition(
        athlete_profile=athlete_profile,
        organization=organization,
        category=category,
        title=title,
        narrative=narrative,
        evidence=evidence,
        body_region=body_region,
        laterality=laterality,
        severity=severity,
        training_impact=training_impact,
        source=source,
        started_at=started_at or timezone.now(),
        valid_until=valid_until,
        recorded_by=actor,
        supersedes=supersedes,
    )
    condition.save()
    return condition


@transaction.atomic
def review_athlete_condition(*, user, condition, accept):
    actor = _assert_can_edit(
        user, condition.athlete_profile, condition.organization, health=True
    )
    condition = AthleteCondition.objects.select_for_update().get(pk=condition.pk)
    if condition.status != condition.Status.PROPOSED:
        raise ValidationError("Només es pot revisar una condició pendent.")
    if accept:
        if condition.supersedes_id:
            previous = AthleteCondition.objects.select_for_update().get(
                pk=condition.supersedes_id
            )
            if previous.status == previous.Status.CONFIRMED:
                previous.status = previous.Status.SUPERSEDED
                previous.save(update_fields=("status", "updated_at"))
        condition.status = condition.Status.CONFIRMED
        condition.confirmed_by = actor
        condition.confirmed_at = timezone.now()
    else:
        condition.status = condition.Status.REJECTED
    condition.save(
        update_fields=("status", "confirmed_by", "confirmed_at", "updated_at")
    )
    return condition


@transaction.atomic
def resolve_athlete_condition(*, user, condition, ended_at=None):
    _assert_can_edit(user, condition.athlete_profile, condition.organization, health=True)
    condition = AthleteCondition.objects.select_for_update().get(pk=condition.pk)
    if condition.status != condition.Status.CONFIRMED:
        raise ValidationError("Només es pot resoldre una condició confirmada.")
    condition.status = condition.Status.RESOLVED
    condition.ended_at = ended_at or timezone.now()
    condition.save(update_fields=("status", "ended_at", "updated_at"))
    return condition


@transaction.atomic
def propose_athlete_insight(
    *,
    user,
    athlete,
    kind,
    statement,
    rationale,
    confidence,
    organization=None,
    evidence_window_start=None,
    evidence_window_end=None,
    valid_until=None,
    model_name="",
):
    athlete_profile = _profile(athlete)
    actor = _assert_can_edit(
        user,
        athlete_profile,
        organization,
        health=kind == AthleteInsight.Kind.RISK_SIGNAL,
    )
    insight = AthleteInsight(
        athlete_profile=athlete_profile,
        organization=organization,
        kind=kind,
        statement=statement,
        rationale=rationale,
        confidence=confidence,
        evidence_window_start=evidence_window_start,
        evidence_window_end=evidence_window_end,
        valid_until=valid_until,
        model_name=model_name,
        triggered_by=actor,
    )
    insight.save()
    return insight


@transaction.atomic
def attach_athlete_insight_evidence(
    *,
    user,
    insight,
    observation=None,
    measurement=None,
    condition=None,
    training_item_result=None,
    contribution="",
):
    needs_health = insight.kind == AthleteInsight.Kind.RISK_SIGNAL or condition is not None
    if measurement and measurement.domain in SENSITIVE_MEASUREMENT_DOMAINS:
        needs_health = True
    _assert_can_edit(user, insight.athlete_profile, insight.organization, health=needs_health)
    link = AthleteInsightEvidence(
        insight=insight,
        observation=observation,
        measurement=measurement,
        condition=condition,
        training_item_result=training_item_result,
        contribution=contribution,
    )
    link.save()
    return link


@transaction.atomic
def review_athlete_insight(*, user, insight, accept):
    actor = _assert_can_edit(
        user,
        insight.athlete_profile,
        insight.organization,
        health=insight.kind == AthleteInsight.Kind.RISK_SIGNAL,
    )
    insight = AthleteInsight.objects.select_for_update().get(pk=insight.pk)
    if insight.status != insight.Status.PROPOSED:
        raise ValidationError("Només es pot revisar una interpretació proposada.")
    if accept and not insight.evidence_links.exists():
        raise ValidationError("No es pot confirmar una interpretació sense evidències.")
    if accept:
        insight.status = insight.Status.CONFIRMED
        insight.confirmed_by = actor
        insight.confirmed_at = timezone.now()
    else:
        insight.status = insight.Status.REJECTED
    insight.save(
        update_fields=("status", "confirmed_by", "confirmed_at", "updated_at")
    )
    return insight
