"""Reproducible, model-blind evaluation of agentic physical blocks."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict

from django.conf import settings

from iatrain_exercises.models import (
    ExerciseConstraint,
    ExerciseEquipmentRequirement,
    ExerciseObjective,
    ExerciseRevision,
)


BENCHMARK_VERSION = "1.2"

QUALITY_DIMENSIONS = {
    "safety": 0.30,
    "personalization": 0.25,
    "selection_coherence": 0.20,
    "dose_and_timing": 0.15,
    "clarity_and_usability": 0.10,
}

DEFAULT_CASES = (
    {
        "id": "base",
        "title": "Cas base",
        "prompt": (
            "Genera un escalfament de 12 minuts per a tot el grup. Ha de preparar "
            "globalment el cos per continuar l’entrenament, amb intensitat progressiva "
            "i sense generar fatiga innecessària."
        ),
        "duration_minutes": 12,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "return_after_inactivity",
        "title": "Retorn després d’inactivitat",
        "prompt": (
            "El grup torna després de dos mesos d’inactivitat. Genera un bloc físic "
            "de 12 minuts adequat per reprendre l’activitat. Decideix lliurement "
            "l’estructura, el nombre d’exercicis, les sèries i les adaptacions necessàries."
        ),
        "duration_minutes": 12,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "individual_conditions",
        "title": "Personalització i condicions individuals",
        "prompt": (
            "Genera un escalfament de 12 minuts per a aquest grup. Tingues en compte "
            "tota la informació individual disponible. Vull una proposta compartida "
            "quan sigui adequada i alternatives personals quan algun participant no "
            "pugui executar un exercici amb seguretat o utilitat."
        ),
        "duration_minutes": 12,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "autonomous_planning",
        "title": "Llibertat completa de planificació",
        "prompt": (
            "Dissenya el bloc físic que consideris més adequat per preparar aquest grup "
            "per a la sessió. Disposes de 15 minuts. Decideix objectius, exercicis, "
            "ordre, volum, descansos i personalitzacions a partir del context disponible."
        ),
        "duration_minutes": 15,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "low_readiness",
        "title": "Estat anímic i baixa activació",
        "prompt": (
            "Avui el grup arriba cansat, poc concentrat i amb poca motivació. Genera "
            "un bloc inicial de 10 minuts que els prepari físicament i mentalment sense "
            "augmentar excessivament la fatiga. Adapta’l a les necessitats individuals "
            "disponibles."
        ),
        "duration_minutes": 10,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "limited_equipment",
        "title": "Equipament limitat",
        "prompt": (
            "Genera un bloc de preparació física de 12 minuts. Avui només podem "
            "utilitzar el terra i bandes elàstiques. Si una proposta compartida no és "
            "adequada per a tothom, resol les incompatibilitats amb variants individuals."
        ),
        "duration_minutes": 12,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "jump_preparation",
        "title": "Objectiu específic",
        "prompt": (
            "Genera un bloc de 15 minuts orientat a preparar el grup per treballar "
            "salts, recepcions i estabilitat durant la sessió posterior. Tingues en "
            "compte les condicions i limitacions individuals i evita que cap participant "
            "quedi simplement ignorat."
        ),
        "duration_minutes": 15,
        "block_role": "preparation",
        "expected_outcomes": ["proposal"],
    },
    {
        "id": "new_ambiguous_pain",
        "title": "Cas deliberadament ambigu",
        "prompt": (
            "Genera un bloc físic de 12 minuts per a tot el grup. Una participant comenta "
            "que avui nota molèsties noves al genoll, però no tenim més informació. "
            "Continua si pots fer-ho amb seguretat; si falta una decisió imprescindible, "
            "explica exactament què necessites saber."
        ),
        "duration_minutes": 12,
        "block_role": "preparation",
        "expected_outcomes": ["proposal", "clarification"],
    },
)


def selected_cases(case_ids=()):
    requested = set(case_ids or ())
    available = {row["id"]: row for row in DEFAULT_CASES}
    unknown = requested - set(available)
    if unknown:
        raise ValueError(f"Casos desconeguts: {', '.join(sorted(unknown))}")
    return tuple(row for row in DEFAULT_CASES if not requested or row["id"] in requested)


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def build_context_snapshot(context):
    revision = context.revision
    athletes = []
    for row in context.athletes:
        payload = _json_safe(row.payload)
        payload.pop("generated_at", None)
        payload.pop("as_of", None)
        athletes.append(
            {"participant_plan_id": row.participant_plan_id, "payload": payload}
        )
    snapshot = {
        "session_revision": {
            "id": revision.pk,
            "title": revision.title,
            "general_objective": revision.general_objective,
            "planned_duration_minutes": revision.planned_duration_minutes,
            "discipline": revision.session.discipline,
            "scope": revision.session.session_scope,
        },
        "goals": list(
            revision.goals.order_by("id").values(
                "id", "domain", "code", "description", "priority", "source", "rationale"
            )
        ),
        "existing_blocks": list(
            revision.blocks.order_by("sequence_index", "id").values(
                "id", "sequence_index", "name", "block_role", "domain",
                "planned_duration_minutes", "objective"
            )
        ),
        "athletes": athletes,
        "available_equipment_ids": list(context.available_equipment_ids),
        "available_equipment_codes": sorted(context.available_equipment_codes),
        "warnings": list(context.warnings),
    }
    return _json_safe(snapshot)


def context_fingerprint(snapshot):
    canonical = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_catalog_snapshot(owner):
    revisions = ExerciseRevision.objects.filter(
        exercise__catalog__owner=owner
    ).order_by("id")
    revision_rows = list(
        revisions.values(
            "id", "exercise_id", "exercise__name", "exercise__is_active",
            "exercise__catalog_id", "exercise__catalog__is_active", "revision_number",
            "editorial_status", "modality", "execution_type", "difficulty",
            "laterality", "kinetic_chain", "movement_pattern", "requires_equipment",
            "updated_at",
        )
    )
    ids = [row["id"] for row in revision_rows]
    return _json_safe(
        {
            "revisions": revision_rows,
            "objectives": list(
                ExerciseObjective.objects.filter(revision_id__in=ids).order_by("id").values(
                    "id", "revision_id", "objective", "priority", "rationale"
                )
            ),
            "constraints": list(
                ExerciseConstraint.objects.filter(revision_id__in=ids).order_by("id").values(
                    "id", "revision_id", "code", "kind", "severity", "statement",
                    "rationale"
                )
            ),
            "equipment": list(
                ExerciseEquipmentRequirement.objects.filter(
                    revision_id__in=ids
                ).order_by("id").values(
                    "id", "revision_id", "equipment_id", "equipment__code",
                    "requirement", "notes"
                )
            ),
        }
    )


def selected_exercise_evidence(proposal_payload):
    ids = set()
    for item in (proposal_payload or {}).get("items", []):
        dose = item.get("dose") or {}
        if dose.get("exercise_revision_id"):
            ids.add(int(dose["exercise_revision_id"]))
        for alternative in item.get("alternatives", []):
            if alternative.get("exercise_revision_id"):
                ids.add(int(alternative["exercise_revision_id"]))
        for adjustment in item.get("athlete_adjustments", []):
            if adjustment.get("replacement_exercise_revision_id"):
                ids.add(int(adjustment["replacement_exercise_revision_id"]))
    rows = ExerciseRevision.objects.filter(pk__in=ids).select_related(
        "exercise"
    ).prefetch_related("objectives", "constraints", "equipment_requirements__equipment")
    return _json_safe(
        [
            {
                "exercise_revision_id": row.pk,
                "name": row.exercise.name,
                "editorial_status": row.editorial_status,
                "modality": row.modality,
                "execution_type": row.execution_type,
                "difficulty": row.difficulty,
                "laterality": row.laterality,
                "kinetic_chain": row.kinetic_chain,
                "movement_pattern": row.movement_pattern,
                "description": row.description,
                "setup": row.setup,
                "execution": row.execution,
                "coaching_cues": row.coaching_cues,
                "safety_notes": row.safety_notes,
                "objectives": [
                    {
                        "objective": item.objective,
                        "priority": item.priority,
                        "rationale": item.rationale,
                    }
                    for item in row.objectives.all()
                ],
                "constraints": [
                    {
                        "code": item.code,
                        "kind": item.kind,
                        "severity": item.severity,
                        "statement": item.statement,
                        "rationale": item.rationale,
                    }
                    for item in row.constraints.all()
                ],
                "equipment": [
                    {
                        "code": item.equipment.code,
                        "requirement": item.requirement,
                        "notes": item.notes,
                    }
                    for item in row.equipment_requirements.all()
                ],
            }
            for row in rows
        ]
    )


def usage_cost(usage, model, pricing):
    """Return cost from explicit per-million rates; never guesses missing prices."""

    rates = (pricing or {}).get("models", {}).get(model)
    if not rates:
        return None
    input_rate = rates.get("input_per_million")
    output_rate = rates.get("output_per_million")
    if input_rate is None or output_rate is None:
        return None
    input_tokens = int((usage or {}).get("input_tokens", 0) or 0)
    output_tokens = int((usage or {}).get("output_tokens", 0) or 0)
    cached_tokens = min(
        input_tokens, int((usage or {}).get("cached_tokens", 0) or 0)
    )
    cached_rate = rates.get("cached_input_per_million")
    if cached_rate is None:
        cached_rate = input_rate
    amount = (
        (input_tokens - cached_tokens) * float(input_rate)
        + cached_tokens * float(cached_rate)
        + output_tokens * float(output_rate)
    ) / 1_000_000
    return round(amount, 8)


def process_metrics(run):
    trace = list(run.agent_trace or [])
    searched = [
        row for row in trace
        if row.get("tool") in {"search_exercises", "find_compatible_alternatives"}
        and row.get("status") == "ok"
    ]
    candidate_ids = {
        int(value)
        for row in searched
        for value in row.get("exercise_revision_ids", [])
    }
    inspected_ids = {
        int(value)
        for row in trace
        if row.get("tool") == "get_exercise_details" and row.get("status") == "ok"
        for value in row.get("exercise_revision_ids", [])
    }
    attempts = (run.validation_payload or {}).get("attempts", [])
    review_attempts = (run.validation_payload or {}).get("review_attempts", [])
    usage = run.usage_payload or {}
    return {
        "tool_calls": len(trace),
        "agent_rounds_including_review": len(run.response_ids or []),
        "search_calls": len(searched),
        "candidate_matches_sum": sum(
            int(row.get("total_matches", 0) or 0) for row in searched
        ),
        "candidate_matches_max": max(
            (int(row.get("total_matches", 0) or 0) for row in searched), default=0
        ),
        "unique_candidates_returned": len(candidate_ids),
        "unique_candidates_inspected": len(inspected_ids),
        "alternative_search_calls": sum(
            row.get("tool") == "find_compatible_alternatives" for row in searched
        ),
        "timing_calls": sum(
            row.get("tool") == "calculate_block_timing" and row.get("status") == "ok"
            for row in trace
        ),
        "audit_calls": sum(row.get("tool") == "audit_block_draft" for row in trace),
        "server_repairs": sum(not row.get("valid", False) for row in attempts),
        "evidence_rounds": int(
            ((run.validation_payload or {}).get("repair_counts") or {}).get(
                "evidence", 0
            )
        ),
        "review_revisions": sum(
            row.get("verdict") == "revise" for row in review_attempts
        ),
        "review_required": bool(
            (run.validation_payload or {}).get("review_required")
        ),
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
        "cached_tokens": int(usage.get("cached_tokens", 0) or 0),
    }


def _strict_object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def judge_schema():
    scored_dimension = _strict_object(
        {
            "score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
            "rationale": {"type": "string"},
        }
    )
    return _strict_object(
        {
            "outcome_assessment": _strict_object(
                {
                    "appropriate": {"type": "boolean"},
                    "rationale": {"type": "string"},
                }
            ),
            "dimensions": _strict_object(
                {name: scored_dimension for name in QUALITY_DIMENSIONS}
            ),
            "critical_failure": {"type": "boolean"},
            "critical_reasons": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        }
    )


def quality_score(judgement):
    if not judgement:
        return None
    weighted = 0.0
    available_weight = 0.0
    dimensions = judgement.get("dimensions", {})
    for name, weight in QUALITY_DIMENSIONS.items():
        value = (dimensions.get(name) or {}).get("score")
        if value is None:
            continue
        weighted += max(0, min(100, int(value))) * weight
        available_weight += weight
    if not available_weight:
        return None
    score = weighted / available_weight
    if not judgement.get("outcome_assessment", {}).get("appropriate", False):
        score = min(score, 39.0)
    if judgement.get("critical_failure"):
        score = min(score, 39.0)
    return round(score, 2)


def evaluate_run_with_judge(
    *, run, case, context_snapshot, judge_model, reasoning_effort,
    exercise_evidence=None
):
    """Blind single-answer grading; failed transport runs are zero without another API call."""

    if run.status == run.Status.FAILED:
        return {
            "model": judge_model,
            "usage": {},
            "judgement": None,
            "quality_score": 0.0,
            "skipped_reason": "generation_failed",
        }
    from iatrain.engine.agent import _post_responses_api, _response_output_text

    packet = {
        "case": case,
        "session_context": context_snapshot,
        "candidate_response": {
            "status": run.status,
            "proposal": run.proposal_payload,
            "decision": run.decision_payload,
            "interpretation": run.interpretation_payload,
            "planning": run.planning_payload,
            "validation": run.validation_payload,
        },
        "selected_exercise_evidence": (
            exercise_evidence
            if exercise_evidence is not None
            else selected_exercise_evidence(run.proposal_payload)
        ),
    }
    payload = {
        "model": judge_model,
        "instructions": (
            "Ets el jutge cec d'un benchmark de planificació física d'IA Train. "
            "No saps quin model ha generat la resposta i no ho has d'inferir. Avalua "
            "només el cas, el context professional i la resposta. Puntua seguretat i "
            "gestió de restriccions; personalització real; coherència de la selecció; "
            "dosi i temps; claredat per a l'entrenador. Una pregunta és adequada només "
            "si falta una dada realment imprescindible; no penalitzis una aclariment "
            "necessari ni premiïs una proposta insegura per haver continuat. Usa null "
            "només quan una dimensió no es pot aplicar honestament. Marca error crític "
            "davant risc material, participant ignorat, incompatibilitat greu o resposta "
            "que no resol el cas. Dona justificacions breus i verificables, sense cadena "
            "de pensament."
        ),
        "input": [{"role": "user", "content": json.dumps(packet, ensure_ascii=False)}],
        "reasoning": {"effort": reasoning_effort},
        "store": False,
        "max_output_tokens": getattr(
            settings, "OPENAI_TRAINING_BENCHMARK_JUDGE_MAX_OUTPUT_TOKENS", 3000
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "iatrain_block_benchmark_judgement",
                "strict": True,
                "schema": judge_schema(),
            }
        },
    }
    data = _post_responses_api(payload)
    judgement = json.loads(_response_output_text(data))
    return {
        "model": data.get("model") or judge_model,
        "response_id": data.get("id", ""),
        "usage": _json_safe(data.get("usage") or {}),
        "judgement": judgement,
        "quality_score": quality_score(judgement),
        "skipped_reason": "",
    }


def outcome_name(status):
    return {
        "proposed": "proposal",
        "review_required": "proposal",
        "awaiting_decision": "clarification",
    }.get(status, "failure")


def _mean(values):
    rows = [float(value) for value in values if value is not None]
    return round(statistics.fmean(rows), 4) if rows else None


def _stdev(values):
    rows = [float(value) for value in values if value is not None]
    return round(statistics.pstdev(rows), 4) if len(rows) > 1 else (0.0 if rows else None)


def summarize_records(records):
    grouped = defaultdict(list)
    grouped_case = defaultdict(list)
    for row in records:
        grouped[row["model_requested"]].append(row)
        grouped_case[(row["model_requested"], row["case_id"])].append(row)

    def summary(rows):
        evaluable_rows = [row for row in rows if not row.get("judge_error")]
        costs = [row.get("production_cost") for row in rows]
        total_cost = sum(value for value in costs if value is not None)
        priced_runs = sum(value is not None for value in costs)
        hard_passes = sum(bool(row.get("hard_gate_pass")) for row in evaluable_rows)
        quality_rows = [row.get("quality_score") for row in evaluable_rows]
        effective_quality = [value if value is not None else 0.0 for value in quality_rows]
        mean_cost = _mean(costs)
        mean_effective_quality = _mean(effective_quality)
        return {
            "runs": len(rows),
            "evaluable_runs": len(evaluable_rows),
            "evaluation_errors": len(rows) - len(evaluable_rows),
            "proposed": sum(row.get("status") == "proposed" for row in rows),
            "review_required": sum(
                row.get("status") == "review_required" for row in rows
            ),
            "clarifications": sum(
                row.get("status") == "awaiting_decision" for row in rows
            ),
            "failed": sum(row.get("status") == "failed" for row in rows),
            "hard_gate_rate": (
                round(hard_passes / len(evaluable_rows), 4)
                if evaluable_rows else None
            ),
            "quality_mean": _mean(quality_rows),
            "quality_effective_mean": mean_effective_quality,
            "quality_stdev": _stdev(quality_rows),
            "latency_seconds_mean": _mean(row.get("elapsed_seconds") for row in rows),
            "tool_calls_mean": _mean(row["process"].get("tool_calls") for row in rows),
            "repairs_mean": _mean(row["process"].get("server_repairs") for row in rows),
            "review_revisions_mean": _mean(
                row["process"].get("review_revisions") for row in rows
            ),
            "tokens_mean": _mean(row["process"].get("total_tokens") for row in rows),
            "production_cost_mean": mean_cost,
            "production_cost_total": round(total_cost, 8) if priced_runs else None,
            "cost_per_hard_pass": (
                round(total_cost / hard_passes, 8)
                if priced_runs == len(rows) and hard_passes else None
            ),
            "value_points_per_cent": (
                round(mean_effective_quality * 0.01 / mean_cost, 4)
                if mean_cost and mean_effective_quality is not None else None
            ),
            "benchmark_judge_cost_total": (
                round(sum(row.get("judge_cost") or 0 for row in rows), 8)
                if all(row.get("judge_cost") is not None for row in rows) else None
            ),
        }

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "by_model": {model: summary(rows) for model, rows in sorted(grouped.items())},
        "by_model_case": {
            f"{model}::{case_id}": summary(rows)
            for (model, case_id), rows in sorted(grouped_case.items())
        },
    }
