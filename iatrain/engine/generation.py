"""Deterministic physical block proposal assembly."""

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP

from iatrain.models import PhysicalExercisePrescription, TrainingSessionItem
from iatrain_exercises.models import ExerciseObjective

from .contracts import (
    AthleteAdjustmentProposal,
    BlockCoverage,
    BlockGenerationProposal,
    BlockItemProposal,
    BlockLoadEstimate,
    ExerciseAlternativeProposal,
    ExerciseDoseProposal,
)
from .guidelines import GUIDELINE_VERSION
from .scoring import EXPERIENCE_ORDER, GenerationBlocked, rank_exercise_candidates
from .validation import validate_block_generation_proposal


ENGINE_VERSION = "physical-block-engine-1.0"


def _target_position(target):
    return {"low": 0, "moderate": 1, "high": 2, "very_high": 2}.get(target, 1)


def _pick(values, index):
    available = [value for value in values if value is not None]
    if not available:
        return None
    return available[min(index, len(available) - 1)]


def _dose_for(candidate, request):
    guide = candidate.guideline
    position = _target_position(request.target_intensity)
    if request.block_role in {"preparation", "recovery"}:
        position = 0
    sets = _pick((guide.min_sets, guide.default_sets, guide.max_sets), position)
    repetitions = _pick(
        (guide.min_repetitions, guide.default_repetitions, guide.max_repetitions),
        position,
    )
    duration = _pick(
        (
            guide.min_duration_seconds,
            guide.default_duration_seconds,
            guide.max_duration_seconds,
        ),
        position,
    )
    rest = _pick(
        (guide.min_rest_seconds, guide.default_rest_seconds, guide.max_rest_seconds),
        position,
    )
    rpe = None
    if guide.min_rpe is not None and guide.max_rpe is not None:
        if position == 0:
            rpe = guide.min_rpe
        elif position == 1:
            rpe = (guide.min_rpe + guide.max_rpe) / 2
        else:
            rpe = guide.max_rpe
        rpe = rpe.quantize(Decimal("0.5"), rounding=ROUND_HALF_UP)
    intent = (
        PhysicalExercisePrescription.ConcentricIntent.EXPLOSIVE
        if request.objective.primary_quality == ExerciseObjective.Objective.POWER
        else PhysicalExercisePrescription.ConcentricIntent.CONTROLLED
    )
    notes = guide.quality_stop_rule
    if "avoid_failure" in request.hard_constraints:
        notes = (notes + " Evita arribar a la fallada.").strip()
    return ExerciseDoseProposal(
        exercise_revision_id=candidate.revision.pk,
        dose_mode=guide.dose_mode,
        sets=sets,
        repetitions=repetitions if guide.dose_mode == "repetitions" else None,
        duration_seconds=(
            duration if guide.dose_mode in {"duration", "hold"} else None
        ),
        intensity_metric=(
            PhysicalExercisePrescription.IntensityMetric.RPE
            if rpe is not None
            else PhysicalExercisePrescription.IntensityMetric.NONE
        ),
        intensity_value=rpe,
        concentric_intent=intent,
        rest_between_sets_seconds=rest,
        execution_notes=notes,
    )


def _duration_seconds(candidate, dose):
    guide = candidate.guideline
    if dose.repetitions:
        work = int(
            Decimal(dose.sets)
            * Decimal(dose.repetitions)
            * (guide.seconds_per_repetition or Decimal("4"))
        )
    else:
        work = dose.sets * (dose.duration_seconds or 20)
    return max(
        30,
        guide.setup_duration_seconds
        + work
        + max(dose.sets - 1, 0) * dose.rest_between_sets_seconds,
    )


def _reduce_to_budget(candidate, dose, maximum_seconds):
    current = dose
    while _duration_seconds(candidate, current) > maximum_seconds and current.sets > 1:
        current = replace(current, sets=current.sets - 1)
    return current


def _condition_adjustment(athlete, candidate, dose):
    regions = candidate.region_codes
    modify_titles = []
    for condition in athlete.payload.get("active_conditions", []):
        if condition.get("training_impact") != "modify":
            continue
        body = condition.get("body_region") or {}
        code = str(body.get("code", "")).casefold().replace("-", "_")
        tokens = {code, *code.split("_")} if code else set()
        if regions & tokens:
            modify_titles.append(condition.get("title", "condició activa"))
    if modify_titles:
        repetitions = max(1, int(dose.repetitions * Decimal("0.8"))) if dose.repetitions else None
        duration = max(5, int(dose.duration_seconds * Decimal("0.8"))) if dose.duration_seconds else None
        intensity = max(Decimal("1"), dose.intensity_value - Decimal("1")) if dose.intensity_value else None
        return AthleteAdjustmentProposal(
            participant_plan_id=athlete.participant_plan_id,
            rationale="Adaptació per " + ", ".join(modify_titles),
            sets=max(1, dose.sets - 1),
            repetitions=repetitions,
            duration_seconds=duration,
            intensity_metric=dose.intensity_metric if intensity is not None else "",
            intensity_value=intensity,
            rest_between_sets_seconds=dose.rest_between_sets_seconds + 30,
            adaptation_notes="Redueix demanda i revalora la resposta durant l'execució.",
        )
    return None


def _experience_adjustment(athlete, candidate, dose, minimum_experience):
    if EXPERIENCE_ORDER[athlete.prescription_profile.experience_level] <= EXPERIENCE_ORDER[minimum_experience]:
        return None
    if dose.sets >= candidate.guideline.max_sets:
        return None
    return AthleteAdjustmentProposal(
        participant_plan_id=athlete.participant_plan_id,
        rationale="Més experiència d'entrenament que el nivell base del grup.",
        sets=min(candidate.guideline.max_sets, dose.sets + 1),
        adaptation_notes="Mantén la mateixa qualitat tècnica i no superis l'esforç objectiu.",
    )


def _select_candidates(candidates, desired_count, requested_patterns):
    selected = []
    families = set()
    patterns = set()
    for candidate in candidates:
        family_id = candidate.revision.exercise.parent_id
        pattern = candidate.revision.movement_pattern
        if family_id in families:
            continue
        if not requested_patterns and pattern in patterns and len(patterns) < desired_count:
            continue
        selected.append(candidate)
        families.add(family_id)
        patterns.add(pattern)
        if len(selected) >= desired_count:
            break
    if len(selected) < desired_count:
        for candidate in candidates:
            if candidate in selected or candidate.revision.exercise.parent_id in families:
                continue
            selected.append(candidate)
            families.add(candidate.revision.exercise.parent_id)
            if len(selected) >= desired_count:
                break
    return selected


def generate_block_proposal(*, context, request):
    candidates = rank_exercise_candidates(context=context, request=request)
    if not candidates:
        raise GenerationBlocked(
            "No hi ha exercicis compatibles amb l'objectiu, el material i les restriccions."
        )
    budget = request.planned_duration_minutes * 60
    desired_count = max(1, min(6, request.planned_duration_minutes // 3 or 1))
    selected = _select_candidates(
        candidates, desired_count, set(request.objective.movement_patterns)
    )
    if not selected:
        raise GenerationBlocked("No s'ha pogut construir una combinació d'exercicis.")

    minimum_experience = min(
        (athlete.prescription_profile.experience_level for athlete in context.athletes),
        key=lambda value: EXPERIENCE_ORDER[value],
        default="novice",
    )
    items = []
    used_seconds = 0
    all_warnings = list(context.warnings)
    fallback_count = 0
    for index, candidate in enumerate(selected, start=1):
        remaining_items = len(selected) - index + 1
        fair_share = max(60, (budget - used_seconds) // remaining_items)
        dose = _reduce_to_budget(candidate, _dose_for(candidate, request), fair_share)
        duration = _duration_seconds(candidate, dose)
        if used_seconds + duration > budget:
            if items:
                break
            dose = _reduce_to_budget(candidate, dose, budget)
            duration = min(_duration_seconds(candidate, dose), budget)
        alternatives = []
        for alternative in candidates:
            if alternative in selected:
                continue
            if alternative.revision.movement_pattern != candidate.revision.movement_pattern:
                continue
            alternatives.append(
                ExerciseAlternativeProposal(
                    exercise_revision_id=alternative.revision.pk,
                    trigger="coach_decision",
                    rationale=f"Alternativa del mateix patró amb puntuació {alternative.score}/100.",
                )
            )
            break
        adjustments = []
        for athlete in context.athletes:
            adjustment = _condition_adjustment(athlete, candidate, dose)
            if adjustment is None:
                adjustment = _experience_adjustment(
                    athlete, candidate, dose, minimum_experience
                )
            if adjustment:
                adjustments.append(adjustment)
        if not candidate.guideline.is_exercise_specific:
            fallback_count += 1
        all_warnings.extend(candidate.warnings)
        source_label = (
            candidate.guideline.source
            if candidate.guideline.is_exercise_specific
            else "baseline professional versionada"
        )
        items.append(
            BlockItemProposal(
                sequence_index=index,
                item_type=TrainingSessionItem.ItemType.PHYSICAL_EXERCISE,
                title=candidate.revision.exercise.name,
                instructions=candidate.revision.execution,
                coaching_cues=candidate.revision.coaching_cues,
                planned_duration_seconds=duration,
                selection_rationale=(
                    f"{candidate.rationale} Dosi basada en {source_label}."
                ),
                dose=dose,
                alternatives=tuple(alternatives),
                athlete_adjustments=tuple(adjustments),
            )
        )
        used_seconds += duration

    if not items:
        raise GenerationBlocked("La dosificació mínima no cap dins del temps disponible.")
    if fallback_count:
        all_warnings.append(
            f"{fallback_count} exercicis utilitzen una baseline professional general; "
            "convé validar una guideline específica."
        )
    loads = []
    for candidate in selected[: len(items)]:
        guide = candidate.guideline
        loads.append(
            (
                guide.mechanical_impact,
                guide.neuromuscular_load,
                guide.metabolic_load,
                guide.coordinative_load,
            )
        )
    divisor = Decimal(len(loads))
    load_values = [
        (sum(row[column] for row in loads) / divisor).quantize(Decimal("0.1"))
        for column in range(4)
    ]
    qualities = [request.objective.primary_quality, *request.objective.secondary_qualities]
    patterns = tuple(dict.fromkeys(item.revision.movement_pattern for item in selected[: len(items)]))
    regions = tuple(
        sorted({region for item in selected[: len(items)] for region in item.region_codes})
    )
    average_score = sum(item.score for item in selected[: len(items)]) / Decimal(len(items))
    confidence = max(Decimal("0"), min(Decimal("1"), average_score / Decimal("100")))
    proposal = BlockGenerationProposal(
        request=request,
        items=tuple(items),
        estimated_duration_seconds=used_seconds,
        estimated_load=BlockLoadEstimate(
            mechanical_impact=load_values[0],
            neuromuscular=load_values[1],
            metabolic=load_values[2],
            coordinative=load_values[3],
            notes="Estimació relativa 0–5; no és una mesura clínica ni una càrrega externa absoluta.",
        ),
        coverage=BlockCoverage(
            physical_qualities=tuple(dict.fromkeys(qualities)),
            movement_patterns=patterns,
            body_region_codes=regions,
        ),
        satisfied_constraints=tuple(request.hard_constraints),
        warnings=tuple(dict.fromkeys(all_warnings)),
        confidence=confidence.quantize(Decimal("0.01")),
        generator_reference=f"{ENGINE_VERSION} · {GUIDELINE_VERSION}",
    )
    validate_block_generation_proposal(
        proposal,
        revision=context.revision,
        exercise_owner=context.owner,
        require_validated_exercises="validated_only" in request.hard_constraints,
    )
    return proposal
