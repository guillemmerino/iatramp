from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils import timezone

from iatrain.models import AthleteProfile, CoachAthleteRelation, TrainingItemResult
from iatrain.services import has_athlete_access, person_for_user

from .models import AthleteCondition, AthleteInsight, AthleteMeasurement
from .services import SENSITIVE_MEASUREMENT_DOMAINS


def _profile(value):
    if isinstance(value, AthleteProfile):
        return value
    try:
        return value.athlete_profile
    except (AttributeError, AthleteProfile.DoesNotExist):
        raise ValidationError("La persona necessita un perfil de gimnasta.")


def _decimal(value):
    return str(value) if isinstance(value, Decimal) else value


def _decimal_display(value):
    if not isinstance(value, Decimal):
        return value
    rendered = format(value, "f").rstrip("0").rstrip(".")
    return (rendered or "0").replace(".", ",")


def _iso(value):
    return value.isoformat() if value else None


def _age_on(birth_date, on_date):
    if birth_date is None:
        return None
    return on_date.year - birth_date.year - (
        (on_date.month, on_date.day) < (birth_date.month, birth_date.day)
    )


def _organization_scope(queryset, organization):
    if organization is None:
        return queryset
    return queryset.filter(Q(organization=organization) | Q(organization__isnull=True))


def _measurement_payload(measurement):
    return {
        "id": measurement.pk,
        "domain": measurement.domain,
        "metric_code": measurement.metric_code,
        "metric_label": measurement.metric_label,
        "value": _decimal(measurement.value),
        "display_value": _decimal_display(measurement.value),
        "unit": measurement.unit,
        "side": measurement.side,
        "protocol": measurement.protocol,
        "source": measurement.source,
        "uncertainty": _decimal(measurement.uncertainty),
        "measured_at": _iso(measurement.measured_at),
        "valid_until": _iso(measurement.valid_until),
        "notes": measurement.notes,
    }


def _condition_payload(condition):
    return {
        "id": condition.pk,
        "category": condition.category,
        "title": condition.title,
        "narrative": condition.narrative,
        "evidence": condition.evidence,
        "body_region": (
            {
                "code": condition.body_region.code,
                "name": condition.body_region.name,
                "kind": condition.body_region.kind,
            }
            if condition.body_region_id
            else None
        ),
        "applicability_scope": condition.applicability_scope,
        "applicability_scope_label": condition.get_applicability_scope_display(),
        "laterality": condition.laterality,
        "severity": condition.severity,
        "training_impact": condition.training_impact,
        "training_impact_label": condition.get_training_impact_display(),
        "source": condition.source,
        "started_at": _iso(condition.started_at),
        "valid_until": _iso(condition.valid_until),
        "confirmed_at": _iso(condition.confirmed_at),
    }


def _insight_payload(insight):
    return {
        "id": insight.pk,
        "kind": insight.kind,
        "statement": insight.statement,
        "rationale": insight.rationale,
        "confidence": _decimal(insight.confidence),
        "status": insight.status,
        "evidence_window_start": _iso(insight.evidence_window_start),
        "evidence_window_end": _iso(insight.evidence_window_end),
        "valid_until": _iso(insight.valid_until),
        "model_name": insight.model_name,
        "evidence": [
            {
                "type": (
                    "observation"
                    if link.observation_id
                    else "measurement"
                    if link.measurement_id
                    else "condition"
                    if link.condition_id
                    else "training_item_result"
                ),
                "id": (
                    link.observation_id
                    or link.measurement_id
                    or link.condition_id
                    or link.training_item_result_id
                ),
                "contribution": link.contribution,
            }
            for link in insight.evidence_links.all()
        ],
    }


def build_athlete_profile_context(
    *,
    user,
    athlete,
    organization=None,
    as_of=None,
    history_days=42,
    observation_limit=20,
    measurement_history_limit=5,
    result_limit=60,
):
    """Build a serializable, point-in-time projection for reasoning and selection.

    Confirmed facts and interpretations are kept separate from proposals. Missing
    health permission is made explicit so a selector cannot assume that no
    restrictions exist.
    """

    athlete_profile = _profile(athlete)
    as_of = as_of or timezone.now()
    actor = person_for_user(user)
    if actor is None:
        raise PermissionDenied("El compte ha d'estar vinculat a una persona activa.")
    if organization is None and not getattr(user, "is_superuser", False):
        if actor.pk != athlete_profile.person_id:
            today = timezone.localdate()
            global_access = CoachAthleteRelation.objects.filter(
                coach_profile__person=actor,
                coach_profile__is_active=True,
                athlete_profile=athlete_profile,
                athlete_profile__is_active=True,
                organization__isnull=True,
                is_active=True,
                can_view_training=True,
                start_date__lte=today,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            if not global_access.exists():
                raise ValidationError(
                    "Cal indicar l'organització per construir el context d'un altre gimnasta."
                )
    if not has_athlete_access(
        user,
        athlete_profile,
        permission="can_view_training",
        organization=organization,
    ):
        raise PermissionDenied("No pots consultar el context d'aquest gimnasta.")
    health_access = has_athlete_access(
        user,
        athlete_profile,
        permission="can_view_health_data",
        organization=organization,
    )

    sport_profiles = [
        {
            "discipline": profile.discipline,
            "level_code": profile.level_code,
            "training_started_on": _iso(profile.training_started_on),
            "preferred_laterality": profile.preferred_laterality,
            "notes": profile.notes,
        }
        for profile in athlete_profile.sport_profiles.filter(is_active=True)
    ]

    measurements = athlete_profile.measurements.filter(
        status=AthleteMeasurement.Status.VALID,
        superseded_by__isnull=True,
        measured_at__lte=as_of,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=as_of))
    measurements = _organization_scope(measurements, organization)
    if not health_access:
        measurements = measurements.exclude(domain__in=SENSITIVE_MEASUREMENT_DOMAINS)
    measurements = measurements.order_by("-measured_at", "-id")
    measurement_groups = defaultdict(list)
    for measurement in measurements:
        key = (measurement.metric_code, measurement.side)
        if len(measurement_groups[key]) < measurement_history_limit:
            measurement_groups[key].append(_measurement_payload(measurement))
    latest_measurements = [values[0] for values in measurement_groups.values()]

    observations = athlete_profile.person.training_observations.filter(
        superseded_by__isnull=True,
        observed_at__lte=as_of,
    ).exclude(status="no_longer_current")
    if organization is not None:
        observations = observations.filter(
            Q(organization=organization)
            | Q(organization__isnull=True, training_context__organization=organization)
            | Q(organization__isnull=True, training_context__isnull=True)
        )
    observations = observations.select_related("concept", "authored_by").order_by(
        "-observed_at", "-id"
    )[:observation_limit]
    observation_payload = [
        {
            "id": observation.pk,
            "category": observation.category,
            "narrative": observation.narrative,
            "evidence": observation.evidence,
            "status": observation.status,
            "confidence": _decimal(observation.confidence),
            "intensity": observation.intensity,
            "observed_at": _iso(observation.observed_at),
            "concept": (
                {
                    "id": observation.concept_id,
                    "name": observation.concept.name,
                    "kind": observation.concept.kind,
                }
                if observation.concept_id
                else None
            ),
            "authored_by": observation.authored_by.display_name,
        }
        for observation in observations
    ]

    active_conditions = []
    if health_access:
        conditions = athlete_profile.conditions.filter(
            status=AthleteCondition.Status.CONFIRMED,
            started_at__lte=as_of,
            ended_at__isnull=True,
        ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=as_of))
        conditions = _organization_scope(conditions, organization).select_related(
            "body_region"
        )
        active_conditions = [_condition_payload(condition) for condition in conditions]

    result_start = as_of - timedelta(days=history_days)
    results = TrainingItemResult.objects.filter(
        athlete_profile=athlete_profile,
        recorded_at__gte=result_start,
        recorded_at__lte=as_of,
    )
    if organization is not None:
        results = results.filter(execution__session__organization=organization)
    results = results.select_related(
        "execution__session",
        "session_item",
        "exercise_revision_performed__exercise",
    ).order_by("-recorded_at", "-id")[:result_limit]
    training_payload = []
    for result in results:
        row = {
            "id": result.pk,
            "session_id": result.execution.session_id,
            "session_started_at": _iso(result.execution.started_at),
            "item_id": result.session_item_id,
            "item_title": result.session_item.title,
            "completion_status": result.completion_status,
            "exercise_revision_id": result.exercise_revision_performed_id,
            "exercise": (
                result.exercise_revision_performed.exercise.name
                if result.exercise_revision_performed_id
                else None
            ),
            "actual_sets": result.actual_sets,
            "actual_repetitions": result.actual_repetitions,
            "actual_duration_seconds": result.actual_duration_seconds,
            "actual_load_value": _decimal(result.actual_load_value),
            "actual_load_unit": result.actual_load_unit,
            "perceived_exertion": _decimal(result.perceived_exertion),
            "execution_quality": result.execution_quality,
            "recorded_at": _iso(result.recorded_at),
        }
        if health_access:
            row.update(
                {
                    "pain_response": result.pain_response,
                    "athlete_feedback": result.athlete_feedback,
                    "coach_feedback": result.coach_feedback,
                }
            )
        training_payload.append(row)

    insights = athlete_profile.insights.filter(
        status__in=(AthleteInsight.Status.CONFIRMED, AthleteInsight.Status.PROPOSED)
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=as_of))
    insights = _organization_scope(insights, organization)
    if not health_access:
        insights = insights.exclude(kind=AthleteInsight.Kind.RISK_SIGNAL)
    insights = insights.prefetch_related("evidence_links")
    confirmed_insights = []
    proposed_insights = []
    for insight in insights:
        payload = _insight_payload(insight)
        if insight.status == AthleteInsight.Status.CONFIRMED:
            confirmed_insights.append(payload)
        else:
            proposed_insights.append(payload)

    blocking_impacts = {
        AthleteCondition.TrainingImpact.MODIFY,
        AthleteCondition.TrainingImpact.AVOID,
        AthleteCondition.TrainingImpact.STOP,
    }
    return {
        "generated_at": _iso(timezone.now()),
        "as_of": _iso(as_of),
        "athlete": {
            "person_id": athlete_profile.person_id,
            "athlete_profile_id": athlete_profile.pk,
            "display_name": athlete_profile.person.display_name,
            "birth_date": _iso(athlete_profile.person.birth_date),
            "age_years": _age_on(athlete_profile.person.birth_date, as_of.date()),
        },
        "scope": {
            "organization_id": organization.pk if organization else None,
            "health_data_available": health_access,
            "history_days": history_days,
        },
        "sport_profiles": sport_profiles,
        "latest_measurements": latest_measurements,
        "measurement_history": [
            {"metric_code": key[0], "side": key[1], "values": values}
            for key, values in measurement_groups.items()
        ],
        "active_conditions": active_conditions,
        "current_observations": observation_payload,
        "recent_training_responses": training_payload,
        "confirmed_insights": confirmed_insights,
        "proposed_insights": proposed_insights,
        "selection_guardrails": {
            "requires_health_review": not health_access,
            "has_training_modifiers": any(
                condition["training_impact"] in blocking_impacts
                for condition in active_conditions
            ),
            "authoritative_insight_status": AthleteInsight.Status.CONFIRMED,
            "proposed_insights_are_non_authoritative": True,
        },
    }
