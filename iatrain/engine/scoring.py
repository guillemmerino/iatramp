"""Deterministic candidate eligibility and explainable multi-criteria scoring."""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Prefetch

from iatrain_exercises.models import (
    ExerciseEquipmentRequirement,
    ExerciseObjective,
    ExerciseRevision,
)
from iatrain_motion.models import EditorialStatus

from .guidelines import AthletePrescriptionProfile, ResolvedGuideline, resolve_guideline


class GenerationBlocked(Exception):
    pass


PATTERN_REGIONS = {
    "squat": {"lower_limb", "hip", "knee", "ankle"},
    "hinge": {"lower_limb", "hip", "knee", "lumbar", "spine"},
    "ankle_dominant": {"lower_limb", "ankle", "foot"},
    "locomotion": {"lower_limb", "hip", "knee", "ankle", "foot"},
    "horizontal_push": {"upper_limb", "shoulder", "elbow", "wrist"},
    "vertical_push": {"upper_limb", "shoulder", "elbow", "wrist", "spine"},
    "horizontal_pull": {"upper_limb", "shoulder", "elbow", "wrist", "thoracic"},
    "vertical_pull": {"upper_limb", "shoulder", "elbow", "wrist"},
    "trunk_control": {"trunk", "lumbar", "spine", "pelvis"},
    "other": set(),
}

OBJECTIVE_MODALITIES = {
    "strength": {"strength", "muscular_endurance"},
    "max_strength": {"strength"},
    "hypertrophy": {"strength", "muscular_endurance"},
    "muscular_endurance": {"muscular_endurance", "strength"},
    "power": {"power"},
    "motor_control": {"motor_control", "warm_up"},
    "mobility": {"mobility", "warm_up", "motor_control"},
    "preparation": {"warm_up", "mobility", "motor_control", "power"},
}

EXPERIENCE_ORDER = {"novice": 0, "intermediate": 1, "advanced": 2, "all": 0}
DIFFICULTY_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


@dataclass(frozen=True, slots=True)
class ScoredExercise:
    revision: ExerciseRevision
    score: Decimal
    components: dict
    rationale: str
    required_equipment_codes: frozenset[str]
    region_codes: frozenset[str]
    guideline: ResolvedGuideline
    warnings: tuple[str, ...]


def _condition_region_tokens(condition):
    body_region = condition.get("body_region") or {}
    token = str(body_region.get("code", "")).casefold().replace("-", "_")
    values = {part for part in token.split("_") if part}
    if token:
        values.add(token)
    return values


def _group_profile(context):
    profiles = [athlete.prescription_profile for athlete in context.athletes]
    if not profiles:
        return AthletePrescriptionProfile("all", "novice", None, None)
    experience = min(profiles, key=lambda item: EXPERIENCE_ORDER[item.experience_level]).experience_level
    stage_priority = {"child": 0, "adolescent": 1, "older_adult": 2, "adult": 3, "all": 4}
    stage = min(profiles, key=lambda item: stage_priority[item.population_stage]).population_stage
    ages = [item.age_years for item in profiles if item.age_years is not None]
    years = [item.training_years for item in profiles if item.training_years is not None]
    return AthletePrescriptionProfile(
        population_stage=stage,
        experience_level=experience,
        age_years=min(ages) if ages else None,
        training_years=min(years) if years else None,
    )


def _health_effect(context, candidate_regions):
    safety_penalty = 0
    warnings = []
    for athlete in context.athletes:
        for condition in athlete.payload.get("active_conditions", []):
            impact = condition.get("training_impact")
            if impact == "stop":
                raise GenerationBlocked(
                    "Hi ha una indicació activa de no entrenar. Revisa el perfil abans de generar el bloc."
                )
            overlap = candidate_regions & _condition_region_tokens(condition)
            if not overlap:
                continue
            if impact == "avoid":
                return None, (
                    f"Exclòs per una condició confirmada que indica evitar {', '.join(sorted(overlap))}.",
                )
            if impact == "modify":
                safety_penalty += 4
                warnings.append(
                    f"Cal adaptar la dosi del participant {athlete.participant_plan_id} "
                    f"per {condition.get('title', 'una condició activa')}."
                )
            elif impact == "monitor":
                safety_penalty += 1
    return min(safety_penalty, 10), tuple(dict.fromkeys(warnings))


def _recent_response_score(context, revision_id):
    score = Decimal("7")
    seen = 0
    for athlete in context.athletes:
        for result in athlete.payload.get("recent_training_responses", []):
            if result.get("exercise_revision_id") != revision_id:
                continue
            seen += 1
            if result.get("pain_response"):
                score -= Decimal("3")
            quality = str(result.get("execution_quality") or "").casefold()
            if quality in {"good", "excellent", "alta", "bona"}:
                score += Decimal("1")
            if result.get("completion_status") in {"not_completed", "stopped"}:
                score -= Decimal("2")
    if not seen:
        return Decimal("6")
    return max(Decimal("0"), min(Decimal("10"), score))


def rank_exercise_candidates(*, context, request):
    profile = _group_profile(context)
    objective = request.objective.primary_quality
    requested_patterns = set(request.objective.movement_patterns)
    hard = set(request.hard_constraints)
    queryset = (
        ExerciseRevision.objects.filter(
            exercise__catalog__owner=context.owner,
            exercise__catalog__is_active=True,
            exercise__is_active=True,
            exercise__kind="variant",
        )
        .exclude(editorial_status=EditorialStatus.RETIRED)
        .select_related("exercise", "exercise__catalog")
        .prefetch_related(
            "objectives",
            "constraints",
            "prescription_guidelines",
            Prefetch(
                "equipment_requirements",
                queryset=ExerciseEquipmentRequirement.objects.select_related("equipment"),
            ),
        )
    )
    candidates = []
    for revision in queryset:
        warnings = []
        if "validated_only" in hard and revision.editorial_status != EditorialStatus.VALIDATED:
            continue
        if revision.editorial_status != EditorialStatus.VALIDATED:
            warnings.append("La revisió de l'exercici encara és un esborrany editorial.")

        required_equipment = frozenset(
            row.equipment.code
            for row in revision.equipment_requirements.all()
            if row.requirement == ExerciseEquipmentRequirement.Requirement.REQUIRED
        )
        if "bodyweight_only" in hard or "no_equipment" in hard:
            if required_equipment or revision.requires_equipment:
                continue
        if not required_equipment.issubset(context.available_equipment_codes):
            continue

        name_code = f"{revision.exercise.code} {revision.exercise.name}".casefold()
        if "no_jumps" in hard and any(token in name_code for token in ("jump", "salt", "pogo")):
            continue
        if {"no_impact", "avoid_high_impact"} & hard and (
            revision.modality == ExerciseRevision.Modality.POWER
            or any(token in name_code for token in ("jump", "salt", "pogo"))
        ):
            continue

        candidate_regions = frozenset(PATTERN_REGIONS.get(revision.movement_pattern, set()))
        health_penalty, health_warnings = _health_effect(context, candidate_regions)
        if health_penalty is None:
            continue
        warnings.extend(health_warnings)

        difficulty_gap = DIFFICULTY_ORDER[revision.difficulty] - EXPERIENCE_ORDER[profile.experience_level]
        if difficulty_gap >= 2:
            continue
        objectives = {row.objective: row.priority for row in revision.objectives.all()}
        if objectives.get(objective) == ExerciseObjective.Priority.PRIMARY:
            objective_score = Decimal("30")
        elif objective in objectives:
            objective_score = Decimal("25")
        elif revision.modality in OBJECTIVE_MODALITIES.get(objective, set()):
            objective_score = Decimal("18")
        else:
            objective_score = Decimal("8")
        if requested_patterns and revision.movement_pattern in requested_patterns:
            objective_score = min(Decimal("30"), objective_score + Decimal("4"))

        suitability = Decimal("20") - Decimal(str(max(difficulty_gap, 0) * 6))
        if revision.difficulty == "beginner" and profile.experience_level == "advanced":
            suitability -= Decimal("2")
        safety = max(Decimal("0"), Decimal("15") - Decimal(str(health_penalty)))
        critical_constraints = sum(
            row.severity == "critical" for row in revision.constraints.all()
        )
        safety = max(Decimal("0"), safety - Decimal(str(critical_constraints * 2)))
        logistics = Decimal("15") if not required_equipment else Decimal("12")
        coverage = Decimal("10") if not requested_patterns or revision.movement_pattern in requested_patterns else Decimal("6")
        response = _recent_response_score(context, revision.pk)
        editorial_penalty = Decimal("8") if revision.editorial_status != EditorialStatus.VALIDATED else Decimal("0")
        score = objective_score + suitability + safety + logistics + coverage + response - editorial_penalty
        preference_text = " ".join(request.preferences).casefold()
        if preference_text and any(
            token in f"{name_code} {revision.description.casefold()}"
            for token in preference_text.split()
            if len(token) > 4
        ):
            score += Decimal("2")
        score = max(Decimal("0"), min(Decimal("100"), score))
        guideline = resolve_guideline(
            revision,
            profile=profile,
            objective=objective,
            block_role=request.block_role,
        )
        components = {
            "objective": str(objective_score),
            "suitability": str(suitability),
            "safety": str(safety),
            "logistics": str(logistics),
            "coverage": str(coverage),
            "recent_response": str(response),
            "editorial_penalty": str(editorial_penalty),
        }
        candidates.append(
            ScoredExercise(
                revision=revision,
                score=score,
                components=components,
                rationale=(
                    f"Coincidència {objective_score}/30; adequació {suitability}/20; "
                    f"seguretat {safety}/15; logística {logistics}/15; "
                    f"cobertura {coverage}/10; resposta prèvia {response}/10."
                ),
                required_equipment_codes=required_equipment,
                region_codes=candidate_regions,
                guideline=guideline,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.revision.exercise.code))
