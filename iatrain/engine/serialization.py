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
    ExerciseKnowledgeSupport,
    IndividualAdjustmentSupport,
    ParticipantConditionDecision,
    ProfessionalKnowledgeClaim,
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


def proposal_payload_from_agent_output(
    *,
    final,
    session_revision_id,
    sequence_index,
    block_role,
    planned_duration_minutes,
    participant_plan_ids,
    excluded_participant_plan_ids,
    available_equipment_ids,
    generator_reference,
    contract_version="3.4",
):
    """Map the public agent schema to the one canonical proposal contract."""

    plan = final["plan"]
    request = {
        "session_revision_id": session_revision_id,
        "sequence_index": sequence_index,
        "name": plan["name"].strip()[:160],
        "block_role": block_role,
        "planned_duration_minutes": planned_duration_minutes,
        "objective": plan["objective"],
        "participant_plan_ids": list(participant_plan_ids),
        "excluded_participant_plan_ids": list(excluded_participant_plan_ids),
        "execution_mode": plan["execution_mode"],
        "domain": "physical",
        "target_intensity": plan["target_intensity"],
        "available_equipment_ids": list(available_equipment_ids),
        "hard_constraints": list(dict.fromkeys(plan["hard_constraints"])),
        "preferences": list(dict.fromkeys(plan["preferences"])),
        "instructions": plan["instructions"],
        "rounds": plan["rounds"],
        "rest_between_rounds_seconds": plan["rest_between_rounds_seconds"],
        "is_optional": False,
        "contract_version": contract_version,
    }
    return {
        "request": request,
        "items": final["items"],
        "estimated_duration_seconds": final["estimated_duration_seconds"],
        "estimated_load": final["estimated_load"],
        "coverage": final["coverage"],
        "participants": final["participants"],
        "satisfied_constraints": final["satisfied_constraints"],
        "warnings": final["warnings"],
        "unmet_constraints": final["unmet_constraints"],
        "confidence": final["confidence"],
        "generator_reference": generator_reference,
        "planning_summary": final["planning_summary"],
        "premise_effects": final["premise_effects"],
        "search_summary": final["search_summary"],
        "contract_version": contract_version,
    }


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
    support = payload.get("professional_justification")
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
        station_remainder_action=payload.get("station_remainder_action", ""),
        adaptation_notes=payload.get("adaptation_notes", ""),
        professional_justification=(
            IndividualAdjustmentSupport(
                condition_ids=tuple(
                    int(value) for value in support.get("condition_ids", [])
                ),
                profile_factor_codes=tuple(
                    support.get("profile_factor_codes", [])
                ),
                professional_claim_ids=tuple(
                    support.get("professional_claim_ids", [])
                ),
                affected_phase_codes=tuple(
                    support.get("affected_phase_codes", [])
                ),
                biomechanical_relevance=support.get(
                    "biomechanical_relevance", ""
                ),
                adaptation_goal=support.get("adaptation_goal", ""),
                monitoring_criteria=tuple(
                    support.get("monitoring_criteria", [])
                ),
                stop_criteria=tuple(support.get("stop_criteria", [])),
                evidence_status=support.get("evidence_status", "hypothesis"),
            )
            if isinstance(support, dict)
            else None
        ),
    )


def _knowledge_support(payload):
    if payload is None:
        return None
    return ExerciseKnowledgeSupport(
        status=payload.get("status", ""),
        summary=payload.get("summary", ""),
        claims=tuple(
            ProfessionalKnowledgeClaim(
                claim_id=row.get("claim_id", ""),
                exercise_revision_id=int(row["exercise_revision_id"]),
                phase_code=row.get("phase_code", ""),
                claim_type=row.get("claim_type", ""),
                action_code=row.get("action_code", ""),
                muscle_code=row.get("muscle_code", ""),
                basis_type=row.get("basis_type", ""),
                basis_code=row.get("basis_code", ""),
                expected_contraction=row.get(
                    "expected_contraction", "not_applicable"
                ),
                verification_state=row.get("verification_state", ""),
                evidence_codes=tuple(row.get("evidence_codes", [])),
                limitations=tuple(row.get("limitations", [])),
            )
            for row in payload.get("claims", [])
        ),
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
                setup_seconds=int(row.get("setup_seconds", 0)),
                planned_duration_seconds=row.get("planned_duration_seconds"),
                rest_after_seconds=int(row.get("rest_after_seconds", 0)),
                selection_rationale=row.get("selection_rationale", ""),
                knowledge_support=_knowledge_support(row.get("knowledge_support")),
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
            condition_decisions=tuple(
                ParticipantConditionDecision(
                    condition_id=int(decision["condition_id"]),
                    action=decision["action"],
                    rationale=decision.get("rationale", ""),
                    affected_sequence_indices=tuple(
                        int(value)
                        for value in decision.get("affected_sequence_indices", [])
                    ),
                )
                for decision in row.get("condition_decisions", [])
            ),
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
        planning_summary=payload.get("planning_summary", ""),
        premise_effects=tuple(payload.get("premise_effects", [])),
        search_summary=payload.get("search_summary", ""),
        contract_version=payload.get("contract_version", "1.0"),
    )
