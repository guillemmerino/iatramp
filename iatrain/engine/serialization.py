from dataclasses import fields, is_dataclass
from decimal import Decimal

from .contracts import (
    AthleteAdjustmentProposal,
    BlockCoverage,
    BlockGenerationProposal,
    BlockGenerationRequest,
    BlockItemProposal,
    BlockLoadEstimate,
    BlockObjective,
    BlockParticipantProposal,
    ExerciseAlternativeProposal,
    ExerciseDoseProposal,
)


def contract_to_payload(value):
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {
            field.name: contract_to_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [contract_to_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: contract_to_payload(item) for key, item in value.items()}
    return value


def _decimal(value):
    return Decimal(str(value)) if value is not None else None


def request_from_payload(payload):
    objective = payload["objective"]
    return BlockGenerationRequest(
        session_revision_id=int(payload["session_revision_id"]),
        sequence_index=int(payload["sequence_index"]),
        name=payload["name"],
        block_role=payload["block_role"],
        planned_duration_minutes=int(payload["planned_duration_minutes"]),
        objective=BlockObjective(
            description=objective["description"],
            primary_quality=objective["primary_quality"],
            secondary_qualities=tuple(objective.get("secondary_qualities", [])),
            movement_patterns=tuple(objective.get("movement_patterns", [])),
            body_region_codes=tuple(objective.get("body_region_codes", [])),
        ),
        participant_plan_ids=tuple(int(value) for value in payload["participant_plan_ids"]),
        excluded_participant_plan_ids=tuple(
            int(value) for value in payload.get("excluded_participant_plan_ids", [])
        ),
        execution_mode=payload.get("execution_mode", "sequential"),
        domain=payload.get("domain", "physical"),
        target_intensity=payload.get("target_intensity", ""),
        available_equipment_ids=tuple(
            int(value) for value in payload.get("available_equipment_ids", [])
        ),
        hard_constraints=tuple(payload.get("hard_constraints", [])),
        preferences=tuple(payload.get("preferences", [])),
        instructions=payload.get("instructions", ""),
        rounds=int(payload.get("rounds", 1)),
        rest_between_rounds_seconds=int(payload.get("rest_between_rounds_seconds", 0)),
        is_optional=bool(payload.get("is_optional", False)),
        contract_version=payload.get("contract_version", "1.0"),
    )


def _dose(payload):
    if payload is None:
        return None
    return ExerciseDoseProposal(
        exercise_revision_id=int(payload["exercise_revision_id"]),
        dose_mode=payload["dose_mode"],
        sets=int(payload.get("sets", 1)),
        repetitions=payload.get("repetitions"),
        duration_seconds=payload.get("duration_seconds"),
        distance=_decimal(payload.get("distance")),
        distance_unit=payload.get("distance_unit", ""),
        load_value=_decimal(payload.get("load_value")),
        load_unit=payload.get("load_unit", ""),
        intensity_metric=payload.get("intensity_metric", "none"),
        intensity_value=_decimal(payload.get("intensity_value")),
        tempo_eccentric_seconds=payload.get("tempo_eccentric_seconds"),
        tempo_pause_seconds=payload.get("tempo_pause_seconds"),
        tempo_concentric_seconds=payload.get("tempo_concentric_seconds"),
        concentric_intent=payload.get("concentric_intent", "controlled"),
        rest_between_sets_seconds=int(payload.get("rest_between_sets_seconds", 0)),
        execution_notes=payload.get("execution_notes", ""),
    )


def _alternative(payload):
    return ExerciseAlternativeProposal(
        exercise_revision_id=int(payload["exercise_revision_id"]),
        trigger=payload["trigger"],
        rationale=payload["rationale"],
        priority=int(payload.get("priority", 1)),
    )


def _adjustment(payload):
    replacement = payload.get("replacement_exercise_revision_id")
    return AthleteAdjustmentProposal(
        participant_plan_id=int(payload["participant_plan_id"]),
        rationale=payload["rationale"],
        action=payload.get("action", "modify"),
        replacement_exercise_revision_id=int(replacement) if replacement else None,
        sets=payload.get("sets"),
        repetitions=payload.get("repetitions"),
        duration_seconds=payload.get("duration_seconds"),
        load_value=_decimal(payload.get("load_value")),
        load_unit=payload.get("load_unit", ""),
        intensity_metric=payload.get("intensity_metric", ""),
        intensity_value=_decimal(payload.get("intensity_value")),
        rest_between_sets_seconds=payload.get("rest_between_sets_seconds"),
        adaptation_notes=payload.get("adaptation_notes", ""),
    )


def proposal_from_payload(payload):
    items = []
    for row in payload["items"]:
        items.append(
            BlockItemProposal(
                sequence_index=int(row["sequence_index"]),
                item_type=row["item_type"],
                title=row["title"],
                instructions=row.get("instructions", ""),
                coaching_cues=row.get("coaching_cues", ""),
                planned_duration_seconds=row.get("planned_duration_seconds"),
                rest_after_seconds=int(row.get("rest_after_seconds", 0)),
                selection_rationale=row.get("selection_rationale", ""),
                is_optional=bool(row.get("is_optional", False)),
                dose=_dose(row.get("dose")),
                alternatives=tuple(
                    _alternative(item) for item in row.get("alternatives", [])
                ),
                athlete_adjustments=tuple(
                    _adjustment(item) for item in row.get("athlete_adjustments", [])
                ),
            )
        )
    load = payload["estimated_load"]
    coverage = payload["coverage"]
    request = request_from_payload(payload["request"])
    participants = tuple(
        BlockParticipantProposal(
            participant_plan_id=int(row["participant_plan_id"]),
            mode=row["mode"],
            rationale=row.get("rationale", ""),
        )
        for row in payload.get("participants", [])
    )
    if not participants:
        participants = tuple(
            BlockParticipantProposal(participant_plan_id=value, mode="shared")
            for value in request.participant_plan_ids
        ) + tuple(
            BlockParticipantProposal(participant_plan_id=value, mode="excluded")
            for value in request.excluded_participant_plan_ids
        )
    return BlockGenerationProposal(
        request=request,
        items=tuple(items),
        estimated_duration_seconds=int(payload["estimated_duration_seconds"]),
        estimated_load=BlockLoadEstimate(
            mechanical_impact=_decimal(load["mechanical_impact"]),
            neuromuscular=_decimal(load["neuromuscular"]),
            metabolic=_decimal(load["metabolic"]),
            coordinative=_decimal(load["coordinative"]),
            notes=load.get("notes", ""),
        ),
        coverage=BlockCoverage(
            physical_qualities=tuple(coverage.get("physical_qualities", [])),
            movement_patterns=tuple(coverage.get("movement_patterns", [])),
            body_region_codes=tuple(coverage.get("body_region_codes", [])),
        ),
        participants=participants,
        satisfied_constraints=tuple(payload.get("satisfied_constraints", [])),
        warnings=tuple(payload.get("warnings", [])),
        unmet_constraints=tuple(payload.get("unmet_constraints", [])),
        confidence=_decimal(payload.get("confidence")),
        generator_reference=payload.get("generator_reference", ""),
        contract_version=payload.get("contract_version", "1.0"),
    )
