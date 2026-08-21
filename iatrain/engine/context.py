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
