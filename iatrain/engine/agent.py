"""Agentic OpenAI boundary for complete physical block planning."""

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

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
from .context import build_group_engine_summary
from .contracts import PHYSICAL_BLOCK_HARD_CONSTRAINTS, TARGET_INTENSITIES
from .openai import (
    InterpretationNeedsClarification,
    OpenAITrainingNotConfigured,
    OpenAITrainingUnavailable,
    _response_output_text,
)
from .planning import planning_payload_bytes, proposal_alignment_errors
from .serialization import (
    contract_to_payload,
    proposal_from_payload,
    proposal_payload_from_agent_output,
)
from .scoring import PATTERN_REGIONS, condition_applies
from .validation import referenced_exercise_revision_ids, validate_block_generation_proposal


AGENT_PROMPT_VERSION = "physical-block-agent-3.10"
AGENT_ENGINE_VERSION = "physical-block-agent-engine-3.10"


@dataclass(frozen=True, slots=True)
class AgentBlockResult:
    proposal: object
    interpretation_payload: dict
    model_name: str
    tool_trace: tuple[dict, ...]
    response_ids: tuple[str, ...]
    usage_payload: dict
    validation_payload: dict
    planning_payload: dict = field(default_factory=dict)
    review_required: bool = False
    review_issues: tuple[dict, ...] = ()


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


class OpenAITrainingRateLimited(OpenAITrainingUnavailable):
    """Retryable Responses API TPM/RPM limit."""

    code = "openai_rate_limited"

    def __init__(self, message, *, retry_after_seconds=1.0):
        super().__init__(message)
        self.retry_after_seconds = max(0.0, float(retry_after_seconds))


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
    individual_support = _strict_object(
        {
            "condition_ids": _array({"type": "integer"}),
            "profile_factor_codes": _array({"type": "string"}),
            "professional_claim_ids": _array({"type": "string"}),
            "affected_phase_codes": _array({"type": "string"}),
            "biomechanical_relevance": {"type": "string"},
            "adaptation_goal": {"type": "string"},
            "monitoring_criteria": _array({"type": "string"}),
            "stop_criteria": _array({"type": "string"}),
            "evidence_status": {
                "type": "string",
                "enum": ["grounded", "hypothesis"],
            },
        }
    )
    adjustment = _strict_object(
        {
            "participant_plan_id": {"type": "integer"},
            "rationale": {"type": "string"},
            "action": {
                "type": "string",
                "enum": ["monitor", "modify", "replace", "skip"],
            },
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
            "station_remainder_action": {
                "type": "string",
                "enum": ["", "rest", "reset", "monitor"],
            },
            "adaptation_notes": {"type": "string"},
            "professional_justification": individual_support,
        }
    )
    knowledge_claim = _strict_object(
        {
            "claim_id": {"type": "string"},
            "exercise_revision_id": {"type": "integer"},
            "phase_code": {"type": "string"},
            "claim_type": {
                "type": "string",
                "enum": ["joint_action", "muscle_role"],
            },
            "action_code": {"type": "string"},
            "muscle_code": {"type": "string"},
            "basis_type": {
                "type": "string",
                "enum": [
                    "motion_concept",
                    "action_function",
                    "stabilization_function",
                ],
            },
            "basis_code": {"type": "string"},
            "expected_contraction": {
                "type": "string",
                "enum": [
                    "concentric", "eccentric", "isometric", "variable",
                    "indeterminate", "not_applicable",
                ],
            },
            "verification_state": {
                "type": "string",
                "enum": ["confirmed", "inferred"],
            },
            "evidence_codes": _array({"type": "string"}),
            "limitations": _array({"type": "string"}),
        }
    )
    knowledge_support = _strict_object(
        {
            "status": {
                "type": "string",
                "enum": ["grounded", "hypothesis", "not_applicable"],
            },
            "summary": {"type": "string"},
            "claims": _array(knowledge_claim),
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
            "knowledge_support": knowledge_support,
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

Abans de consultar qualsevol altra eina, registra submit_block_planning_brief. Aquest pla
previ defineix resultats, no exercicis: objectiu, criteris d'èxit, cobertura, intensitat,
temps, estratègia compartida, prioritats individuals, abast de restriccions, preguntes
professionals i estratègia de cerca. No hi posis identificadors d'exercici. Les preferències
globals han d'indicar si provenen de coach_prompt, session_goal, coach_decision o
planning_inference; una
condició individual mai no es converteix en una preferència global. Conserva el pla durant
el run i fes que la proposta final el compleixi.
En una petició full body, exigeix només els dominis lower_body, upper_body i trunk. Deixa
els patrons concrets a preferred_movement_patterns, tret que l'entrenador n'hagi demanat
un explícitament. global_hard_constraints només pot repetir restriccions literals de la
petició o ja autoritzades; les precaucions que infereixis van a global_preferences amb
source=planning_inference. No declaris validated_only si hi ha autorització d'esborranys.

Has d'usar search_exercises abans de seleccionar res. Pots fer tantes cerques diferents
com necessitis, paginar i ampliar o relaxar filtres si hi ha pocs candidats. Consulta els
detalls, la compatibilitat i les guies dels finalistes. Abans d'entregar, crida
calculate_block_timing amb la dosificació exacta final. Pots usar audit_block_draft com a
màxim dues vegades; després entrega la proposta perquè el servidor faci la validació final.
No inventis mai identificadors: només pots usar revisions retornades per search_exercises.

La base professional anatòmica-biomecànica és la font dels fets sobre moviment i
musculatura. Si la petició parla d'accions, articulacions, músculs, grups musculars o
contraccions, usa search_professional_concepts i reutilitza només els codis retornats als
filtres de search_exercises. Per a un grup muscular, usa els codis dels músculs membres
retornats per les relacions incoming member_of_muscle_group. «Concèntric», «excèntric» o
«isomètric» descriu una fase i una funció muscular prevista, no tot l'exercici de manera
absoluta. get_exercise_details és compacte i no inclou claims. Consulta
get_exercise_knowledge_support una sola vegada per cada exercici finalista, alternativa o
substitució; el servidor ja conserva els claims i no els tornarà a enviar si repeteixes la
consulta.

Cada ítem necessita knowledge_support. Usa grounded només si copies claim_id i la resta de
camps exactament dels camins retornats, i cobreix tots els exercicis referenciats a l'ítem.
Si la base no conté un camí suficient, usa hypothesis, explica el buit, redueix la confiança
i afegeix un avís: l'absència no és una prohibició. Usa not_applicable només quan la raó de
tria no formula cap afirmació anatòmica, però igualment consulta el paquet professional.
No converteixis una inferència funcional en activació observada, força interna o risc.

Cada athlete_adjustment necessita professional_justification. Enllaça la condició activa
o un factor explícit del perfil amb claim_id i phase_code exactes del knowledge_support de
l'ítem, explica per separat la rellevància biomecànica inferida, l'objectiu de l'adaptació,
què s'ha de monitorar i quan cal aturar o canviar. grounded només vol dir que els fets de
l'exercici estan fonamentats: no atribueix a la font anatòmica una conclusió clínica. Si
falta un camí professional suficient, usa hypothesis, redueix confiança i mostra un avís.

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
experiència o incertesa. Una dada absent és incertesa, no una prohibició: continua amb una
decisió prudent, redueix la confiança i afegeix un avís si és rellevant, però no demanis
aclariments només perquè falta edat, experiència, càrrega, regió corporal o una altra dada.
No diagnostiquis ni prescriguis tractament. Una condició stop ja ha estat resolta pel
servidor; avoid, modify i monitor s'han de respectar explícitament. Una condició monitor
necessita sempre una condition_decision: usa action=monitor i un athlete_adjustment amb
criteris de seguiment i aturada quan no cal canviar la dosi, o modify/replace/skip si sí.

Les guies són envolupants, no receptes deterministes: decideix dins d'elles o justifica
qualsevol desviació prudent. estimated_duration_seconds ha de coincidir exactament amb
l'últim calculate_block_timing i no superar el pressupost. Tots els participants actius
i exclosos s'han d'incloure una sola vegada. Una participant personalized ha de tenir
almenys un athlete_adjustment real, i qualsevol participant amb ajustament ha de ser
personalized. No escriguis indicacions individuals dins instructions, coaching_cues o
execution_notes compartides: posa-les sempre a athlete_adjustments.

Abans de substituir, comprova si l'exercici original ja evita realment el risc i si és
possible conservar-lo modificant rang, càrrega, palanca o dosi. Una substitució ha de
preservar l'objectiu, la regió corporal i preferentment el patró de moviment; un exercici
segur però funcionalment irrellevant no és una alternativa. Cerca primer amb
same_pattern_only=true. Quan incorporis un exercici o una nova parella
exercici-participant, demana junts en una mateixa ronda tots els detalls, compatibilitats
i guies pendents. La Responses API pot retornar diverses function calls en aquella ronda.

Per a cada condició activa avoid, modify o monitor, crea una condition_decision. Si no afecta cap
ítem, usa not_applicable i justifica-ho. Una condició avoid no obliga automàticament a
substituir: pots usar modify si l'ajust elimina explícitament el risc concret (per exemple
rang, impacte, càrrega, palanca, tempo o volum), replace si l'alternativa redueix aquell
risc, o skip com a última via. La justificació i adaptation_notes han de dir quin risc es
resol i com; compartir regió corporal o patró no demostra per si sol incompatibilitat.
modify, replace o skip han de correspondre amb athlete_adjustments als sequence_index
indicats. Cada exercici seleccionat, incloses
alternatives i substitucions, necessita detalls, compatibilitat i guia consultats. Copia
setup_seconds i planned_duration_seconds de l'últim calculate_block_timing perquè el temps
visible i el calculat siguin idèntics. planned_duration_seconds és el total d'una passada
per l'ítem i JA INCLOU setup_seconds, el treball, els descansos entre sèries i
rest_after_seconds; no tornis a sumar aquests components. unmet_constraints ha de quedar buit.

En circuits o estacions, duration_seconds d'un ajustament és temps de treball dins el
temps compartit, no una nova durada d'estació. Si és inferior a la dosi comuna, indica
station_remainder_action=rest, reset o monitor i descriu l'ús del temps restant. No pot
superar la durada comuna.

No tens cerca web en aquesta fase. No inventis bibliografia. planning_summary és una
justificació visible i concisa, no una cadena de pensament. Escriu en català.
Contracte: 3.5. Pla previ: 1.1. Eines: {TOOL_VERSION}.
""".strip()


def _athlete_payload(context, active_ids, excluded_ids, *, detail=False):
    rows = []
    active = set(active_ids)
    excluded = set(excluded_ids)
    for athlete in context.athletes:
        payload = athlete.payload
        recent_responses = payload.get("recent_training_responses", [])
        observations = payload.get("current_observations", [])
        row = {
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
                "sport_profiles": [
                    {
                        key: sport.get(key)
                        for key in (
                            "discipline",
                            "level_code",
                            "training_started_on",
                            "preferred_laterality",
                        )
                    }
                    for sport in payload.get("sport_profiles", [])
                ],
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
                "confirmed_insights": [
                    {
                        key: insight.get(key)
                        for key in ("id", "kind", "statement", "confidence", "valid_until")
                    }
                    for insight in payload.get("confirmed_insights", [])[:5]
                ],
                "recent_state": {
                    "observation_count": len(observations),
                    "training_response_count": len(recent_responses),
                    "last_training_at": (
                        recent_responses[0].get("recorded_at")
                        if recent_responses
                        else None
                    ),
                    "latest_observations": [
                        {
                            key: observation.get(key)
                            for key in (
                                "id",
                                "category",
                                "narrative",
                                "status",
                                "confidence",
                                "intensity",
                                "observed_at",
                            )
                        }
                        for observation in observations[:3]
                    ],
                    "latest_training_responses": [
                        {
                            key: response.get(key)
                            for key in (
                                "id",
                                "item_title",
                                "completion_status",
                                "perceived_exertion",
                                "execution_quality",
                                "pain_response",
                                "recorded_at",
                            )
                            if key in response
                        }
                        for response in recent_responses[:3]
                    ],
                },
                "health_data_available": payload.get("scope", {}).get(
                    "health_data_available", False
                ),
                "detail_available_via": "get_participant_context",
                "excluded_by_coach": athlete.participant_plan_id in excluded,
            }
        if detail:
            row["current_observations"] = observations[:8]
            row["recent_training_responses"] = recent_responses[:12]
            row["latest_measurements"] = payload.get("latest_measurements", [])
            row["proposed_insights"] = payload.get("proposed_insights", [])
        rows.append(row)
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
        "group_summary": build_group_engine_summary(context, active_ids),
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
        retry_after = 0.0
        try:
            retry_after = float(exc.headers.get("Retry-After", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            retry_after = 0.0
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="ignore"))
            message = detail.get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        if exc.code == 429:
            if retry_after <= 0:
                match = re.search(
                    r"try again in\s+([0-9]+(?:\.[0-9]+)?)s",
                    message,
                    flags=re.IGNORECASE,
                )
                retry_after = float(match.group(1)) if match else 1.0
            raise OpenAITrainingRateLimited(
                "OpenAI ha limitat temporalment els tokens per minut"
                + (f": {message[:240]}" if message else "."),
                retry_after_seconds=retry_after,
            ) from exc
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
            "severity": {
                "type": "string",
                "enum": ["critical", "error", "warning"],
            },
            "message": {"type": "string"},
            "correction": {"type": "string"},
            "participant_plan_ids": _array({"type": "integer"}),
            "sequence_indices": _array({"type": "integer"}),
            "exercise_revision_ids": _array({"type": "integer"}),
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


def _review_packet(
    *, proposal, context, executor, active_ids, excluded_ids, request_context=None
):
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
        for row in _athlete_payload(context, active_ids, excluded_ids, detail=True)
        if row["participation_state"] == "active"
    ]
    request_context = request_context or {}
    timing_errors = _validate_timing_evidence(
        proposal=proposal,
        executor=executor,
    )
    return {
        "planning_brief": dict(executor.planning_brief or {}),
        "request_context": {
            "coach_prompt": request_context.get("coach_prompt", ""),
            "refinement_instruction": request_context.get(
                "refinement_instruction", ""
            ),
            "coach_decisions": request_context.get("coach_decisions", {}),
            "server_authority": request_context.get("server_authority", {}),
            "session": request_context.get("session", {}),
            "context_warnings": request_context.get("context_warnings", []),
        },
        "proposal": contract_to_payload(proposal),
        "active_athletes": athletes,
        "selected_exercises": exercises,
        "evidence": {
            "detail_exercise_ids": sorted(executor.detail_exercise_ids),
            "professional_knowledge": {
                "exercise_revision_ids": sorted(executor.knowledge_exercise_ids),
                "claims": list(executor.knowledge_claims.values()),
                "sources": list(executor.knowledge_sources.values()),
                "interpretation_policy": {
                    "activation_is_observed": False,
                    "absence_is_not_prohibition": True,
                },
            },
            "guidance_pairs": sorted([list(value) for value in executor.guidance_pairs]),
            "compatibility_pairs": sorted(
                [list(value) for value in executor.compatibility_pairs]
            ),
            "timing": executor.last_timing,
            "timing_contract": {
                "planned_duration_seconds_semantics": (
                    "Total d'una passada per l'ítem; inclou setup_seconds, treball, "
                    "descansos entre sèries i rest_after_seconds."
                ),
                "equation": (
                    "planned_duration_seconds = setup + work + between_sets + rest_after"
                ),
                "components_are_already_included": True,
                "server_timing_valid": not timing_errors,
                "server_timing_errors": timing_errors,
                "numerical_authority": "calculate_block_timing + server validation",
            },
        },
    }


def _compact_repair_history(
    *, initial, final, errors, executor, context, active_ids, excluded_ids,
    proposal=None, source="server", required_tool_calls=None,
):
    """Start a fresh repair turn with only current state and retained evidence."""

    selected_exercises = []
    if proposal is not None:
        selected_exercises = _review_packet(
            proposal=proposal,
            context=context,
            executor=executor,
            active_ids=active_ids,
            excluded_ids=excluded_ids,
        )["selected_exercises"]
    trace_summary = [
        {
            "tool": row.get("tool"),
            "status": row.get("status"),
            "exercise_revision_ids": row.get("exercise_revision_ids", []),
            "total_matches": row.get("total_matches"),
            "audit_valid": row.get("audit_valid"),
        }
        for row in executor.trace[-30:]
    ]
    packet = {
        "mode": "repair_current_proposal",
        "repair_source": source,
        "original_request": initial,
        "current_proposal": final,
        "errors_to_fix": list(errors),
        "retained_evidence": {
            "planning_brief": dict(executor.planning_brief or {}),
            "selected_exercises": selected_exercises,
            "allowed_exercise_revision_ids": sorted(executor.allowed_exercise_ids),
            "detail_exercise_ids": sorted(executor.detail_exercise_ids),
            "knowledge_exercise_ids": sorted(executor.knowledge_exercise_ids),
            "knowledge_claim_ids": sorted(executor.knowledge_claims),
            "compatibility_pairs": sorted(
                [list(value) for value in executor.compatibility_pairs]
            ),
            "guidance_pairs": sorted([list(value) for value in executor.guidance_pairs]),
            "last_timing": executor.last_timing,
            "tool_trace_summary": trace_summary,
        },
        "required_tool_calls": list(required_tool_calls or []),
        "repair_instruction": (
            "Executa primer totes les required_tool_calls pendents, preferentment juntes "
            "en una sola resposta amb múltiples function calls. Conserva la proposta si "
            "l'evidència la confirma; si revela una incompatibilitat o exigeix canviar la "
            "dosi, fes només aquell ajust, completa l'evidència nova i recalcula el temps. "
            "Després retorna el contracte complet."
            if source == "tool_evidence"
            else
            "Corregeix només les incidències indicades. Conserva les decisions vàlides, "
            "reutilitza l'evidència retinguda i torna a consultar eines només si canvies "
            "un exercici o la dosi. Si has canviat exercicis o participants afectats, "
            "demana junts detalls, compatibilitat i guia. Retorna el contracte complet."
        ),
    }
    return [
        {
            "role": "user",
            "content": json.dumps(packet, ensure_ascii=False, default=str),
        }
    ]


def _compact_live_history(*, initial, executor, context, active_ids, excluded_ids):
    """Replace accumulated tool transcripts with a factual server-side ledger."""

    revisions = (
        ExerciseRevision.objects.filter(pk__in=executor.allowed_exercise_ids)
        .select_related("exercise")
        .prefetch_related("objectives", "constraints")
        .order_by("pk")
    )
    candidates = []
    for revision in revisions:
        row = {
            "exercise_revision_id": revision.pk,
            "name": revision.exercise.name,
            "editorial_status": revision.editorial_status,
            "modality": revision.modality,
            "difficulty": revision.difficulty,
            "movement_pattern": revision.movement_pattern,
            "laterality": revision.laterality,
            "objectives": [item.objective for item in revision.objectives.all()],
            "details_loaded": revision.pk in executor.detail_exercise_ids,
            "knowledge_loaded": revision.pk in executor.knowledge_exercise_ids,
        }
        if revision.pk in executor.detail_exercise_ids:
            row.update(
                {
                    "description": revision.description,
                    "setup": revision.setup,
                    "execution": revision.execution,
                    "coaching_cues": revision.coaching_cues,
                    "safety_notes": revision.safety_notes,
                    "constraints": [
                        {
                            "code": item.code,
                            "severity": item.severity,
                            "statement": item.statement,
                        }
                        for item in revision.constraints.all()
                    ],
                }
            )
        candidates.append(row)
    packet = {
        "mode": "continue_from_compacted_tool_ledger",
        "original_request": initial,
        "planning_brief": dict(executor.planning_brief or {}),
        "athletes": _athlete_payload(context, active_ids, excluded_ids),
        "candidate_ledger": candidates,
        "professional_evidence": {
            "claims": list(executor.knowledge_claims.values()),
            "sources": list(executor.knowledge_sources.values()),
        },
        "guidance": list(executor.guidance_packets),
        "compatibility": list(executor.compatibility_packets),
        "evidence_status": {
            "detail_exercise_ids": sorted(executor.detail_exercise_ids),
            "knowledge_exercise_ids": sorted(executor.knowledge_exercise_ids),
            "guidance_pairs": sorted([list(value) for value in executor.guidance_pairs]),
            "compatibility_pairs": sorted(
                [list(value) for value in executor.compatibility_pairs]
            ),
            "last_timing": executor.last_timing,
        },
        "tool_trace_summary": [
            {
                "tool": row.get("tool"),
                "status": row.get("status"),
                "exercise_revision_ids": row.get("exercise_revision_ids", []),
                "total_matches": row.get("total_matches"),
            }
            for row in executor.trace
        ],
        "continue_instruction": (
            "Continua des d'aquest registre. No repeteixis consultes marcades com a "
            "carregades. Completa només l'evidència pendent, calcula el temps final i "
            "retorna la proposta completa alineada amb planning_brief."
        ),
    }
    return [
        {
            "role": "user",
            "content": json.dumps(packet, ensure_ascii=False, default=str),
        }
    ]


def _request_independent_review(
    *, proposal, context, executor, active_ids, excluded_ids, request_context=None
):
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
            "coherència amb la petició i amb planning_brief, cobertura real, nivell i "
            "inactivitat, dosificació, "
            "seguretat, condicions individuals, alternatives i correspondència entre "
            "justificacions i ajustaments estructurats. Comprova també que les afirmacions "
            "anatòmiques de knowledge_support coincideixin amb professional_knowledge, "
            "respectin verification_state i mantinguin les limitacions; una hipòtesi no "
            "es pot presentar com un fet. Revisa també cada professional_justification: "
            "la condició o factor de perfil, les afirmacions i fases citades, l'objectiu "
            "de l'adaptació i els criteris de monitoratge/aturada han de correspondre. "
            "Per temporització, timing_contract és autoritatiu: planned_duration_seconds "
            "ja inclou setup, treball, descansos entre sèries i rest_after. No els sumis "
            "una segona vegada. Només marca un error numèric si server_timing_valid és "
            "false; encara pots marcar una contradicció real del text operatiu. "
            "Marca revise davant qualsevol "
            "error material i dona correccions concretes. Usa severity=critical només "
            "davant un risc greu no resolt, una restricció mèdica incompatible o una "
            "proposta que no es podria executar amb seguretat. Usa severity=error per "
            "incoherències locals corregibles manualment, com equivalència, cobertura o "
            "dosi individual. Per cada incidència identifica participant_plan_ids, "
            "sequence_indices i exercise_revision_ids afectats quan es coneguin. Usa "
            "No confonguis una dada absent amb una restricció ni contradiguis una premissa "
            "explícita de request_context. La manca de dades no bloqueja: comprova que la "
            "proposta sigui prudent, redueixi confiança o mostri un avís quan calgui. Usa "
            "Per incertesa o dades absents usa revise amb severity=error perquè la proposta "
            "quedi disponible per a revisió humana; reserva needs_clarification per "
            "compatibilitats històriques. Un warning no bloqueja per si sol. Respon en català amb "
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
                        request_context=request_context,
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
    retries = 0
    max_retries = max(
        0, getattr(settings, "OPENAI_TRAINING_MAX_RATE_LIMIT_RETRIES", 2)
    )
    max_wait = max(
        1, getattr(settings, "OPENAI_TRAINING_MAX_RATE_LIMIT_WAIT_SECONDS", 60)
    )
    while True:
        try:
            data = _post_responses_api(payload)
            break
        except OpenAITrainingRateLimited as error:
            wait = error.retry_after_seconds + 0.5
            if retries >= max_retries or wait > max_wait:
                raise OpenAITrainingUnavailable(
                    "El revisor ha superat el límit temporal d'OpenAI després dels "
                    "reintents configurats."
                ) from error
            retries += 1
            time.sleep(wait)
    data["iatrain_rate_limit_retries"] = retries
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
    planning_enabled = getattr(
        settings, "OPENAI_TRAINING_PLANNING_BRIEF_ENABLED", True
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
        contract_version="3.5" if planning_enabled else "3.4",
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
    if proposal.contract_version in {"3.1", "3.2", "3.3", "3.4", "3.5"}:
        required_condition_impacts = {"avoid", "modify"}
        if proposal.contract_version in {"3.4", "3.5"}:
            required_condition_impacts.add("monitor")
        for participant_id, athlete in athletes.items():
            participant = participant_rows.get(participant_id)
            if participant is None:
                continue
            active_conditions = {
                int(condition["id"]): condition
                for condition in athlete.payload.get("active_conditions", [])
                if condition.get("id")
                and condition.get("training_impact") in required_condition_impacts
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
                allowed_actions = {
                    "not_applicable", "monitor", "modify", "replace", "skip"
                }
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
                        continue
                    support = adjustment.professional_justification
                    if (
                        proposal.contract_version in {"3.4", "3.5"}
                        and (
                            support is None
                            or condition_id not in support.condition_ids
                        )
                    ):
                        errors.append(
                            f"La justificació individual de la condició {condition_id} "
                            f"no està vinculada a l'ítem {sequence_index}."
                        )
                    if proposal.contract_version == "3.5" and support is not None:
                        laterality = condition.get("laterality", "")
                        laterality_tokens = {
                            "left": ("esquerr", "left"),
                            "right": ("dret", "dreta", "right"),
                        }.get(laterality)
                        if laterality_tokens:
                            monitoring_text = " ".join(
                                [
                                    adjustment.rationale,
                                    adjustment.adaptation_notes,
                                    *support.monitoring_criteria,
                                    *support.stop_criteria,
                                ]
                            ).casefold()
                            if not any(
                                token in monitoring_text
                                for token in laterality_tokens
                            ):
                                errors.append(
                                    f"La condició {condition_id} és {laterality}: "
                                    "l'ajustament i el monitoratge han d'explicitar el costat."
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
                adjustment is None
                or adjustment.action not in {"modify", "replace", "skip"}
            ):
                errors.append(
                    f"El participant {participant_id} necessita resoldre explícitament "
                    f"el risc a l'exercici {base.pk} mitjançant modify, replace o skip."
                )
            if "modify" in impacts and adjustment is None:
                errors.append(
                    f"El participant {participant_id} necessita una adaptació explícita "
                    f"per a l'exercici {base.pk}."
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


def _missing_tool_evidence(*, proposal, executor):
    required_detail_ids, required_pairs = _required_tool_evidence(proposal)
    return {
        "details": required_detail_ids - executor.detail_exercise_ids,
        "knowledge": required_detail_ids - executor.knowledge_exercise_ids,
        "compatibility": required_pairs - executor.compatibility_pairs,
        "guidance": required_pairs - executor.guidance_pairs,
    }


def _evidence_messages(missing):
    messages = []
    if missing["details"]:
        messages.append(
            "Falten detalls dels exercicis seleccionats: "
            f"{sorted(missing['details'])}."
        )
    if missing["knowledge"]:
        messages.append(
            "Falta consultar el suport professional dels exercicis: "
            f"{sorted(missing['knowledge'])}."
        )
    if missing["compatibility"]:
        messages.append(
            "Falten comprovacions de compatibilitat exercici-participant: "
            f"{sorted(missing['compatibility'])}."
        )
    if missing["guidance"]:
        messages.append(
            "Falten guies de dosificació exercici-participant: "
            f"{sorted(missing['guidance'])}."
        )
    return messages


def _required_evidence_tool_calls(*, proposal, missing):
    calls = []
    if missing["details"]:
        calls.append(
            {
                "name": "get_exercise_details",
                "arguments": {
                    "exercise_revision_ids": sorted(missing["details"]),
                },
            }
        )
    knowledge_only = missing["knowledge"] - missing["details"]
    if knowledge_only:
        calls.append(
            {
                "name": "get_exercise_knowledge_support",
                "arguments": {
                    "exercise_revision_ids": sorted(knowledge_only),
                },
            }
        )
    if missing["compatibility"]:
        calls.append(
            {
                "name": "check_participant_compatibility",
                "arguments": {
                    "exercise_revision_ids": sorted(
                        {exercise_id for exercise_id, _ in missing["compatibility"]}
                    ),
                    "participant_plan_ids": sorted(
                        {participant_id for _, participant_id in missing["compatibility"]}
                    ),
                },
                "required_pairs": sorted([list(value) for value in missing["compatibility"]]),
            }
        )
    if missing["guidance"]:
        calls.append(
            {
                "name": "get_prescription_guidance",
                "arguments": {
                    "objective": proposal.request.objective.primary_quality,
                    "block_role": proposal.request.block_role,
                    "exercise_revision_ids": sorted(
                        {exercise_id for exercise_id, _ in missing["guidance"]}
                    ),
                    "participant_plan_ids": sorted(
                        {participant_id for _, participant_id in missing["guidance"]}
                    ),
                },
                "required_pairs": sorted([list(value) for value in missing["guidance"]]),
            }
        )
    return calls


def _validate_professional_knowledge_evidence(*, proposal, executor):
    """Ensure the model cites only exact claims returned by professional tools."""

    errors = []
    comparable_fields = (
        "exercise_revision_id",
        "phase_code",
        "claim_type",
        "action_code",
        "muscle_code",
        "basis_type",
        "basis_code",
        "expected_contraction",
        "verification_state",
    )
    for item in proposal.items:
        if item.dose is None or item.knowledge_support is None:
            continue
        support = item.knowledge_support
        for claim in support.claims:
            returned = executor.knowledge_claims.get(claim.claim_id)
            if returned is None:
                errors.append(
                    f"L'ítem {item.sequence_index} cita una afirmació professional "
                    f"no recuperada: {claim.claim_id}."
                )
                continue
            for field_name in comparable_fields:
                if getattr(claim, field_name) != returned.get(field_name, ""):
                    errors.append(
                        f"L'afirmació {claim.claim_id} altera el camp {field_name} "
                        "retornat per la base professional."
                    )
            if tuple(claim.evidence_codes) != tuple(returned.get("evidence_codes", [])):
                errors.append(
                    f"L'afirmació {claim.claim_id} altera les fonts professionals."
                )
            if tuple(claim.limitations) != tuple(returned.get("limitations", [])):
                errors.append(
                    f"L'afirmació {claim.claim_id} omet o altera les limitacions."
                )
    return errors


def _hydrate_professional_claims(*, final, executor):
    """Replace copied professional facts with the server-held canonical claims."""

    hydrated = 0
    for item in final.get("items", []):
        support = item.get("knowledge_support") or {}
        exact_claims = []
        for claim in support.get("claims", []):
            claim_id = claim.get("claim_id", "")
            exact = executor.knowledge_claims.get(claim_id)
            if exact is None:
                exact_claims.append(claim)
                continue
            exact_claims.append(dict(exact))
            hydrated += 1
        support["claims"] = exact_claims
        if support.get("status") == "grounded" and exact_claims:
            fragments = []
            for claim in exact_claims[:8]:
                phase = claim.get("phase_code") or "fase no especificada"
                if claim.get("claim_type") == "joint_action":
                    fact = f"acció {claim.get('action_code') or 'no especificada'}"
                else:
                    fact = (
                        f"{claim.get('muscle_code') or 'múscul no especificat'} "
                        f"({claim.get('expected_contraction') or 'indeterminada'})"
                    )
                fragments.append(f"{phase}: {fact}")
            suffix = "; …" if len(exact_claims) > 8 else ""
            support["summary"] = "Camins professionals recuperats: " + "; ".join(
                fragments
            ) + suffix
    return hydrated


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
    planning_enabled = getattr(
        settings, "OPENAI_TRAINING_PLANNING_BRIEF_ENABLED", True
    )
    request_hint = {
        "planned_duration_minutes": duration,
        "block_role": block_role,
        "active_participant_plan_ids": list(active_ids),
        "excluded_participant_plan_ids": list(excluded_ids),
        "coach_prompt": prompt,
        "coach_decisions": decisions,
        "previous_hard_constraints": list(
            ((previous_proposal or {}).get("request") or {}).get(
                "hard_constraints", []
            )
        ),
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
        require_planning=planning_enabled,
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
    initial_payload_bytes = planning_payload_bytes(initial)
    history = [
        {
            "role": "user",
            "content": json.dumps(initial, ensure_ascii=False, default=str),
        }
    ]
    model = getattr(settings, "OPENAI_TRAINING_MODEL", "gpt-5.6-luna")
    max_rounds = max(2, getattr(settings, "OPENAI_TRAINING_MAX_TOOL_ROUNDS", 20)) + (
        1 if planning_enabled else 0
    )
    max_calls = max(1, getattr(settings, "OPENAI_TRAINING_MAX_TOOL_CALLS", 50))
    max_repairs = max(0, getattr(settings, "OPENAI_TRAINING_MAX_REPAIRS", 2))
    max_evidence_rounds = max(
        0, getattr(settings, "OPENAI_TRAINING_MAX_EVIDENCE_ROUNDS", 3)
    )
    max_review_repairs = max(
        0, getattr(settings, "OPENAI_TRAINING_MAX_REVIEW_REPAIRS", 1)
    )
    max_live_history_bytes = max(
        20000,
        getattr(settings, "OPENAI_TRAINING_MAX_LIVE_HISTORY_BYTES", 100000),
    )
    max_rate_limit_retries = max(
        0, getattr(settings, "OPENAI_TRAINING_MAX_RATE_LIMIT_RETRIES", 2)
    )
    max_rate_limit_wait = max(
        1, getattr(settings, "OPENAI_TRAINING_MAX_RATE_LIMIT_WAIT_SECONDS", 60)
    )
    call_count = 0
    repairs = 0
    evidence_rounds = 0
    review_repairs = 0
    live_compactions = 0
    rate_limit_retries = 0
    response_ids = []
    usage = {"planner": {}, "reviewer": {}}
    validation_payload = {
        "attempts": [],
        "context_metrics": {
            "initial_payload_bytes": initial_payload_bytes,
            "planning_enabled": planning_enabled,
            "live_compactions": 0,
            "rate_limit_retries": 0,
        },
    }
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
        history_bytes = planning_payload_bytes(history)
        if (
            executor.planning_brief is not None
            and history_bytes > max_live_history_bytes
        ):
            history = _compact_live_history(
                initial=initial,
                executor=executor,
                context=context,
                active_ids=active_ids,
                excluded_ids=excluded_ids,
            )
            live_compactions += 1
            validation_payload["context_metrics"].update(
                {
                    "live_compactions": live_compactions,
                    "last_pre_compaction_bytes": history_bytes,
                    "last_post_compaction_bytes": planning_payload_bytes(history),
                }
            )
            emit(
                "compacting",
                "Compactant l'evidència acumulada abans de continuar…",
            )
        payload = {
            "model": model,
            "instructions": _instructions(),
            "input": list(history),
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
                if (
                    (planning_enabled or tool.get("name") != "submit_block_planning_brief")
                    and (
                        tool.get("name") != "audit_block_draft"
                        or executor.audit_calls < 2
                    )
                )
            ],
            "tool_choice": (
                {"type": "function", "name": "submit_block_planning_brief"}
                if planning_enabled and executor.planning_brief is None
                else {"type": "function", "name": "search_exercises"}
                if not planning_enabled and round_index == 0
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
        while True:
            try:
                data = _post_responses_api(payload)
                break
            except OpenAITrainingRateLimited as error:
                if rate_limit_retries >= max_rate_limit_retries:
                    exhausted = runtime_error(str(error))
                    exhausted.code = "openai_rate_limited"
                    raise exhausted from error
                requested_wait = error.retry_after_seconds + 0.5
                if requested_wait > max_rate_limit_wait:
                    exhausted = runtime_error(
                        "El límit d'OpenAI requereix esperar massa temps per a aquesta run: "
                        f"{requested_wait:.1f} segons."
                    )
                    exhausted.code = "openai_rate_limited"
                    raise exhausted from error
                rate_limit_retries += 1
                history = _compact_live_history(
                    initial=initial,
                    executor=executor,
                    context=context,
                    active_ids=active_ids,
                    excluded_ids=excluded_ids,
                )
                payload["input"] = list(history)
                validation_payload["context_metrics"].update(
                    {
                        "rate_limit_retries": rate_limit_retries,
                        "rate_limit_retry_payload_bytes": planning_payload_bytes(
                            history
                        ),
                    }
                )
                emit(
                    "rate_limited",
                    (
                        "OpenAI ha limitat temporalment la run; reintent automàtic "
                        f"{rate_limit_retries}/{max_rate_limit_retries} en "
                        f"{requested_wait:.1f} segons…"
                    ),
                )
                time.sleep(requested_wait)
        actual_model = data.get("model") or actual_model
        if data.get("id"):
            response_ids.append(data["id"])
        _usage_total(usage, data.get("usage"))
        _usage_total(usage["planner"], data.get("usage"))
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
                    if tool_name == "search_professional_concepts":
                        emit(
                            "knowledge",
                            (
                                "Base professional consultada: "
                                f"{len(result.get('results', []))} conceptes validats."
                            ),
                        )
                    elif tool_name == "submit_block_planning_brief":
                        emit(
                            "planning",
                            "Pla previ validat; iniciant la cerca de solucions…",
                            planning_payload=dict(executor.planning_brief or {}),
                        )
                    elif tool_name == "get_participant_context":
                        emit(
                            "context",
                            "Ampliant només el context individual necessari…",
                        )
                    elif tool_name == "get_group_training_summary":
                        emit("context", "Actualitzant el resum factual del grup…")
                    elif tool_name == "search_exercises":
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
                    elif tool_name == "get_exercise_knowledge_support":
                        emit(
                            "knowledge",
                            (
                                "Verificant el fonament professional de "
                                f"{len(result.get('results', []))} exercicis…"
                            ),
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
        proposal = None
        review_required = False
        review_issues = []
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
            if planning_enabled and executor.planning_brief is None:
                raise ValidationError("L'agent no ha registrat el pla previ obligatori.")
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
            hydrated_claims = _hydrate_professional_claims(
                final=final,
                executor=executor,
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
            missing_evidence = _missing_tool_evidence(
                proposal=proposal, executor=executor
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
            alignment_errors = proposal_alignment_errors(
                brief=executor.planning_brief,
                proposal=proposal,
            )
            if alignment_errors:
                raise ValidationError(alignment_errors)
            evidence_messages = _evidence_messages(missing_evidence)
            if evidence_messages:
                required_tool_calls = _required_evidence_tool_calls(
                    proposal=proposal, missing=missing_evidence
                )
                validation_payload.setdefault("evidence_attempts", []).append(
                    {
                        "complete": False,
                        "missing": {
                            "details": sorted(missing_evidence["details"]),
                            "knowledge": sorted(missing_evidence["knowledge"]),
                            "compatibility": sorted(
                                [list(value) for value in missing_evidence["compatibility"]]
                            ),
                            "guidance": sorted(
                                [list(value) for value in missing_evidence["guidance"]]
                            ),
                        },
                        "required_tool_calls": required_tool_calls,
                    }
                )
                if evidence_rounds >= max_evidence_rounds:
                    raise runtime_error(
                        "L'agent no ha completat l'evidència obligatòria: "
                        + "; ".join(evidence_messages)
                    )
                evidence_rounds += 1
                emit(
                    "evidence",
                    (
                        "Completant conjuntament detalls, compatibilitat i guies "
                        f"({evidence_rounds}/{max_evidence_rounds})…"
                    ),
                    validation_errors=evidence_messages,
                )
                history = _compact_repair_history(
                    initial=initial,
                    final=final,
                    errors=evidence_messages,
                    executor=executor,
                    context=context,
                    active_ids=active_ids,
                    excluded_ids=excluded_ids,
                    proposal=proposal,
                    source="tool_evidence",
                    required_tool_calls=required_tool_calls,
                )
                continue
            knowledge_errors = _validate_professional_knowledge_evidence(
                proposal=proposal, executor=executor
            )
            if knowledge_errors:
                raise ValidationError(knowledge_errors)
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
                    request_context=initial,
                )
                if review_data.get("id"):
                    response_ids.append(review_data["id"])
                _usage_total(usage, review_data.get("usage"))
                _usage_total(usage["reviewer"], review_data.get("usage"))
                usage["reviewer_model"] = review_data.get("model") or getattr(
                    settings, "OPENAI_TRAINING_REVIEW_MODEL", model
                )
                validation_payload["context_metrics"][
                    "reviewer_rate_limit_retries"
                ] = int(review_data.get("iatrain_rate_limit_retries", 0) or 0)
                validation_payload.setdefault("review_attempts", []).append(
                    independent_review
                )
                if independent_review["verdict"] == "needs_clarification":
                    question = independent_review.get("clarification_question") or (
                        "El revisor recomana completar informació abans d'aplicar el bloc."
                    )
                    review_required = True
                    review_issues = independent_review.get("issues", []) or [
                        {
                            "code": "REVIEWER-CONTEXT-UNCERTAINTY",
                            "severity": "error",
                            "message": question,
                            "correction": (
                                "Revisa la proposta prudent i completa el perfil quan sigui "
                                "possible; la dada absent no bloqueja la previsualització."
                            ),
                            "participant_plan_ids": [],
                            "sequence_indices": [],
                            "exercise_revision_ids": [],
                        }
                    ]
                if independent_review["verdict"] == "revise":
                    material_issues = [
                        row
                        for row in independent_review.get("issues", [])
                        if row.get("severity") in {"critical", "error"}
                    ]
                    review_messages = [
                        f"Revisor {row.get('code', 'semantic')}: "
                        f"{row.get('message', '')} Correcció: "
                        f"{row.get('correction', '')}"
                        for row in material_issues
                    ]
                    if material_issues and review_repairs < max_review_repairs:
                        review_repairs += 1
                        emit(
                            "repairing",
                            (
                                "Revisió independent: corregint incidències "
                                f"({review_repairs}/{max_review_repairs})…"
                            ),
                            validation_errors=review_messages[:3],
                        )
                        history = _compact_repair_history(
                            initial=initial,
                            final=final,
                            errors=review_messages,
                            executor=executor,
                            context=context,
                            active_ids=active_ids,
                            excluded_ids=excluded_ids,
                            proposal=proposal,
                            source="independent_reviewer",
                        )
                        continue
                    critical_issues = [
                        row for row in material_issues
                        if row.get("severity") == "critical"
                    ]
                    if critical_issues:
                        raise runtime_error(
                            "La proposta conserva un risc crític després de la revisió: "
                            + "; ".join(review_messages[:3])
                        )
                    if material_issues:
                        review_required = True
                        review_issues = material_issues
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
            history = _compact_repair_history(
                initial=initial,
                final=final,
                errors=messages,
                executor=executor,
                context=context,
                active_ids=active_ids,
                excluded_ids=excluded_ids,
                proposal=proposal,
                source="server_validation",
            )
            continue
        validation_payload["attempts"].append({"valid": True, "errors": []})
        validation_payload["allowed_exercise_revision_ids"] = sorted(
            executor.allowed_exercise_ids
        )
        validation_payload["last_timing"] = executor.last_timing
        validation_payload["independent_review"] = independent_review
        validation_payload["review_required"] = review_required
        validation_payload["review_issues"] = list(review_issues)
        validation_payload["planning"] = {
            "contract_version": (
                executor.planning_brief or {}
            ).get("contract_version", ""),
            "accepted": bool(executor.planning_brief),
            "alignment_valid": True,
        }
        validation_payload["context_metrics"].update(
            {
                "tool_result_bytes": sum(
                    int(row.get("result_bytes", 0) or 0)
                    for row in executor.trace
                ),
                "participant_context_calls": len(
                    executor.participant_context_calls
                ),
                "group_context_calls": executor.group_context_calls,
            }
        )
        cited_claim_ids = {
            claim.claim_id
            for item in proposal.items
            if item.knowledge_support is not None
            for claim in item.knowledge_support.claims
        }
        cited_evidence_codes = {
            code
            for item in proposal.items
            if item.knowledge_support is not None
            for claim in item.knowledge_support.claims
            for code in claim.evidence_codes
        }
        validation_payload["professional_knowledge"] = {
            "exercise_revision_ids": sorted(executor.knowledge_exercise_ids),
            "retrieved_claim_ids": sorted(executor.knowledge_claims),
            "cited_claim_ids": sorted(cited_claim_ids),
            "sources": [
                source
                for code, source in executor.knowledge_sources.items()
                if code in cited_evidence_codes
            ],
            "professional_concept_searches": executor.professional_concept_calls,
            "server_hydrated_claims": hydrated_claims,
        }
        if evidence_rounds:
            validation_payload.setdefault("evidence_attempts", []).append(
                {"complete": True, "missing": {}, "required_tool_calls": []}
            )
        validation_payload["repair_counts"] = {
            "server": repairs,
            "evidence": evidence_rounds,
            "reviewer": review_repairs,
        }
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
        emit(
            "completed",
            (
                "Proposta preparada; requereix revisió de l'entrenador."
                if review_required
                else "Proposta preparada i validada."
            ),
        )
        return AgentBlockResult(
            proposal=proposal,
            interpretation_payload=interpretation,
            planning_payload=dict(executor.planning_brief or {}),
            model_name=actual_model,
            tool_trace=tuple(executor.trace),
            response_ids=tuple(response_ids),
            usage_payload=usage,
            validation_payload=validation_payload,
            review_required=review_required,
            review_issues=tuple(review_issues),
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
