"""Pre-search planning contract and deterministic alignment checks."""

import json
import re

from django.core.exceptions import ValidationError

from iatrain_exercises.models import ExerciseRevision

from .contracts import PHYSICAL_BLOCK_HARD_CONSTRAINTS, TARGET_INTENSITIES


PLANNING_CONTRACT_VERSION = "1.1"
COVERAGE_MODES = ("focused", "full_body", "upper_body", "lower_body", "mixed")
COVERAGE_DOMAINS = ("lower_body", "upper_body", "trunk")

DOMAIN_PATTERNS = {
    "lower_body": {"squat", "hinge", "ankle_dominant", "locomotion"},
    "upper_body": {
        "horizontal_push",
        "vertical_push",
        "horizontal_pull",
        "vertical_pull",
    },
    "trunk": {"trunk_control"},
}

PATTERN_PROMPT_TOKENS = {
    "squat": ("squat", "esquat"),
    "hinge": ("hinge", "frontissa"),
    "ankle_dominant": ("ankle dominant", "dominant de turmell"),
    "locomotion": ("locomocio", "locomoció", "desplacament", "desplaçament"),
    "horizontal_push": ("horizontal push", "empenta horitzontal"),
    "vertical_push": ("vertical push", "empenta vertical"),
    "horizontal_pull": ("horizontal pull", "traccio horitzontal", "tracció horitzontal"),
    "vertical_pull": ("vertical pull", "traccio vertical", "tracció vertical"),
    "trunk_control": ("trunk control", "control del tronc"),
}

HARD_CONSTRAINT_PROMPT_TOKENS = {
    "validated_only": ("nomes validats", "només validats", "validated only"),
    "bodyweight_only": ("nomes pes corporal", "només pes corporal", "bodyweight only"),
    "no_equipment": ("sense material", "sense equipament", "no equipment"),
    "no_jumps": ("sense salts", "no salts", "no jumps"),
    "no_impact": ("sense impacte", "no impact"),
    "avoid_high_impact": ("evita impacte alt", "evitar impacte alt", "avoid high impact"),
    "avoid_failure": ("evita la fallada", "sense arribar a la fallada", "avoid failure"),
}


def planning_brief_schema():
    """Strict tool argument schema for a concise, auditable planning brief."""

    def array(items):
        return {"type": "array", "items": items}

    def obj(properties):
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    scoped_preference = obj(
        {
            "statement": {"type": "string"},
            "source": {
                "type": "string",
                "enum": [
                    "coach_prompt",
                    "session_goal",
                    "coach_decision",
                    "planning_inference",
                ],
            },
        }
    )
    individual_priority = obj(
        {
            "participant_plan_id": {"type": "integer"},
            "condition_ids": array({"type": "integer"}),
            "laterality": {
                "type": "string",
                "enum": ["", "left", "right", "bilateral", "not_applicable"],
            },
            "requirement": {"type": "string"},
        }
    )
    return obj(
        {
            "contract_version": {
                "type": "string",
                "enum": [PLANNING_CONTRACT_VERSION],
            },
            "objective_summary": {"type": "string"},
            "success_criteria": array({"type": "string"}),
            "coverage_mode": {"type": "string", "enum": list(COVERAGE_MODES)},
            "required_coverage_domains": array(
                {"type": "string", "enum": list(COVERAGE_DOMAINS)}
            ),
            "required_movement_patterns": array(
                {
                    "type": "string",
                    "enum": list(ExerciseRevision.MovementPattern.values),
                }
            ),
            "preferred_movement_patterns": array(
                {
                    "type": "string",
                    "enum": list(ExerciseRevision.MovementPattern.values),
                }
            ),
            "target_intensity": {
                "type": "string",
                "enum": list(TARGET_INTENSITIES),
            },
            "load_strategy": {"type": "string"},
            "time_budget_seconds": {"type": "integer", "minimum": 60},
            "shared_strategy": {"type": "string"},
            "individual_priorities": array(individual_priority),
            "global_hard_constraints": array(
                {
                    "type": "string",
                    "enum": list(PHYSICAL_BLOCK_HARD_CONSTRAINTS),
                }
            ),
            "global_preferences": array(scoped_preference),
            "professional_queries": array({"type": "string"}),
            "search_strategy": array({"type": "string"}),
            "uncertainties": array({"type": "string"}),
        }
    )


def _normalized_text(value):
    text = re.sub(r"[-_/]+", " ", str(value or "").strip().casefold())
    return re.sub(r"\s+", " ", text)


def _looks_full_body(prompt):
    text = _normalized_text(prompt)
    return any(
        token in text
        for token in ("full body", "cos sencer", "tot el cos", "cos complet")
    )


def _explicit_prompt_patterns(prompt):
    text = _normalized_text(prompt)
    return {
        code
        for code, tokens in PATTERN_PROMPT_TOKENS.items()
        if any(_normalized_text(token) in text for token in tokens)
    }


def authorized_hard_constraints(request_hint):
    """Only the coach/current proposal can create hard constraints."""

    text = _normalized_text(request_hint.get("coach_prompt"))
    authorized = {
        code
        for code, tokens in HARD_CONSTRAINT_PROMPT_TOKENS.items()
        if any(_normalized_text(token) in text for token in tokens)
    }
    authorized.update(request_hint.get("previous_hard_constraints", []))
    decisions = request_hint.get("coach_decisions", {}) or {}
    if decisions.get("catalog_drafts") == "allow_draft_exercises":
        authorized.discard("validated_only")
    return authorized


def validate_planning_brief(brief, *, context, request_hint):
    if not isinstance(brief, dict):
        raise ValidationError("El pla previ ha de ser un objecte JSON.")
    required = set(planning_brief_schema()["required"])
    missing = sorted(required - set(brief))
    if missing:
        raise ValidationError(f"Falten camps obligatoris del pla previ: {missing}.")
    if brief.get("contract_version") != PLANNING_CONTRACT_VERSION:
        raise ValidationError("La versió del pla previ no és compatible.")
    if not _normalized_text(brief.get("objective_summary")):
        raise ValidationError("El pla previ necessita un objectiu explícit.")
    if not brief.get("success_criteria"):
        raise ValidationError("El pla previ necessita criteris d'èxit.")
    if not brief.get("search_strategy"):
        raise ValidationError("El pla previ necessita una estratègia de cerca.")
    expected_seconds = int(request_hint["planned_duration_minutes"]) * 60
    if int(brief.get("time_budget_seconds", 0)) != expected_seconds:
        raise ValidationError(
            f"El pressupost del pla ha de ser exactament {expected_seconds} segons."
        )
    if _looks_full_body(request_hint.get("coach_prompt")):
        if brief.get("coverage_mode") != "full_body":
            raise ValidationError("La petició de cos sencer requereix coverage_mode=full_body.")
        required_domains = set(COVERAGE_DOMAINS)
        declared = set(brief.get("required_coverage_domains", []))
        if not required_domains.issubset(declared):
            raise ValidationError(
                "Un pla full body ha d'exigir tren inferior, tren superior i tronc."
            )
    required_patterns = set(brief.get("required_movement_patterns", []))
    explicit_patterns = _explicit_prompt_patterns(request_hint.get("coach_prompt"))
    invented_patterns = required_patterns - explicit_patterns
    if invented_patterns:
        raise ValidationError(
            "Els patrons obligatoris només poden venir explícitament de la petició; "
            f"passa aquests patrons a preferits: {sorted(invented_patterns)}."
        )
    hard_constraints = set(brief.get("global_hard_constraints", []))
    unauthorized_hard = hard_constraints - authorized_hard_constraints(request_hint)
    if unauthorized_hard:
        raise ValidationError(
            "El pla ha convertit preferències prudents en restriccions dures no "
            f"autoritzades: {sorted(unauthorized_hard)}."
        )
    active_ids = set(request_hint.get("active_participant_plan_ids", []))
    athletes = {
        row.participant_plan_id: row
        for row in context.athletes
        if row.participant_plan_id in active_ids
    }
    seen = set()
    for priority in brief.get("individual_priorities", []):
        participant_id = int(priority.get("participant_plan_id", 0))
        if participant_id not in athletes:
            raise ValidationError(
                f"La prioritat individual referencia un participant no actiu: {participant_id}."
            )
        if participant_id in seen:
            raise ValidationError(
                f"El participant {participant_id} no es pot repetir al pla previ."
            )
        seen.add(participant_id)
        active_conditions = {
            int(row["id"]): row
            for row in athletes[participant_id].payload.get("active_conditions", [])
            if row.get("id")
        }
        unknown = set(priority.get("condition_ids", [])) - set(active_conditions)
        if unknown:
            raise ValidationError(
                f"El pla referencia condicions no actives del participant {participant_id}: "
                f"{sorted(unknown)}."
            )
        declared_laterality = priority.get("laterality", "")
        condition_lateralities = {
            active_conditions[value].get("laterality", "")
            for value in priority.get("condition_ids", [])
        }
        condition_lateralities.discard("")
        if (
            declared_laterality
            and condition_lateralities
            and declared_laterality not in condition_lateralities
        ):
            raise ValidationError(
                f"La lateralitat de la prioritat del participant {participant_id} "
                "no coincideix amb les condicions referenciades."
            )
    return brief


def proposal_alignment_errors(*, brief, proposal):
    """Compare the selected proposal with the accepted pre-search outcomes."""

    if not brief:
        return []
    errors = []
    if proposal.request.target_intensity != brief.get("target_intensity"):
        errors.append("La intensitat final no coincideix amb el pla previ acceptat.")
    missing_hard = set(brief.get("global_hard_constraints", [])) - set(
        proposal.request.hard_constraints
    )
    if missing_hard:
        errors.append(
            "La proposta ha perdut restriccions globals del pla: "
            f"{sorted(missing_hard)}."
        )
    unexpected_hard = set(proposal.request.hard_constraints) - set(
        brief.get("global_hard_constraints", [])
    )
    if unexpected_hard:
        errors.append(
            "La proposta ha afegit restriccions dures que no constaven al pla "
            f"autoritzat: {sorted(unexpected_hard)}."
        )
    exercise_ids = [
        item.dose.exercise_revision_id
        for item in proposal.items
        if item.dose is not None
    ]
    revisions = {
        row.pk: row
        for row in ExerciseRevision.objects.filter(pk__in=exercise_ids)
    }
    actual_patterns = {
        revisions[value].movement_pattern
        for value in exercise_ids
        if value in revisions
    }
    missing_patterns = set(brief.get("required_movement_patterns", [])) - actual_patterns
    if missing_patterns:
        errors.append(
            "La proposta no cobreix els patrons obligatoris del pla: "
            f"{sorted(missing_patterns)}."
        )
    actual_domains = {
        domain
        for domain, patterns in DOMAIN_PATTERNS.items()
        if actual_patterns & patterns
    }
    missing_domains = set(brief.get("required_coverage_domains", [])) - actual_domains
    if missing_domains:
        errors.append(
            "La proposta no cobreix els dominis obligatoris del pla: "
            f"{sorted(missing_domains)}."
        )
    side_tokens = ("cada costat", "per costat", "cada banda", "per banda", "total")
    for item in proposal.items:
        if item.dose is None:
            continue
        revision = revisions.get(item.dose.exercise_revision_id)
        if revision is None or revision.laterality not in {"unilateral", "alternating"}:
            continue
        operational_text = _normalized_text(
            f"{item.instructions} {item.dose.execution_notes}"
        )
        if not any(token in operational_text for token in side_tokens):
            errors.append(
                f"L'ítem {item.sequence_index} és unilateral o alternant: cal indicar "
                "si la dosi és per costat o total."
            )
    return errors


def planning_payload_bytes(payload):
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
