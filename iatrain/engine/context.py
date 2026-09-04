"""Point-in-time context used by the physical block generator."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError

from iatrain.athletes.context import build_athlete_profile_context
from iatrain.models import GymEquipment, TrainingSessionRevision
from iatrain.services import person_for_user

from .guidelines import AthletePrescriptionProfile, athlete_prescription_profile


EQUIPMENT_ALIASES = {
    "mancuerna": "dumbbell",
    "mancuernes": "dumbbell",
    "dumbbell": "dumbbell",
    "barra": "barbell",
    "barbell": "barbell",
    "kettlebell": "kettlebell",
    "banda": "elastic_band",
    "banda_elastica": "elastic_band",
    "elastic_band": "elastic_band",
    "banc": "bench",
    "bench": "bench",
    "caixa": "box",
    "box": "box",
    "matalas": "mat",
    "mat": "mat",
    "pilota_medicinal": "medicine_ball",
    "medicine_ball": "medicine_ball",
    "pilota_estabilitat": "stability_ball",
    "politja": "cable_machine",
    "cable_machine": "cable_machine",
    "barra_dominades": "pull_up_bar",
    "pull_up_bar": "pull_up_bar",
    "suspensio": "suspension_trainer",
}


@dataclass(frozen=True, slots=True)
class AthleteEngineContext:
    participant_plan_id: int
    payload: dict
    prescription_profile: AthletePrescriptionProfile


@dataclass(frozen=True, slots=True)
class BlockEngineContext:
    revision: TrainingSessionRevision
    owner: object
    athletes: tuple[AthleteEngineContext, ...]
    available_equipment_ids: tuple[int, ...]
    available_equipment_codes: frozenset[str]
    warnings: tuple[str, ...]


def _token(value):
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", normalized.casefold()).strip("_")


def equipment_codes(rows):
    codes = set()
    for row in rows:
        for code in row.catalog_equipment_codes:
            codes.add(_token(code))
        name_token = _token(row.name)
        codes.add(EQUIPMENT_ALIASES.get(name_token, name_token))
    return frozenset(code for code in codes if code)


def build_block_engine_context(*, user, revision):
    if not isinstance(revision, TrainingSessionRevision):
        raise ValidationError("La versió de sessió no és vàlida.")
    owner = person_for_user(user)
    if owner is None:
        raise ValidationError("El compte necessita una persona activa.")
    inventory = ()
    if revision.session.gym_id:
        inventory = tuple(
            GymEquipment.objects.filter(gym_id=revision.session.gym_id)
            .exclude(availability=GymEquipment.Availability.UNAVAILABLE)
            .order_by("id")
        )
    athlete_contexts = []
    warnings = []
    plans = revision.participant_plans.select_related("athlete_profile__person")
    for plan in plans:
        payload = build_athlete_profile_context(
            user=user,
            athlete=plan.athlete_profile,
            organization=revision.session.organization,
        )
        athlete_contexts.append(
            AthleteEngineContext(
                participant_plan_id=plan.pk,
                payload=payload,
                prescription_profile=athlete_prescription_profile(payload),
            )
        )
        if payload["selection_guardrails"]["requires_health_review"]:
            warnings.append(
                f"No hi ha accés a les dades de salut del participant {plan.pk}; "
                "la proposta necessita revisió explícita."
            )
    return BlockEngineContext(
        revision=revision,
        owner=owner,
        athletes=tuple(athlete_contexts),
        available_equipment_ids=tuple(row.pk for row in inventory),
        available_equipment_codes=equipment_codes(inventory),
        warnings=tuple(warnings),
    )


def build_group_engine_summary(context, participant_ids):
    """Return a small factual group projection; no missing datum becomes a restriction."""

    active = {int(value) for value in participant_ids}
    stages = {}
    experience = {}
    conditions = []
    last_training = {}
    response_counts = {}
    health_unavailable = []
    for athlete in context.athletes:
        participant_id = athlete.participant_plan_id
        if participant_id not in active:
            continue
        stage = athlete.prescription_profile.population_stage
        level = athlete.prescription_profile.experience_level
        stages[stage] = stages.get(stage, 0) + 1
        experience[level] = experience.get(level, 0) + 1
        payload = athlete.payload
        if not payload.get("scope", {}).get("health_data_available", False):
            health_unavailable.append(participant_id)
        for condition in payload.get("active_conditions", []):
            conditions.append(
                {
                    "participant_plan_id": participant_id,
                    "condition_id": condition.get("id"),
                    "training_impact": condition.get("training_impact"),
                    "laterality": condition.get("laterality"),
                    "body_region_code": (
                        condition.get("body_region") or {}
                    ).get("code", ""),
                }
            )
        responses = payload.get("recent_training_responses", [])
        response_counts[str(participant_id)] = len(responses)
        last_training[str(participant_id)] = (
            responses[0].get("recorded_at") if responses else None
        )
    return {
        "participant_count": len(active),
        "population_stages": stages,
        "experience_levels": experience,
        "active_condition_impacts": conditions,
        "health_data_unavailable_participant_ids": sorted(health_unavailable),
        "recent_response_counts": response_counts,
        "last_training_at": last_training,
        "detail_policy": (
            "Una absència és incertesa; amplia només les participants necessàries."
        ),
    }
