"""Agentic OpenAI boundary for complete physical block planning."""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

from iatrain.models import (
    PhysicalExercisePrescription,
    SessionItemAlternative,
    TrainingBlock,
    TrainingSessionItem,
)
from iatrain_exercises.models import (
    ExerciseEquipmentRequirement,
    ExerciseObjective,
    ExerciseRevision,
)

from .agent_tools import AgentToolExecutor, TOOL_VERSION, tool_definitions
from .contracts import PHYSICAL_BLOCK_HARD_CONSTRAINTS, TARGET_INTENSITIES
from .openai import (
    InterpretationNeedsClarification,
    OpenAITrainingNotConfigured,
    OpenAITrainingUnavailable,
    _response_output_text,
)
from .serialization import (
    contract_to_payload,
    proposal_from_payload,
    proposal_payload_from_agent_output,
)
from .scoring import PATTERN_REGIONS, condition_applies
from .validation import referenced_exercise_revision_ids, validate_block_generation_proposal


AGENT_PROMPT_VERSION = "physical-block-agent-3.3"
AGENT_ENGINE_VERSION = "physical-block-agent-engine-3.3"


@dataclass(frozen=True, slots=True)
class AgentBlockResult:
    proposal: object
    interpretation_payload: dict
    model_name: str
    tool_trace: tuple[dict, ...]
    response_ids: tuple[str, ...]
    usage_payload: dict
    validation_payload: dict


class AgentNeedsCoachDecision(Exception):
    code = "agent_needs_coach_decision"

    def __init__(self, message, *, issues):
        super().__init__(message)
        self.issues = tuple(issues)
        self.agent_trace = ()
        self.response_ids = ()
        self.usage_payload = {}
        self.validation_payload = {}
        self.model_name = ""


def _array(items):
    return {"type": "array", "items": items}


def _nullable(type_name, **extra):
    return {"type": [type_name, "null"], **extra}


def _strict_object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _proposal_schema():
    objective = _strict_object(
        {
            "description": {"type": "string"},
            "primary_quality": {
                "type": "string",
                "enum": list(ExerciseObjective.Objective.values),
            },
            "secondary_qualities": _array(
                {"type": "string", "enum": list(ExerciseObjective.Objective.values)}
            ),
            "movement_patterns": _array(
                {"type": "string", "enum": list(ExerciseRevision.MovementPattern.values)}
            ),
            "body_region_codes": _array({"type": "string"}),
        }
    )
    plan = _strict_object(
        {
            "name": {"type": "string"},
            "execution_mode": {
                "type": "string",
                "enum": list(TrainingBlock.ExecutionMode.values),
            },
            "objective": objective,
            "target_intensity": {"type": "string", "enum": list(TARGET_INTENSITIES)},
            "hard_constraints": _array(
                {"type": "string", "enum": list(PHYSICAL_BLOCK_HARD_CONSTRAINTS)}
            ),
            "preferences": _array({"type": "string"}),
            "instructions": {"type": "string"},
            "rounds": {"type": "integer", "minimum": 1, "maximum": 20},
            "rest_between_rounds_seconds": {
                "type": "integer",
                "minimum": 0,
                "maximum": 900,
            },
        }
    )
    dose = _strict_object(
        {
            "exercise_revision_id": {"type": "integer"},
            "dose_mode": {
                "type": "string",
                "enum": list(PhysicalExercisePrescription.DoseMode.values),
            },
            "sets": {"type": "integer", "minimum": 1, "maximum": 20},
            "repetitions": _nullable("integer"),
            "duration_seconds": _nullable("integer"),
            "distance": _nullable("number"),
            "distance_unit": {
                "type": "string",
                "enum": ["", *PhysicalExercisePrescription.DistanceUnit.values],
            },
            "load_value": _nullable("number"),
            "load_unit": {
                "type": "string",
                "enum": ["", *PhysicalExercisePrescription.LoadUnit.values],
            },
            "intensity_metric": {
                "type": "string",
                "enum": list(PhysicalExercisePrescription.IntensityMetric.values),
            },
            "intensity_value": _nullable("number"),
            "tempo_eccentric_seconds": _nullable("integer"),
            "tempo_pause_seconds": _nullable("integer"),
            "tempo_concentric_seconds": _nullable("integer"),
            "concentric_intent": {
                "type": "string",
                "enum": list(PhysicalExercisePrescription.ConcentricIntent.values),
            },
            "rest_between_sets_seconds": {
                "type": "integer",
                "minimum": 0,
                "maximum": 900,
            },
            "execution_notes": {"type": "string"},
        }
    )
    alternative = _strict_object(
        {
            "exercise_revision_id": {"type": "integer"},
            "trigger": {
                "type": "string",
                "enum": list(SessionItemAlternative.Trigger.values),
            },
            "rationale": {"type": "string"},
            "priority": {"type": "integer", "minimum": 1},
        }
    )
    adjustment = _strict_object(
        {
            "participant_plan_id": {"type": "integer"},
            "rationale": {"type": "string"},
            "action": {"type": "string", "enum": ["modify", "replace", "skip"]},
            "replacement_exercise_revision_id": _nullable("integer"),
            "sets": _nullable("integer"),
            "repetitions": _nullable("integer"),
            "duration_seconds": _nullable("integer"),
            "load_value": _nullable("number"),
            "load_unit": {
                "type": "string",
                "enum": ["", *PhysicalExercisePrescription.LoadUnit.values],
            },
            "intensity_metric": {
                "type": "string",
                "enum": ["", *PhysicalExercisePrescription.IntensityMetric.values],
            },
            "intensity_value": _nullable("number"),
            "rest_between_sets_seconds": _nullable("integer"),
            "adaptation_notes": {"type": "string"},
        }
    )
    item = _strict_object(
        {
            "sequence_index": {"type": "integer", "minimum": 1},
            "item_type": {
                "type": "string",
                "enum": [TrainingSessionItem.ItemType.PHYSICAL_EXERCISE],
            },
            "title": {"type": "string"},
            "instructions": {"type": "string"},
            "coaching_cues": {"type": "string"},
            "setup_seconds": {"type": "integer", "minimum": 0, "maximum": 900},
            "planned_duration_seconds": {"type": "integer", "minimum": 1},
            "rest_after_seconds": {"type": "integer", "minimum": 0},
            "selection_rationale": {"type": "string"},
            "is_optional": {"type": "boolean"},
            "dose": dose,
            "alternatives": _array(alternative),
            "athlete_adjustments": _array(adjustment),
        }
    )
    condition_decision = _strict_object(
        {
            "condition_id": {"type": "integer"},
            "action": {
                "type": "string",
                "enum": ["not_applicable", "monitor", "modify", "replace", "skip"],
            },
            "rationale": {"type": "string"},
            "affected_sequence_indices": _array(
                {"type": "integer", "minimum": 1}
            ),
        }
    )
    participant = _strict_object(
        {
            "participant_plan_id": {"type": "integer"},
            "mode": {"type": "string", "enum": ["shared", "personalized", "excluded"]},
            "rationale": {"type": "string"},
            "condition_decisions": _array(condition_decision),
        }
    )
    load = _strict_object(
        {
            "mechanical_impact": {"type": "number", "minimum": 0, "maximum": 5},
            "neuromuscular": {"type": "number", "minimum": 0, "maximum": 5},
            "metabolic": {"type": "number", "minimum": 0, "maximum": 5},
            "coordinative": {"type": "number", "minimum": 0, "maximum": 5},
            "notes": {"type": "string"},
        }
    )
    coverage = _strict_object(
        {
            "physical_qualities": _array(
                {"type": "string", "enum": list(ExerciseObjective.Objective.values)}
            ),
            "movement_patterns": _array(
                {"type": "string", "enum": list(ExerciseRevision.MovementPattern.values)}
            ),
            "body_region_codes": _array({"type": "string"}),
        }
    )
    return _strict_object(
        {
            "intent_status": {
                "type": "string",
                "enum": ["ready", "needs_clarification"],
            },
            "clarification_question": {"type": "string"},
            "planning_summary": {"type": "string"},
            "premise_effects": _array({"type": "string"}),
            "search_summary": {"type": "string"},
            "plan": plan,
            "items": _array(item),
            "participants": _array(participant),
            "estimated_duration_seconds": {"type": "integer", "minimum": 1},
            "estimated_load": load,
            "coverage": coverage,
            "satisfied_constraints": _array(
                {"type": "string", "enum": list(PHYSICAL_BLOCK_HARD_CONSTRAINTS)}
            ),
            "warnings": _array({"type": "string"}),
            "unmet_constraints": _array({"type": "string"}),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        }
    )


def _instructions():
    return f"""
Ets el motor agentiu de planificació física d'IA Train. Tu prens les decisions
professionals del bloc: interpretes les premisses, decideixes quants exercicis calen,
explores el catàleg, compares candidats, tries exercicis i variants, decideixes la
seqüència, les sèries, repeticions, descansos i personalitzacions, i ajustes el pla al temps.

Has d'usar search_exercises abans de seleccionar res. Pots fer tantes cerques diferents
com necessitis, paginar i ampliar o relaxar filtres si hi ha pocs candidats. Consulta els
detalls, la compatibilitat i les guies dels finalistes. Abans d'entregar, crida
calculate_block_timing amb la dosificació exacta final. Pots usar audit_block_draft com a
màxim dues vegades; després entrega la proposta perquè el servidor faci la validació final.
No inventis mai identificadors: només pots usar revisions retornades per search_exercises.

Relaxa les cerques progressivament, una dimensió cada vegada. Si no hi ha candidats
validats, no passis silenciosament a esborranys: explora primer el catàleg i, si els
esborranys són imprescindibles, el servidor demanarà autorització a l'entrenador.
Si coach_decisions conté catalog_drafts=allow_draft_exercises, l'autorització ja ha estat
concedida: les eines ampliaran automàticament les cerques a esborranys i no l'has de tornar
a demanar.

La base pot ser compartida, però no la forcis. Si un exercici compartit no és adequat per
una gimnasta, busca una substitució, modifica la dosi o marca skip només per aquell ítem.
Abans de qualsevol skip has de cridar find_compatible_alternatives per aquella participant.
No entreguis mai un bloc on una participant activa ometi tots els exercicis. Si després de
buscar no hi ha cap sortida real, demana una aclariment en lloc de dissimular el bloqueig.
Explica breument l'efecte de premisses com inactivitat, estat anímic, càrrega recent,
experiència o incertesa. No diagnostiquis ni prescriguis tractament. Una condició stop ja
ha estat resolta pel servidor; avoid, modify i monitor s'han de respectar explícitament.

Les guies són envolupants, no receptes deterministes: decideix dins d'elles o justifica
qualsevol desviació prudent. estimated_duration_seconds ha de coincidir exactament amb
l'últim calculate_block_timing i no superar el pressupost. Tots els participants actius
i exclosos s'han d'incloure una sola vegada. Una participant personalized ha de tenir
almenys un athlete_adjustment real, i qualsevol participant amb ajustament ha de ser
personalized. No escriguis indicacions individuals dins instructions, coaching_cues o
execution_notes compartides: posa-les sempre a athlete_adjustments.

Per a cada condició activa avoid o modify, crea una condition_decision. Si no afecta cap
ítem, usa not_applicable i justifica-ho; modify, replace o skip han de correspondre amb
athlete_adjustments als sequence_index indicats. Cada exercici seleccionat, incloses
alternatives i substitucions, necessita detalls, compatibilitat i guia consultats. Copia
setup_seconds i planned_duration_seconds de l'últim calculate_block_timing perquè el temps
visible i el calculat siguin idèntics. unmet_constraints ha de quedar buit.

No tens cerca web en aquesta fase. No inventis bibliografia. planning_summary és una
justificació visible i concisa, no una cadena de pensament. Escriu en català.
Contracte: 3.1. Eines: {TOOL_VERSION}.
""".strip()


def _athlete_payload(context, active_ids, excluded_ids):
    rows = []
    active = set(active_ids)
    excluded = set(excluded_ids)
    for athlete in context.athletes:
        payload = athlete.payload
        rows.append(
            {
                "participant_plan_id": athlete.participant_plan_id,
                "participation_state": (
                    "active" if athlete.participant_plan_id in active else "excluded"
                ),
                "age_years": payload.get("athlete", {}).get("age_years"),
                "population_stage": athlete.prescription_profile.population_stage,
                "experience_level": athlete.prescription_profile.experience_level,
                "training_years": (
                    str(athlete.prescription_profile.training_years)
                    if athlete.prescription_profile.training_years is not None
                    else None
                ),
                "sport_profiles": payload.get("sport_profiles", []),
                "active_conditions": [
                    {
                        key: condition.get(key)
                        for key in (
                            "id",
                            "title",
                            "narrative",
                            "body_region",
                            "applicability_scope",
                            "training_impact",
                            "severity",
                            "laterality",
                            "coach_scope_decision",
                        )
                    }
                    for condition in payload.get("active_conditions", [])
                ],
                "confirmed_insights": payload.get("confirmed_insights", []),
                "current_observations": payload.get("current_observations", [])[:8],
                "recent_training_responses": payload.get("recent_training_responses", [])[:12],
                "health_data_available": payload.get("scope", {}).get(
                    "health_data_available", False
                ),
                "excluded_by_coach": athlete.participant_plan_id in excluded,
            }
        )
    return rows


def _initial_payload(
    *, context, prompt, duration_minutes, block_role, active_ids, excluded_ids,
    previous_proposal=None, refinement="", coach_decisions=None
):
    revision = context.revision
    remaining = revision.planned_duration_minutes - sum(
        revision.blocks.values_list("planned_duration_minutes", flat=True)
    )
    payload = {
        "session": {
            "revision_id": revision.pk,
            "discipline": revision.session.discipline,
            "planned_duration_minutes": revision.planned_duration_minutes,
            "remaining_duration_minutes": remaining,
            "general_objective": revision.general_objective,
            "goals": [
                {"domain": row.domain, "description": row.description, "priority": row.priority}
                for row in revision.goals.all()
            ],
            "existing_blocks": [
                {
                    "name": row.name,
                    "role": row.block_role,
                    "objective": row.objective,
                    "duration_minutes": row.planned_duration_minutes,
                }
                for row in revision.blocks.all()
            ],
        },
        "server_authority": {
            "block_role": block_role,
            "planned_duration_minutes": duration_minutes,
            "available_equipment_codes": sorted(context.available_equipment_codes),
            "active_participant_plan_ids": list(active_ids),
            "excluded_participant_plan_ids": list(excluded_ids),
        },
        "athletes": _athlete_payload(context, active_ids, excluded_ids),
        "context_warnings": list(context.warnings),
        "coach_decisions": dict(coach_decisions or {}),
        "coach_prompt": prompt,
    }
    if previous_proposal:
        payload["previous_proposal"] = previous_proposal
        payload["refinement_instruction"] = refinement
    return payload


def _post_responses_api(payload):
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise OpenAITrainingNotConfigured(
            "Configura OPENAI_API_KEY per activar la generació automàtica."
        )
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=getattr(settings, "OPENAI_TRAINING_TIMEOUT_SECONDS", 120),
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="ignore"))
            message = detail.get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        raise OpenAITrainingUnavailable(
            "OpenAI no ha pogut completar la planificació"
            + (f": {message[:240]}" if message else ".")
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OpenAITrainingUnavailable(
            "No s'ha pogut contactar amb OpenAI per completar la planificació."
        ) from exc


def _usage_total(total, usage):
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        total[key] = total.get(key, 0) + int((usage or {}).get(key, 0) or 0)
    details = (usage or {}).get("input_tokens_details", {}) or {}
    total["cached_tokens"] = total.get("cached_tokens", 0) + int(
        details.get("cached_tokens", 0) or 0
    )
    return total


def _review_schema():
    issue = _strict_object(
        {
            "code": {"type": "string"},
            "severity": {"type": "string", "enum": ["error", "warning"]},
            "message": {"type": "string"},
            "correction": {"type": "string"},
        }
    )
    return _strict_object(
        {
            "verdict": {
                "type": "string",
                "enum": ["pass", "revise", "needs_clarification"],
            },
            "summary": {"type": "string"},
            "issues": _array(issue),
            "clarification_question": {"type": "string"},
        }
    )


def _review_packet(*, proposal, context, executor, active_ids, excluded_ids):
    exercise_ids = referenced_exercise_revision_ids(proposal)
    revisions = ExerciseRevision.objects.filter(pk__in=exercise_ids).select_related(
        "exercise"
    ).prefetch_related("objectives", "constraints")
    exercises = [
        {
            "exercise_revision_id": row.pk,
            "name": row.exercise.name,
            "editorial_status": row.editorial_status,
            "modality": row.modality,
            "difficulty": row.difficulty,
            "movement_pattern": row.movement_pattern,
            "laterality": row.laterality,
            "description": row.description,
            "safety_notes": row.safety_notes,
            "objectives": [item.objective for item in row.objectives.all()],
            "constraints": [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "statement": item.statement,
                }
                for item in row.constraints.all()
            ],
        }
        for row in revisions
    ]
    athletes = [
        row
        for row in _athlete_payload(context, active_ids, excluded_ids)
        if row["participation_state"] == "active"
    ]
    return {
        "proposal": contract_to_payload(proposal),
        "active_athletes": athletes,
        "selected_exercises": exercises,
        "evidence": {
            "detail_exercise_ids": sorted(executor.detail_exercise_ids),
            "guidance_pairs": sorted([list(value) for value in executor.guidance_pairs]),
            "compatibility_pairs": sorted(
                [list(value) for value in executor.compatibility_pairs]
            ),
            "timing": executor.last_timing,
        },
    }


def _request_independent_review(*, proposal, context, executor, active_ids, excluded_ids):
    model = getattr(
        settings,
        "OPENAI_TRAINING_REVIEW_MODEL",
        getattr(settings, "OPENAI_TRAINING_MODEL", "gpt-5.6-luna"),
    )
    payload = {
        "model": model,
        "instructions": (
            "Ets el revisor independent d'una proposta física d'IA Train. No planifiques "
            "de nou ni inventes exercicis. Avalua críticament només l'evidència rebuda: "
            "coherència amb la petició, cobertura real, nivell i inactivitat, dosificació, "
            "seguretat, condicions individuals, alternatives i correspondència entre "
            "justificacions i ajustaments estructurats. Marca revise davant qualsevol "
            "error material i dona correccions concretes. Usa needs_clarification només "
            "si falta una dada imprescindible o no hi ha cap sortida viable; no ho usis "
            "per preferències. Un warning no bloqueja per si sol. Respon en català amb "
            "observacions breus i auditables, sense cadena de pensament."
        ),
        "input": [
            {
                "role": "user",
                "content": json.dumps(
                    _review_packet(
                        proposal=proposal,
                        context=context,
                        executor=executor,
                        active_ids=active_ids,
                        excluded_ids=excluded_ids,
                    ),
                    ensure_ascii=False,
                    default=str,
                ),
            }
        ],
        "reasoning": {
            "effort": getattr(
                settings, "OPENAI_TRAINING_REVIEW_REASONING_EFFORT", "medium"
            )
        },
        "store": False,
        "max_output_tokens": getattr(
            settings, "OPENAI_TRAINING_REVIEW_MAX_OUTPUT_TOKENS", 3500
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "iatrain_independent_block_review",
                "strict": True,
                "schema": _review_schema(),
            }
        },
    }
    data = _post_responses_api(payload)
    text = _response_output_text(data)
    try:
        review = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise OpenAITrainingUnavailable(
            "El revisor independent no ha retornat un veredicte vàlid."
        ) from error
    return data, review


def _server_proposal_payload(
    *, final, context, duration_minutes, block_role, active_ids, excluded_ids
):
    revision = context.revision
    sequence_index = (
        max(revision.blocks.values_list("sequence_index", flat=True), default=0) + 1
    )
    return proposal_payload_from_agent_output(
        final=final,
        session_revision_id=revision.pk,
        sequence_index=sequence_index,
        block_role=block_role,
        planned_duration_minutes=duration_minutes,
        participant_plan_ids=active_ids,
        excluded_participant_plan_ids=excluded_ids,
        available_equipment_ids=context.available_equipment_ids,
        generator_reference=f"{AGENT_ENGINE_VERSION} · {TOOL_VERSION}",
    )


def _validation_messages(error):
    if hasattr(error, "message_dict"):
        return [
            f"{field}: {message}"
            for field, messages in error.message_dict.items()
            for message in messages
        ]
    return list(getattr(error, "messages", None) or [str(error)])


def _validate_agent_context_invariants(*, proposal, context):
    """Check factual safety/logistics without selecting or dosing for the model."""

    identifiers = referenced_exercise_revision_ids(proposal)
    revisions = {
        row.pk: row
        for row in ExerciseRevision.objects.filter(pk__in=identifiers).prefetch_related(
            "equipment_requirements__equipment"
        )
    }
    hard = set(proposal.request.hard_constraints)
    errors = []
    for revision in revisions.values():
        required = {
            row.equipment.code
            for row in revision.equipment_requirements.all()
            if row.requirement == ExerciseEquipmentRequirement.Requirement.REQUIRED
        }
        if not required.issubset(context.available_equipment_codes):
            errors.append(
                f"L'exercici {revision.pk} requereix material no disponible: "
                f"{sorted(required - context.available_equipment_codes)}."
            )
        if "validated_only" in hard and revision.editorial_status != "validated":
            errors.append(f"L'exercici {revision.pk} no està validat editorialment.")
        if {"bodyweight_only", "no_equipment"} & hard and (
            required or revision.requires_equipment
        ):
            errors.append(f"L'exercici {revision.pk} necessita material.")
        name_code = f"{revision.exercise.code} {revision.exercise.name}".casefold()
        jump = any(token in name_code for token in ("jump", "salt", "pogo"))
        if "no_jumps" in hard and jump:
            errors.append(f"L'exercici {revision.pk} incompleix no_jumps.")
        if {"no_impact", "avoid_high_impact"} & hard and (
            revision.modality == ExerciseRevision.Modality.POWER or jump
        ):
            errors.append(f"L'exercici {revision.pk} incompleix la restricció d'impacte.")

    athletes = {
        row.participant_plan_id: row
        for row in context.athletes
        if row.participant_plan_id in proposal.request.participant_plan_ids
    }
    participant_rows = {
        row.participant_plan_id: row for row in proposal.participants
    }
    item_adjustments = {
        item.sequence_index: {
            row.participant_plan_id: row for row in item.athlete_adjustments
        }
        for item in proposal.items
    }
    if proposal.contract_version == "3.1":
        for participant_id, athlete in athletes.items():
            participant = participant_rows.get(participant_id)
            if participant is None:
                continue
            active_conditions = {
                int(condition["id"]): condition
                for condition in athlete.payload.get("active_conditions", [])
                if condition.get("id")
                and condition.get("training_impact") in {"avoid", "modify"}
            }
            decisions = {
                decision.condition_id: decision
                for decision in participant.condition_decisions
            }
            missing = set(active_conditions) - set(decisions)
            if missing:
                errors.append(
                    f"El participant {participant_id} necessita una decisió estructurada "
                    f"per a les condicions {sorted(missing)}."
                )
            unknown = set(decisions) - set(active_conditions)
            if unknown:
                errors.append(
                    f"El participant {participant_id} respon condicions no actives: "
                    f"{sorted(unknown)}."
                )
            for condition_id, decision in decisions.items():
                condition = active_conditions.get(condition_id)
                if condition is None:
                    continue
                impact = condition.get("training_impact")
                allowed_actions = (
                    {"not_applicable", "replace", "skip"}
                    if impact == "avoid"
                    else {"not_applicable", "modify", "replace", "skip"}
                )
                if decision.action not in allowed_actions:
                    errors.append(
                        f"La resposta {decision.action} no resol la condició "
                        f"{condition_id} ({impact})."
                    )
                if decision.action == "not_applicable":
                    if decision.affected_sequence_indices:
                        errors.append(
                            f"La condició {condition_id} marcada no aplicable no pot "
                            "assenyalar ítems afectats."
                        )
                    continue
                if not decision.affected_sequence_indices:
                    errors.append(
                        f"La decisió de la condició {condition_id} ha d'indicar els ítems afectats."
                    )
                for sequence_index in decision.affected_sequence_indices:
                    adjustment = item_adjustments.get(sequence_index, {}).get(
                        participant_id
                    )
                    if adjustment is None or adjustment.action != decision.action:
                        errors.append(
                            f"La condició {condition_id} declara {decision.action} a l'ítem "
                            f"{sequence_index}, però no hi ha l'athlete_adjustment corresponent."
                        )
    for item in proposal.items:
        if item.dose is None:
            continue
        base = revisions.get(item.dose.exercise_revision_id)
        if base is None:
            continue
        adjustments = {row.participant_plan_id: row for row in item.athlete_adjustments}
        base_regions = PATTERN_REGIONS.get(base.movement_pattern, set())
        for participant_id, athlete in athletes.items():
            impacts = {
                condition.get("training_impact")
                for condition in athlete.payload.get("active_conditions", [])
                if condition_applies(condition, base_regions)
            }
            adjustment = adjustments.get(participant_id)
            if "stop" in impacts:
                errors.append(
                    f"El participant {participant_id} conserva una indicació stop activa."
                )
            if "avoid" in impacts and (
                adjustment is None or adjustment.action not in {"replace", "skip"}
            ):
                errors.append(
                    f"El participant {participant_id} necessita substituir o ometre "
                    f"l'exercici {base.pk}."
                )
            if "modify" in impacts and adjustment is None:
                errors.append(
                    f"El participant {participant_id} necessita una adaptació explícita "
                    f"per a l'exercici {base.pk}."
                )
            if adjustment and adjustment.action == "replace":
                replacement = revisions.get(adjustment.replacement_exercise_revision_id)
                if replacement is None:
                    continue
                replacement_regions = PATTERN_REGIONS.get(
                    replacement.movement_pattern, set()
                )
                incompatible = [
                    condition
                    for condition in athlete.payload.get("active_conditions", [])
                    if condition.get("training_impact") in {"stop", "avoid"}
                    and condition_applies(condition, replacement_regions)
                ]
                if incompatible:
                    errors.append(
                        f"La substitució {replacement.pk} continua sent incompatible amb "
                        f"el participant {participant_id}."
                    )
    if errors:
        raise ValidationError(errors)


def _participants_without_exposure(proposal):
    physical_items = [item for item in proposal.items if item.dose is not None]
    if not physical_items:
        return set(proposal.request.participant_plan_ids)
    missing = set()
    for participant_id in proposal.request.participant_plan_ids:
        skips = 0
        for item in physical_items:
            adjustment = next(
                (
                    row
                    for row in item.athlete_adjustments
                    if row.participant_plan_id == participant_id
                ),
                None,
            )
            if adjustment and adjustment.action == "skip":
                skips += 1
        if skips == len(physical_items):
            missing.add(participant_id)
    return missing


def _participants_with_skips(proposal):
    return {
        adjustment.participant_plan_id
        for item in proposal.items
        for adjustment in item.athlete_adjustments
        if adjustment.action == "skip"
    }


def _required_tool_evidence(proposal):
    active_ids = set(proposal.request.participant_plan_ids)
    detail_ids = set()
    participant_pairs = set()
    for item in proposal.items:
        if item.dose is None:
            continue
        base_id = item.dose.exercise_revision_id
        detail_ids.add(base_id)
        participant_pairs.update((base_id, value) for value in active_ids)
        for alternative in item.alternatives:
            detail_ids.add(alternative.exercise_revision_id)
            participant_pairs.update(
                (alternative.exercise_revision_id, value) for value in active_ids
            )
        for adjustment in item.athlete_adjustments:
            if adjustment.replacement_exercise_revision_id:
                replacement_id = adjustment.replacement_exercise_revision_id
                detail_ids.add(replacement_id)
                participant_pairs.add(
                    (replacement_id, adjustment.participant_plan_id)
                )
    return detail_ids, participant_pairs


def _validate_timing_evidence(*, proposal, executor):
    errors = []
    arguments = executor.last_timing_arguments or {}
    timing = executor.last_timing or {}
    physical_items = [item for item in proposal.items if item.dose is not None]
    argument_items = arguments.get("items", [])
    details = timing.get("details", [])
    if arguments.get("execution_mode") != proposal.request.execution_mode:
        errors.append("El mode d'execució no coincideix amb l'últim càlcul temporal.")
    if arguments.get("rounds") != proposal.request.rounds:
        errors.append("Les rondes no coincideixen amb l'últim càlcul temporal.")
    if (
        arguments.get("rest_between_rounds_seconds")
        != proposal.request.rest_between_rounds_seconds
    ):
        errors.append("El descans entre rondes no coincideix amb el càlcul temporal.")
    if not (
        len(physical_items) == len(argument_items) == len(details)
    ):
        errors.append("Els ítems finals no coincideixen amb l'últim càlcul temporal.")
        return errors
    for item, timed_item, detail in zip(physical_items, argument_items, details):
        dose = item.dose
        expected = {
            "exercise_revision_id": dose.exercise_revision_id,
            "sets": dose.sets,
            "repetitions": dose.repetitions,
            "duration_seconds": dose.duration_seconds,
            "rest_between_sets_seconds": dose.rest_between_sets_seconds,
            "rest_after_seconds": item.rest_after_seconds,
        }
        if any(timed_item.get(key) != value for key, value in expected.items()):
            errors.append(
                f"La dosi de l'ítem {item.sequence_index} no coincideix amb "
                "l'últim càlcul temporal."
            )
        if item.setup_seconds != detail.get("setup_seconds"):
            errors.append(
                f"La preparació visible de l'ítem {item.sequence_index} no coincideix "
                "amb el càlcul temporal."
            )
        if item.planned_duration_seconds != detail.get("single_round_seconds"):
            errors.append(
                f"La durada visible de l'ítem {item.sequence_index} no coincideix "
                "amb el càlcul temporal."
            )
    return errors


def _draft_permission_issues(*, draft_count=0, draft_ids=()):
    identifiers = sorted({int(value) for value in draft_ids})
    if identifiers:
        detail = f"Les revisions {identifiers} encara no estan validades."
    elif draft_count:
        detail = (
            f"El catàleg conté {int(draft_count)} revisions en esborrany, però cap "
            "revisió validada disponible per iniciar la cerca."
        )
    else:
        detail = "La cerca només ha trobat revisions pendents de validació editorial."
    return [
        {
            "decision_key": "catalog_drafts",
            "reason_code": "draft_exercises_required",
            "title": "Cal autoritzar els exercicis en esborrany",
            "explanation": (
                detail
                + " L'autorització és només per a aquesta proposta i quedarà registrada."
            ),
            "choices": [
                {
                    "value": "allow_draft_exercises",
                    "label": "Permetre cercar i utilitzar esborranys",
                }
            ],
            "profile_review_available": False,
        }
    ]


def plan_block_with_agent(
    *, context, prompt, duration_minutes, block_role, active_participant_ids,
    excluded_participant_ids=(), previous_proposal=None, refinement="",
    coach_decisions=None, progress_callback=None
):
    """Run the stateless tool loop and return one server-valid proposal."""

    remaining = context.revision.planned_duration_minutes - sum(
        context.revision.blocks.values_list("planned_duration_minutes", flat=True)
    )
    duration = min(int(duration_minutes), int(remaining))
    if duration < 1:
        raise ValidationError("La sessió no té temps disponible per a un altre bloc.")
    active_ids = tuple(int(value) for value in active_participant_ids)
    excluded_ids = tuple(int(value) for value in excluded_participant_ids)
    decisions = dict(coach_decisions or {})
    request_hint = {
        "planned_duration_minutes": duration,
        "block_role": block_role,
        "active_participant_plan_ids": list(active_ids),
        "excluded_participant_plan_ids": list(excluded_ids),
    }
    executor = AgentToolExecutor(
        context=context,
        request_hint=request_hint,
        max_results=getattr(settings, "OPENAI_TRAINING_MAX_RESULTS_PER_SEARCH", 20),
        max_unique_candidates=getattr(
            settings, "OPENAI_TRAINING_MAX_UNIQUE_CANDIDATES", 100
        ),
        allow_drafts=(
            decisions.get("catalog_drafts") == "allow_draft_exercises"
        ),
    )
    initial = _initial_payload(
        context=context,
        prompt=prompt,
        duration_minutes=duration,
        block_role=block_role,
        active_ids=active_ids,
        excluded_ids=excluded_ids,
        previous_proposal=previous_proposal,
        refinement=refinement,
        coach_decisions=decisions,
    )
    history = [
        {
            "role": "user",
            "content": json.dumps(initial, ensure_ascii=False, default=str),
        }
    ]
    model = getattr(settings, "OPENAI_TRAINING_MODEL", "gpt-5.6-luna")
    max_rounds = max(2, getattr(settings, "OPENAI_TRAINING_MAX_TOOL_ROUNDS", 20))
    max_calls = max(1, getattr(settings, "OPENAI_TRAINING_MAX_TOOL_CALLS", 50))
    max_repairs = max(0, getattr(settings, "OPENAI_TRAINING_MAX_REPAIRS", 2))
    call_count = 0
    repairs = 0
    response_ids = []
    usage = {}
    validation_payload = {"attempts": []}
    actual_model = model

    def emit(stage, message, **extra):
        if progress_callback is None:
            return
        progress_callback(
            {
                "stage": stage,
                "message": message,
                "tool_calls": call_count,
                "round": len(response_ids),
                "trace": list(executor.trace),
                "response_ids": list(response_ids),
                "usage_payload": dict(usage),
                **extra,
            }
        )

    def runtime_error(message):
        error = OpenAITrainingUnavailable(message)
        error.agent_trace = list(executor.trace)
        error.response_ids = list(response_ids)
        error.usage_payload = dict(usage)
        error.validation_payload = dict(validation_payload)
        error.model_name = actual_model
        return error

    def decision_error(message, issues):
        error = AgentNeedsCoachDecision(message, issues=issues)
        error.agent_trace = tuple(executor.trace)
        error.response_ids = tuple(response_ids)
        error.usage_payload = dict(usage)
        error.validation_payload = dict(validation_payload)
        error.model_name = actual_model
        return error

    editorial_availability = executor.editorial_availability()
    if (
        not executor.allow_drafts
        and editorial_availability["validated"] == 0
        and editorial_availability["draft"] > 0
    ):
        raise decision_error(
            "El catàleg no té exercicis validats; cal una autorització abans de continuar.",
            _draft_permission_issues(
                draft_count=editorial_availability["draft"]
            ),
        )

    emit("analyzing", "Analitzant el grup, les premisses i el temps disponible…")
    for round_index in range(max_rounds):
        payload = {
            "model": model,
            "instructions": _instructions(),
            "input": history,
            "reasoning": {
                "effort": getattr(
                    settings, "OPENAI_TRAINING_REASONING_EFFORT", "medium"
                )
            },
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": getattr(
                settings, "OPENAI_TRAINING_MAX_OUTPUT_TOKENS", 9000
            ),
            "tools": [
                tool
                for tool in tool_definitions()
                if tool.get("name") != "audit_block_draft" or executor.audit_calls < 2
            ],
            "tool_choice": (
                {"type": "function", "name": "search_exercises"}
                if round_index == 0
                else "auto"
            ),
            "parallel_tool_calls": True,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "iatrain_agentic_physical_block",
                    "strict": True,
                    "schema": _proposal_schema(),
                }
            },
        }
        data = _post_responses_api(payload)
        actual_model = data.get("model") or actual_model
        if data.get("id"):
            response_ids.append(data["id"])
        _usage_total(usage, data.get("usage"))
        emit(
            "reasoning",
            "El model està valorant la informació disponible…",
        )
        output = data.get("output", [])
        history.extend(output)
        function_calls = [item for item in output if item.get("type") == "function_call"]
        if function_calls:
            for function_call in function_calls:
                call_count += 1
                if call_count > max_calls:
                    raise runtime_error(
                        "L'agent ha superat el límit de consultes permès."
                    )
                arguments = {}
                try:
                    arguments = json.loads(function_call.get("arguments") or "{}")
                    result = executor.execute(function_call.get("name", ""), arguments)
                    envelope = {"ok": True, "result": result}
                    tool_name = function_call.get("name", "")
                    if tool_name == "search_exercises":
                        emit(
                            "searching",
                            (
                                f"Cerca completada: {result.get('returned', 0)} candidats "
                                f"mostrats de {result.get('total_matches', 0)} coincidències."
                            ),
                        )
                    elif tool_name == "get_exercise_details":
                        emit(
                            "comparing",
                            f"Comparant en detall {len(result.get('results', []))} exercicis…",
                        )
                    elif tool_name == "get_prescription_guidance":
                        emit("dosing", "Revisant rangs de dosificació professionals…")
                    elif tool_name == "check_participant_compatibility":
                        emit(
                            "personalizing",
                            "Comprovant compatibilitat i possibles variants individuals…",
                        )
                    elif tool_name == "find_compatible_alternatives":
                        emit(
                            "personalizing",
                            (
                                f"S’han trobat {result.get('returned', 0)} alternatives "
                                "compatibles per a una personalització."
                            ),
                        )
                    elif tool_name == "calculate_block_timing":
                        emit(
                            "timing",
                            (
                                f"Temps calculat: {result.get('total_seconds', 0)} segons; "
                                + (
                                    "cap dins del bloc."
                                    if result.get("fits_budget")
                                    else "cal reajustar el bloc."
                                )
                            ),
                        )
                    elif tool_name == "audit_block_draft":
                        emit(
                            "validating",
                            (
                                "L’esborrany supera l’auditoria interna."
                                if result.get("valid")
                                else "L’esborrany necessita correccions abans d’acabar."
                            ),
                        )
                except (ValueError, TypeError, KeyError, ValidationError) as error:
                    message = _validation_messages(error)[0][:500]
                    executor.trace.append(
                        {
                            "sequence": len(executor.trace) + 1,
                            "tool": function_call.get("name", ""),
                            "arguments": arguments,
                            "status": "error",
                            "error": message,
                            "exercise_revision_ids": [],
                        }
                    )
                    envelope = {"ok": False, "error": message}
                    emit(
                        "adjusting",
                        "Una consulta no era vàlida; el model està ajustant l’estratègia…",
                    )
                history.append(
                    {
                        "type": "function_call_output",
                        "call_id": function_call["call_id"],
                        "output": json.dumps(envelope, ensure_ascii=False, default=str),
                    }
                )
            continue

        text = _response_output_text(data)
        if not text:
            raise runtime_error("OpenAI no ha retornat una proposta utilitzable.")
        try:
            final = json.loads(text)
        except json.JSONDecodeError as error:
            raise runtime_error(
                "La resposta final d'OpenAI no compleix el contracte."
            ) from error
        if final.get("intent_status") == "needs_clarification":
            question = final.get("clarification_question") or "Cal concretar la petició."
            if (
                not executor.allow_drafts
                and (
                    executor.draft_candidate_ids
                    or (
                        not executor.allowed_exercise_ids
                        and executor.draft_matches_available > 0
                    )
                )
            ):
                raise decision_error(
                    "La cerca necessita exercicis en esborrany per poder continuar.",
                    _draft_permission_issues(
                        draft_count=executor.draft_matches_available,
                        draft_ids=executor.draft_candidate_ids,
                    ),
                )
            raise InterpretationNeedsClarification(
                question,
                payload={
                    "planning_summary": final.get("planning_summary", ""),
                    "premise_effects": final.get("premise_effects", []),
                },
                model_name=actual_model,
            )
        if not executor.allowed_exercise_ids:
            if not executor.allow_drafts and executor.draft_matches_available > 0:
                raise decision_error(
                    "La cerca necessita exercicis en esborrany per poder continuar.",
                    _draft_permission_issues(
                        draft_count=executor.draft_matches_available
                    ),
                )
            raise InterpretationNeedsClarification(
                (
                    "No he trobat cap exercici utilitzable amb les premisses actuals. "
                    "Vols ampliar els criteris, revisar el catàleg o reformular l’objectiu?"
                ),
                payload={
                    "planning_summary": final.get("planning_summary", ""),
                    "premise_effects": final.get("premise_effects", []),
                    "search_summary": final.get("search_summary", ""),
                },
                model_name=actual_model,
            )
        try:
            if not any(row.get("tool") == "search_exercises" and row.get("status") == "ok" for row in executor.trace):
                raise ValidationError("L'agent no ha consultat el catàleg.")
            if executor.last_timing is None:
                raise ValidationError("L'agent no ha calculat la durada final.")
            if int(final["estimated_duration_seconds"]) != int(
                executor.last_timing["total_seconds"]
            ):
                raise ValidationError(
                    "La durada final no coincideix amb l'últim càlcul temporal."
                )
            proposal_payload = _server_proposal_payload(
                final=final,
                context=context,
                duration_minutes=duration,
                block_role=block_role,
                active_ids=active_ids,
                excluded_ids=excluded_ids,
            )
            proposal = proposal_from_payload(proposal_payload)
            unknown_ids = referenced_exercise_revision_ids(proposal) - executor.allowed_exercise_ids
            if unknown_ids:
                raise ValidationError(
                    f"La proposta usa exercicis no retornats per les eines: {sorted(unknown_ids)}."
                )
            required_detail_ids, required_pairs = _required_tool_evidence(proposal)
            missing_details = required_detail_ids - executor.detail_exercise_ids
            if missing_details:
                raise ValidationError(
                    "Falten detalls dels exercicis seleccionats: "
                    f"{sorted(missing_details)}."
                )
            missing_compatibility = required_pairs - executor.compatibility_pairs
            if missing_compatibility:
                raise ValidationError(
                    "Falten comprovacions de compatibilitat exercici-participant: "
                    f"{sorted(missing_compatibility)}."
                )
            missing_guidance = required_pairs - executor.guidance_pairs
            if missing_guidance:
                raise ValidationError(
                    "Falten guies de dosificació exercici-participant: "
                    f"{sorted(missing_guidance)}."
                )
            timing_errors = _validate_timing_evidence(
                proposal=proposal, executor=executor
            )
            if timing_errors:
                raise ValidationError(timing_errors)
            participants_with_skips = _participants_with_skips(proposal)
            missing_alternative_searches = (
                participants_with_skips
                - executor.alternative_search_participant_ids
            )
            if missing_alternative_searches:
                raise ValidationError(
                    "Abans d'ometre tot el bloc per a una participant, cal cercar "
                    "alternatives compatibles per a: "
                    f"{sorted(missing_alternative_searches)}."
                )
            participants_without_exposure = _participants_without_exposure(proposal)
            if participants_without_exposure:
                raise decision_error(
                    "No s’ha trobat una exposició útil per a totes les participants.",
                    [
                        {
                            "participant_plan_id": participant_id,
                            "decision_key": str(participant_id),
                            "reason_code": "participant_without_exposure",
                            "title": "No s’ha trobat cap alternativa compatible",
                            "explanation": (
                                "L’agent ha cercat alternatives, però aquesta gimnasta "
                                "acabaria ometent tot el bloc."
                            ),
                            "choices": [
                                {
                                    "value": "exclude_from_block",
                                    "label": "Excloure-la només d’aquest bloc",
                                }
                            ],
                            "profile_review_available": True,
                        }
                    ],
                )
            draft_ids = set(
                ExerciseRevision.objects.filter(
                    pk__in=referenced_exercise_revision_ids(proposal)
                )
                .exclude(editorial_status="validated")
                .values_list("pk", flat=True)
            )
            if (
                draft_ids
                and decisions.get("catalog_drafts") != "allow_draft_exercises"
                and "validated_only" not in proposal.request.hard_constraints
            ):
                raise decision_error(
                    "La proposta necessita exercicis pendents de validació editorial.",
                    _draft_permission_issues(draft_ids=draft_ids),
                )
            validate_block_generation_proposal(
                proposal,
                revision=context.revision,
                exercise_owner=context.owner,
            )
            _validate_agent_context_invariants(proposal=proposal, context=context)
            independent_review = None
            if getattr(settings, "OPENAI_TRAINING_REVIEW_ENABLED", True):
                emit(
                    "reviewing",
                    "Un segon model està revisant coherència, dosi i personalització…",
                )
                review_data, independent_review = _request_independent_review(
                    proposal=proposal,
                    context=context,
                    executor=executor,
                    active_ids=active_ids,
                    excluded_ids=excluded_ids,
                )
                if review_data.get("id"):
                    response_ids.append(review_data["id"])
                _usage_total(usage, review_data.get("usage"))
                validation_payload.setdefault("review_attempts", []).append(
                    independent_review
                )
                if independent_review["verdict"] == "needs_clarification":
                    question = independent_review.get("clarification_question") or (
                        "El revisor necessita una dada imprescindible abans de continuar."
                    )
                    raise InterpretationNeedsClarification(
                        question,
                        payload={
                            "planning_summary": final.get("planning_summary", ""),
                            "premise_effects": final.get("premise_effects", []),
                            "review_summary": independent_review.get("summary", ""),
                            "review_issues": independent_review.get("issues", []),
                        },
                        model_name=actual_model,
                    )
                if independent_review["verdict"] == "revise":
                    blocking_issues = [
                        row
                        for row in independent_review.get("issues", [])
                        if row.get("severity") == "error"
                    ] or independent_review.get("issues", [])
                    raise ValidationError(
                        [
                            f"Revisor {row.get('code', 'semantic')}: "
                            f"{row.get('message', '')} Correcció: "
                            f"{row.get('correction', '')}"
                            for row in blocking_issues
                        ]
                    )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            messages = _validation_messages(error)
            validation_payload["attempts"].append(
                {"valid": False, "errors": messages[:20]}
            )
            if repairs >= max_repairs:
                raise runtime_error(
                    "L'agent no ha pogut reparar la proposta: " + "; ".join(messages[:3])
                ) from error
            repairs += 1
            emit(
                "repairing",
                f"Validació del servidor: corregint la proposta ({repairs}/{max_repairs})…",
                validation_errors=messages[:3],
            )
            history.append(
                {
                    "role": "user",
                    "content": (
                        "La proposta no supera la validació del servidor. Corregeix-la, "
                        "torna a consultar eines o recalcula el temps si cal, i entrega el "
                        "contracte complet. Errors: " + json.dumps(messages, ensure_ascii=False)
                    ),
                }
            )
            continue
        validation_payload["attempts"].append({"valid": True, "errors": []})
        validation_payload["allowed_exercise_revision_ids"] = sorted(
            executor.allowed_exercise_ids
        )
        validation_payload["last_timing"] = executor.last_timing
        validation_payload["independent_review"] = independent_review
        interpretation = {
            "intent_status": "ready",
            "planning_summary": final["planning_summary"],
            "premise_effects": final["premise_effects"],
            "search_summary": final["search_summary"],
            "agent_rounds": len(response_ids),
            "tool_calls": call_count,
            "review_summary": (
                independent_review.get("summary", "")
                if independent_review
                else "Revisió independent desactivada."
            ),
        }
        emit("completed", "Proposta preparada i validada.")
        return AgentBlockResult(
            proposal=proposal,
            interpretation_payload=interpretation,
            model_name=actual_model,
            tool_trace=tuple(executor.trace),
            response_ids=tuple(response_ids),
            usage_payload=usage,
            validation_payload=validation_payload,
        )
    if not executor.allowed_exercise_ids:
        if not executor.allow_drafts and executor.draft_matches_available > 0:
            raise decision_error(
                "La cerca necessita exercicis en esborrany per poder continuar.",
                _draft_permission_issues(
                    draft_count=executor.draft_matches_available
                ),
            )
        raise InterpretationNeedsClarification(
            (
                "No s’ha trobat cap exercici utilitzable després d’explorar el catàleg. "
                "Cal ampliar criteris, revisar el catàleg o reformular l’objectiu."
            ),
            payload={"planning_summary": "", "premise_effects": []},
            model_name=actual_model,
        )
    raise runtime_error("L'agent ha superat el límit d'iteracions sense completar la proposta.")
