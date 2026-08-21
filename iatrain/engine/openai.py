"""OpenAI Responses API boundary for natural-language block interpretation."""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

from iatrain.models import TrainingBlock
from iatrain_exercises.models import ExerciseObjective, ExerciseRevision

from .contracts import (
    PHYSICAL_BLOCK_HARD_CONSTRAINTS,
    TARGET_INTENSITIES,
    BlockGenerationRequest,
    BlockObjective,
)
from .validation import validate_block_generation_request


PROMPT_VERSION = "physical-block-interpreter-1.0"
class OpenAITrainingError(Exception):
    code = "openai_error"


class OpenAITrainingNotConfigured(OpenAITrainingError):
    code = "openai_not_configured"


class OpenAITrainingUnavailable(OpenAITrainingError):
    code = "openai_unavailable"


class InterpretationNeedsClarification(OpenAITrainingError):
    code = "clarification_needed"

    def __init__(self, question, *, payload=None):
        super().__init__(question)
        self.question = question
        self.payload = payload or {}


@dataclass(frozen=True, slots=True)
class InterpretedBlockRequest:
    request: BlockGenerationRequest
    payload: dict
    source_references: tuple[dict, ...]
    model_name: str


def _schema():
    string_array = lambda enum=None: {
        "type": "array",
        "items": {"type": "string", **({"enum": list(enum)} if enum else {})},
    }
    request_properties = {
        "name": {"type": "string"},
        "block_role": {"type": "string", "enum": list(TrainingBlock.Role.values)},
        "planned_duration_minutes": {"type": "integer", "minimum": 1, "maximum": 180},
        "execution_mode": {"type": "string", "enum": list(TrainingBlock.ExecutionMode.values)},
        "objective_description": {"type": "string"},
        "primary_quality": {"type": "string", "enum": list(ExerciseObjective.Objective.values)},
        "secondary_qualities": string_array(ExerciseObjective.Objective.values),
        "movement_patterns": string_array(ExerciseRevision.MovementPattern.values),
        "body_region_codes": string_array(),
        "target_intensity": {"type": "string", "enum": list(TARGET_INTENSITIES)},
        "hard_constraints": string_array(PHYSICAL_BLOCK_HARD_CONSTRAINTS),
        "preferences": string_array(),
        "instructions": {"type": "string"},
        "rounds": {"type": "integer", "minimum": 1, "maximum": 20},
        "rest_between_rounds_seconds": {"type": "integer", "minimum": 0, "maximum": 900},
    }
    source_properties = {
        "title": {"type": "string"},
        "url": {"type": "string"},
        "applicability": {"type": "string"},
    }
    properties = {
        "clarification_needed": {"type": "boolean"},
        "clarification_question": {"type": "string"},
        "reasoning_summary": {"type": "string"},
        "request": {
            "type": "object",
            "properties": request_properties,
            "required": list(request_properties),
            "additionalProperties": False,
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": source_properties,
                "required": list(source_properties),
                "additionalProperties": False,
            },
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _response_output_text(data):
    fragments = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    fragments.append(text)
    return "\n".join(fragments).strip()


def _safe_sources(rows):
    sources = []
    for row in rows:
        url = str(row.get("url", "")).strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            url = ""
        sources.append(
            {
                "title": str(row.get("title", "")).strip()[:240],
                "url": url,
                "applicability": str(row.get("applicability", "")).strip()[:1000],
            }
        )
    return sources


def _call_responses_api(*, instructions, user_input):
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise OpenAITrainingNotConfigured(
            "Configura OPENAI_API_KEY per activar la generació automàtica."
        )
    model = getattr(settings, "OPENAI_TRAINING_MODEL", "gpt-5.6")
    payload = {
        "model": model,
        "instructions": instructions,
        "input": [{"role": "user", "content": user_input}],
        "reasoning": {
            "effort": getattr(settings, "OPENAI_TRAINING_REASONING_EFFORT", "medium")
        },
        "store": False,
        "max_output_tokens": 3500,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "iatrain_physical_block_request",
                "strict": True,
                "schema": _schema(),
            }
        },
    }
    if getattr(settings, "OPENAI_TRAINING_WEB_SEARCH", True):
        payload["tools"] = [{"type": "web_search"}]
        payload["tool_choice"] = "auto"
        payload["include"] = ["web_search_call.action.sources"]
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
            timeout=getattr(settings, "OPENAI_TRAINING_TIMEOUT_SECONDS", 90),
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="ignore"))
            message = detail.get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        raise OpenAITrainingUnavailable(
            "OpenAI no ha pogut completar la interpretació"
            + (f": {message[:180]}" if message else ".")
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OpenAITrainingUnavailable(
            "No s'ha pogut contactar amb OpenAI. Torna-ho a provar."
        ) from exc
    text = _response_output_text(data)
    if not text:
        raise OpenAITrainingUnavailable("OpenAI no ha retornat una interpretació utilitzable.")
    try:
        return json.loads(text), model
    except json.JSONDecodeError as exc:
        raise OpenAITrainingUnavailable("La resposta d'OpenAI no compleix el contracte.") from exc


def _athlete_summary(context):
    rows = []
    for athlete in context.athletes:
        payload = athlete.payload
        rows.append(
            {
                "participant_plan_id": athlete.participant_plan_id,
                "age_years": payload.get("athlete", {}).get("age_years"),
                "population_stage": athlete.prescription_profile.population_stage,
                "experience_level": athlete.prescription_profile.experience_level,
                "training_years": (
                    str(athlete.prescription_profile.training_years)
                    if athlete.prescription_profile.training_years is not None
                    else None
                ),
                "sport_profiles": payload.get("sport_profiles", []),
                "active_conditions": payload.get("active_conditions", []),
                "confirmed_insights": payload.get("confirmed_insights", []),
                "current_observations": payload.get("current_observations", [])[:8],
                "recent_training_responses": payload.get("recent_training_responses", [])[:12],
                "health_data_available": payload.get("scope", {}).get(
                    "health_data_available", False
                ),
            }
        )
    return rows


def _instructions():
    return """
Ets la capa d'interpretació professional d'IA Train per a blocs de preparació física.
Transforma la petició de l'entrenador en el contracte estructurat indicat. No seleccionis
exercicis ni inventis identificadors: un motor determinista consultarà el catàleg després.

Raona sobre edat cronològica, etapa de desenvolupament, experiència real d'entrenament,
nivell competitiu, condicions actives, càrrega recent, objectiu, temps i material. Un infant
d'alt rendiment pot ser avançat; un adult sedentari és inicial. No confonguis edat i nivell.

Fes servir la cerca web per contrastar orientacions de dosificació quan sigui rellevant.
Prioritza posicionaments d'ACSM/NSCA/IOC, federacions, consensos i literatura revisada per
parells. Retorna fonts concretes i explica breument l'aplicabilitat; no presentis una font
d'adults sans com si fos específica per infants. No diagnostiquis ni prescriguis tractament.

Només usa les hard_constraints canòniques disponibles. Les altres instruccions van a
preferences o instructions. Demana aclariment únicament si falta una dada que impedeix una
proposta segura. reasoning_summary és una justificació breu i visible, no una cadena de
pensament interna. Escriu en català.
""".strip()


def interpret_block_prompt(
    *, context, prompt, duration_minutes, block_role, previous_payload=None, refinement=""
):
    revision = context.revision
    remaining = revision.planned_duration_minutes - sum(
        revision.blocks.values_list("planned_duration_minutes", flat=True)
    )
    session_payload = {
        "session": {
            "discipline": revision.session.discipline,
            "planned_duration_minutes": revision.planned_duration_minutes,
            "remaining_duration_minutes": remaining,
            "general_objective": revision.general_objective,
            "goals": [
                {
                    "domain": goal.domain,
                    "description": goal.description,
                    "priority": goal.priority,
                }
                for goal in revision.goals.all()
            ],
            "existing_blocks": [
                {
                    "name": block.name,
                    "role": block.block_role,
                    "objective": block.objective,
                    "duration_minutes": block.planned_duration_minutes,
                }
                for block in revision.blocks.all()
            ],
        },
        "fixed_hints": {
            "duration_minutes": duration_minutes,
            "block_role": block_role,
        },
        "available_equipment_codes": sorted(context.available_equipment_codes),
        "athletes": _athlete_summary(context),
        "coach_prompt": prompt,
    }
    if previous_payload:
        session_payload["previous_interpretation"] = previous_payload
        session_payload["refinement_instruction"] = refinement
    interpreted, model = _call_responses_api(
        instructions=_instructions(),
        user_input=json.dumps(session_payload, ensure_ascii=False, default=str),
    )
    if interpreted.get("clarification_needed"):
        question = interpreted.get("clarification_question") or "Cal concretar la petició."
        raise InterpretationNeedsClarification(question, payload=interpreted)
    interpreted["sources"] = _safe_sources(interpreted.get("sources", []))
    row = interpreted["request"]
    # Duration and ownership-sensitive identifiers remain server-authoritative.
    duration = min(int(row["planned_duration_minutes"]), int(duration_minutes), remaining)
    if duration < 1:
        raise ValidationError("La sessió no té temps disponible per a un altre bloc.")
    request = BlockGenerationRequest(
        session_revision_id=revision.pk,
        sequence_index=(
            max(revision.blocks.values_list("sequence_index", flat=True), default=0) + 1
        ),
        name=row["name"].strip()[:160],
        block_role=block_role,
        planned_duration_minutes=duration,
        objective=BlockObjective(
            description=row["objective_description"].strip(),
            primary_quality=row["primary_quality"],
            secondary_qualities=tuple(dict.fromkeys(row["secondary_qualities"])),
            movement_patterns=tuple(dict.fromkeys(row["movement_patterns"])),
            body_region_codes=tuple(dict.fromkeys(row["body_region_codes"])),
        ),
        participant_plan_ids=tuple(
            revision.participant_plans.values_list("pk", flat=True)
        ),
        execution_mode=row["execution_mode"],
        target_intensity=row["target_intensity"],
        available_equipment_ids=context.available_equipment_ids,
        hard_constraints=tuple(dict.fromkeys(row["hard_constraints"])),
        preferences=tuple(dict.fromkeys(row["preferences"])),
        instructions=row["instructions"],
        rounds=row["rounds"],
        rest_between_rounds_seconds=row["rest_between_rounds_seconds"],
    )
    validate_block_generation_request(request, revision=revision)
    return InterpretedBlockRequest(
        request=request,
        payload=interpreted,
        source_references=tuple(interpreted["sources"]),
        model_name=model,
    )
