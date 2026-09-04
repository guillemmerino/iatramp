"""Read-only, tenant-scoped tools exposed to the training planning agent."""

import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q

from iatrain_exercises.models import (
    ExerciseEquipmentRequirement,
    ExerciseObjective,
    ExerciseRevision,
)
from iatrain_exercises.knowledge import (
    PROFESSIONAL_CONCEPT_KINDS,
    build_exercise_knowledge_support,
    search_professional_concepts,
)
from iatrain_motion.models import EditorialStatus

from .guidelines import resolve_guideline
from .context import build_group_engine_summary
from .planning import planning_brief_schema, validate_planning_brief
from .scoring import (
    OBJECTIVE_MODALITIES,
    PATTERN_REGIONS,
    condition_applicability,
    condition_applies,
)
from .serialization import proposal_from_payload, proposal_payload_from_agent_output
from .validation import validate_block_generation_proposal


TOOL_VERSION = "training-agent-tools-1.9"


def _nullable(type_name):
    return {"type": [type_name, "null"]}


def _object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def tool_definitions():
    """Return strict Responses API function definitions."""

    return [
        {
            "type": "function",
            "name": "submit_block_planning_brief",
            "description": (
                "Registra el pla de resultats abans de consultar el catàleg. No incloguis "
                "exercicis ni identificadors de revisions: defineix objectiu, cobertura, "
                "càrrega, temps, abast de restriccions i estratègia de cerca."
            ),
            "strict": True,
            "parameters": planning_brief_schema(),
        },
        {
            "type": "function",
            "name": "get_participant_context",
            "description": (
                "Amplia sota demanda el context d'una participant activa. Usa-la només "
                "quan el resum inicial no sigui suficient per personalitzar o dosificar."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "participant_plan_id": {"type": "integer"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "sport_profiles",
                                "conditions",
                                "observations",
                                "training_responses",
                                "measurements",
                                "insights",
                            ],
                        },
                    },
                }
            ),
        },
        {
            "type": "function",
            "name": "get_group_training_summary",
            "description": (
                "Recupera de nou el resum factual del grup actiu: heterogeneïtat, "
                "condicions, disponibilitat de salut i activitat recent."
            ),
            "strict": True,
            "parameters": _object({}),
        },
        {
            "type": "function",
            "name": "search_professional_concepts",
            "description": (
                "Resol objectius anatòmics o biomecànics en conceptes validats de la "
                "base professional. Usa-la per peticions sobre moviments, articulacions, "
                "músculs, grups musculars o tipus de contracció abans de filtrar exercicis."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "query": {"type": "string"},
                    "kinds": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(PROFESSIONAL_CONCEPT_KINDS),
                        },
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                }
            ),
        },
        {
            "type": "function",
            "name": "search_exercises",
            "description": (
                "Cerca variants reals del catàleg privat. Retorna el recompte total, "
                "candidats paginats i consideracions factuals; no decideix quins escollir."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "query": {"type": "string"},
                    "objective": {
                        "type": "string",
                        "enum": ["", *ExerciseObjective.Objective.values],
                    },
                    "movement_patterns": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(ExerciseRevision.MovementPattern.values),
                        },
                    },
                    "modalities": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(ExerciseRevision.Modality.values),
                        },
                    },
                    "difficulties": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(ExerciseRevision.Difficulty.values),
                        },
                    },
                    "action_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "muscle_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "expected_contractions": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "concentric", "eccentric", "isometric",
                                "variable", "indeterminate",
                            ],
                        },
                    },
                    "equipment_mode": {
                        "type": "string",
                        "enum": ["available_only", "bodyweight_only", "any"],
                    },
                    "validated_only": {"type": "boolean"},
                    "participant_plan_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                }
            ),
        },
        {
            "type": "function",
            "name": "get_exercise_details",
            "description": (
                "Obté descripció, execució, seguretat, objectius i restriccions dels "
                "candidats retornats. És compacte i no repeteix els claims professionals."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "exercise_revision_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                        "maxItems": 8,
                    }
                }
            ),
        },
        {
            "type": "function",
            "name": "get_exercise_knowledge_support",
            "description": (
                "Recupera de nou, de manera explícita, els camins professionals validats "
                "d'exercicis ja retornats: fase, acció, múscul, funció, contracció, "
                "verificació, fonts i limitacions. Crida-la una sola vegada per finalista."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "exercise_revision_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                        "maxItems": 8,
                    }
                }
            ),
        },
        {
            "type": "function",
            "name": "get_prescription_guidance",
            "description": (
                "Retorna envolupants de dosificació professionals per exercici i participant. "
                "Són orientacions; la dosi final la decideix l'agent."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "exercise_revision_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "participant_plan_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                    },
                    "objective": {
                        "type": "string",
                        "enum": list(ExerciseObjective.Objective.values),
                    },
                    "block_role": {
                        "type": "string",
                        "enum": ["preparation", "main", "complementary", "recovery", "assessment"],
                    },
                }
            ),
        },
        {
            "type": "function",
            "name": "check_participant_compatibility",
            "description": (
                "Comprova fets de compatibilitat entre candidats i participants: condicions "
                "stop/avoid/modify/monitor i respostes recents. No substitueix el criteri de l'agent."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "exercise_revision_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "participant_plan_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                    },
                }
            ),
        },
        {
            "type": "function",
            "name": "find_compatible_alternatives",
            "description": (
                "Busca substitucions reals per a un exercici i una participant concreta. "
                "Conserva sempre la regió corporal, prioritza el patró i l'objectiu, "
                "respecta material i condicions aplicables, i explica els descartes. "
                "Cal usar-la abans de proposar skip."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "exercise_revision_id": {"type": "integer"},
                    "participant_plan_id": {"type": "integer"},
                    "objective": {
                        "type": "string",
                        "enum": ["", *ExerciseObjective.Objective.values],
                    },
                    "same_pattern_only": {"type": "boolean"},
                    "validated_only": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                }
            ),
        },
        {
            "type": "function",
            "name": "calculate_block_timing",
            "description": (
                "Calcula de manera determinista el temps de treball, descans i rondes d'un esborrany."
            ),
            "strict": True,
            "parameters": _object(
                {
                    "execution_mode": {
                        "type": "string",
                        "enum": ["sequential", "circuit", "stations", "superset", "parallel"],
                    },
                    "rounds": {"type": "integer", "minimum": 1, "maximum": 20},
                    "rest_between_rounds_seconds": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 900,
                    },
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": _object(
                            {
                                "exercise_revision_id": {"type": "integer"},
                                "sets": {"type": "integer", "minimum": 1, "maximum": 20},
                                "repetitions": _nullable("integer"),
                                "duration_seconds": _nullable("integer"),
                                "rest_between_sets_seconds": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 900,
                                },
                                "rest_after_seconds": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 900,
                                },
                            }
                        ),
                    },
                }
            ),
        },
        {
            "type": "function",
            "name": "audit_block_draft",
            "description": "Valida un esborrany complet abans de lliurar-lo. El contingut és el mateix JSON de la proposta final.",
            "strict": True,
            "parameters": _object({"proposal_json": {"type": "string"}}),
        },
    ]


def _decimal(value):
    return str(value) if isinstance(value, Decimal) else value


def _guideline_payload(guide):
    return {
        "dose_mode": guide.dose_mode,
        "sets": [guide.min_sets, guide.default_sets, guide.max_sets],
        "repetitions": [guide.min_repetitions, guide.default_repetitions, guide.max_repetitions],
        "duration_seconds": [guide.min_duration_seconds, guide.default_duration_seconds, guide.max_duration_seconds],
        "rest_seconds": [guide.min_rest_seconds, guide.default_rest_seconds, guide.max_rest_seconds],
        "rpe": [_decimal(guide.min_rpe), _decimal(guide.max_rpe)],
        "setup_duration_seconds": guide.setup_duration_seconds,
        "seconds_per_repetition": _decimal(guide.seconds_per_repetition),
        "load_estimate": {
            "mechanical": _decimal(guide.mechanical_impact),
            "neuromuscular": _decimal(guide.neuromuscular_load),
            "metabolic": _decimal(guide.metabolic_load),
            "coordinative": _decimal(guide.coordinative_load),
        },
        "quality_stop_rule": guide.quality_stop_rule,
        "source": guide.source,
        "source_url": guide.source_url,
        "exercise_specific": guide.is_exercise_specific,
    }


class AgentToolExecutor:
    """Executes the public tool contract while preserving an auditable allowlist."""

    def __init__(
        self,
        *,
        context,
        request_hint,
        max_results=20,
        max_unique_candidates=100,
        allow_drafts=False,
        require_planning=False,
    ):
        self.context = context
        self.request_hint = request_hint
        self.max_results = max(1, min(int(max_results), 30))
        self.max_unique_candidates = max(1, int(max_unique_candidates))
        self.allow_drafts = bool(allow_drafts)
        self.require_planning = bool(require_planning)
        self.allowed_exercise_ids = set()
        self.trace = []
        self.last_timing = None
        self.last_timing_arguments = None
        self.audit_calls = 0
        self.alternative_search_participant_ids = set()
        self.draft_matches_available = 0
        self.draft_candidate_ids = set()
        self.detail_exercise_ids = set()
        self.guidance_pairs = set()
        self.compatibility_pairs = set()
        self.allowed_professional_codes = set()
        self.professional_concept_calls = 0
        self.knowledge_exercise_ids = set()
        self.knowledge_claim_ids = {}
        self.knowledge_claims = {}
        self.knowledge_sources = {}
        self.planning_brief = None
        self.participant_context_calls = set()
        self.group_context_calls = 0
        self.guidance_packets = []
        self.compatibility_packets = []

    @property
    def participant_ids(self):
        return set(
            self.request_hint.get(
                "active_participant_plan_ids",
                [athlete.participant_plan_id for athlete in self.context.athletes],
            )
        )

    def execute(self, name, arguments):
        handlers = {
            "submit_block_planning_brief": self._submit_block_planning_brief,
            "get_participant_context": self._get_participant_context,
            "get_group_training_summary": self._get_group_training_summary,
            "search_professional_concepts": self._search_professional_concepts,
            "search_exercises": self._search_exercises,
            "get_exercise_details": self._get_exercise_details,
            "get_exercise_knowledge_support": self._get_exercise_knowledge_support,
            "get_prescription_guidance": self._get_prescription_guidance,
            "check_participant_compatibility": self._check_participant_compatibility,
            "find_compatible_alternatives": self._find_compatible_alternatives,
            "calculate_block_timing": self._calculate_block_timing,
            "audit_block_draft": self._audit_block_draft,
        }
        if name not in handlers:
            raise ValidationError("L'agent ha demanat una eina desconeguda.")
        if (
            self.require_planning
            and name != "submit_block_planning_brief"
            and self.planning_brief is None
        ):
            raise ValidationError(
                "Primer cal registrar un pla previ vàlid amb "
                "submit_block_planning_brief."
            )
        if (
            name == "submit_block_planning_brief"
            and self.planning_brief is not None
        ):
            raise ValidationError(
                "El pla previ ja està acceptat; conserva'l durant aquesta generació."
            )
        if name == "audit_block_draft":
            self.audit_calls += 1
        result = handlers[name](arguments)
        result_ids = self._result_exercise_ids(result)
        trace_arguments = arguments
        if name == "audit_block_draft":
            trace_arguments = {
                "proposal_bytes": len(arguments.get("proposal_json", "").encode("utf-8"))
            }
        trace_row = {
            "sequence": len(self.trace) + 1,
            "tool": name,
            "arguments": trace_arguments,
            "result_count": (
                len(result.get("results", result.get("exercises", [])))
                if isinstance(result, dict)
                else 0
            ),
            "total_matches": (
                result.get("total_matches") if isinstance(result, dict) else None
            ),
            "exercise_revision_ids": sorted(result_ids),
            "status": "ok",
            "result_bytes": len(
                json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
            ),
        }
        if name == "submit_block_planning_brief":
            trace_row["planning_contract_version"] = result.get("contract_version")
            trace_row["coverage_mode"] = result.get("coverage_mode")
        if name in {"search_exercises", "find_compatible_alternatives"}:
            trace_row["requested_validated_only"] = result.get(
                "requested_validated_only"
            )
            trace_row["effective_validated_only"] = result.get(
                "effective_validated_only"
            )
            trace_row["draft_permission_applied"] = result.get(
                "draft_permission_applied", False
            )
            trace_row["draft_matches_available"] = result.get(
                "draft_matches_available", 0
            )
        if name == "audit_block_draft":
            trace_row["audit_valid"] = bool(result.get("valid"))
            trace_row["audit_errors"] = list(result.get("errors", []))[:10]
        if name == "calculate_block_timing":
            trace_row["total_seconds"] = result.get("total_seconds")
            trace_row["fits_budget"] = result.get("fits_budget")
        if name == "search_professional_concepts":
            trace_row["professional_concept_codes"] = sorted(
                row.get("concept_code", "")
                for row in result.get("results", [])
                if row.get("concept_code")
            )
        if name == "get_exercise_knowledge_support":
            knowledge_rows = result.get("results", [])
            trace_row["knowledge_claim_ids"] = sorted(
                claim["claim_id"]
                for row in knowledge_rows
                for claim in row.get("claims", [])
            )
        self.trace.append(trace_row)
        return result

    def _submit_block_planning_brief(self, arguments):
        brief = dict(arguments)
        validate_planning_brief(
            brief,
            context=self.context,
            request_hint=self.request_hint,
        )
        self.planning_brief = brief
        return {"accepted": True, **brief}

    def _get_participant_context(self, arguments):
        participant_id = int(arguments["participant_plan_id"])
        if participant_id not in self.participant_ids:
            raise ValidationError("Només es pot ampliar el context d'una participant activa.")
        athlete = next(
            (
                row
                for row in self.context.athletes
                if row.participant_plan_id == participant_id
            ),
            None,
        )
        if athlete is None:
            raise ValidationError("La participant no pertany al context congelat.")
        payload = athlete.payload
        sections = list(dict.fromkeys(arguments.get("sections", [])))
        if not sections:
            raise ValidationError("Cal indicar almenys una secció de context.")
        mapping = {
            "sport_profiles": payload.get("sport_profiles", []),
            "conditions": payload.get("active_conditions", []),
            "observations": payload.get("current_observations", [])[:20],
            "training_responses": payload.get("recent_training_responses", [])[:30],
            "measurements": {
                "latest": payload.get("latest_measurements", []),
                "history": payload.get("measurement_history", []),
            },
            "insights": {
                "confirmed": payload.get("confirmed_insights", []),
                "proposed": payload.get("proposed_insights", []),
            },
        }
        self.participant_context_calls.add(participant_id)
        return {
            "participant_plan_id": participant_id,
            "as_of": payload.get("as_of"),
            "health_data_available": payload.get("scope", {}).get(
                "health_data_available", False
            ),
            "sections": {name: mapping[name] for name in sections},
        }

    def _get_group_training_summary(self, arguments):
        self.group_context_calls += 1
        return build_group_engine_summary(self.context, self.participant_ids)

    def _search_professional_concepts(self, arguments):
        self.professional_concept_calls += 1
        result = search_professional_concepts(
            query=arguments["query"],
            kinds=arguments["kinds"],
            limit=arguments["limit"],
        )
        for row in result["results"]:
            self.allowed_professional_codes.add(row["concept_code"])
            for relation in row.get("relations", []):
                self.allowed_professional_codes.update(
                    value
                    for value in (
                        relation.get("source_code"),
                        relation.get("target_code"),
                    )
                    if value
                )
        return {
            "query": result.get("query", ""),
            "results": [
                {
                    "concept_code": row.get("concept_code", ""),
                    "name": row.get("name", ""),
                    "kind": row.get("kind", ""),
                    "relations": [
                        {
                            key: relation.get(key, "")
                            for key in (
                                "direction",
                                "relation_type",
                                "source_code",
                                "source_kind",
                                "target_code",
                                "target_kind",
                            )
                        }
                        for relation in row.get("relations", [])
                    ],
                }
                for row in result.get("results", [])
            ],
            "policy": result.get("policy", {}),
        }

    def _record_knowledge(self, payload):
        for row in payload.get("results", []):
            exercise_id = int(row["exercise_revision_id"])
            self.knowledge_exercise_ids.add(exercise_id)
            self.knowledge_claim_ids.setdefault(exercise_id, set()).update(
                claim["claim_id"] for claim in row.get("claims", [])
            )
            self.knowledge_claims.update(
                {claim["claim_id"]: claim for claim in row.get("claims", [])}
            )
        for source in payload.get("sources", []):
            self.knowledge_sources[source["code"]] = source
        return payload

    def _queryset(self):
        return (
            ExerciseRevision.objects.filter(
                exercise__catalog__owner=self.context.owner,
                exercise__catalog__is_active=True,
                exercise__is_active=True,
                exercise__kind="variant",
            )
            .exclude(editorial_status=EditorialStatus.RETIRED)
            .select_related("exercise", "exercise__parent", "exercise__catalog")
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

    def editorial_availability(self):
        queryset = self._queryset()
        return {
            "validated": queryset.filter(
                editorial_status=EditorialStatus.VALIDATED
            ).count(),
            "draft": queryset.exclude(
                editorial_status=EditorialStatus.VALIDATED
            ).count(),
        }

    def _participants(self, values):
        requested = {int(value) for value in values}
        if not requested or not requested.issubset(self.participant_ids):
            raise ValidationError("L'eina només pot consultar participants actius d'aquesta sessió.")
        return [
            athlete
            for athlete in self.context.athletes
            if athlete.participant_plan_id in requested
        ]

    def _allowed_revisions(self, values):
        identifiers = {int(value) for value in values}
        if not identifiers or not identifiers.issubset(self.allowed_exercise_ids):
            raise ValidationError("Primer cal obtenir els exercicis mitjançant search_exercises.")
        rows = list(self._queryset().filter(pk__in=identifiers))
        if {row.pk for row in rows} != identifiers:
            raise ValidationError("Hi ha candidats que ja no estan disponibles.")
        return rows

    def _equipment(self, revision):
        required = [
            row.equipment.code
            for row in revision.equipment_requirements.all()
            if row.requirement == ExerciseEquipmentRequirement.Requirement.REQUIRED
        ]
        optional = [
            row.equipment.code
            for row in revision.equipment_requirements.all()
            if row.requirement != ExerciseEquipmentRequirement.Requirement.REQUIRED
        ]
        return sorted(required), sorted(optional)

    def _considerations(self, revision, athletes, *, compact=False):
        regions = PATTERN_REGIONS.get(revision.movement_pattern, set())
        rows = []
        for athlete in athletes:
            conditions = []
            for condition in athlete.payload.get("active_conditions", []):
                applicability = condition_applicability(condition, regions)
                if applicability == "not_applicable":
                    continue
                conditions.append(
                    {
                        "condition_id": condition.get("id"),
                        "title": condition.get("title", "condició activa"),
                        "training_impact": condition.get("training_impact", ""),
                        "applicability": applicability,
                        "applicability_scope": condition.get(
                            "applicability_scope", "unknown"
                        ),
                        "coach_scope_decision": condition.get(
                            "coach_scope_decision", ""
                        ),
                        "body_region": (condition.get("body_region") or {}).get(
                            "code", ""
                        ),
                    }
                )
            if compact:
                conditions = [
                    {
                        "condition_id": row["condition_id"],
                        "training_impact": row["training_impact"],
                        "applicability": row["applicability"],
                    }
                    for row in conditions
                ]
            applicable_impacts = {
                row["training_impact"]
                for row in conditions
                if row["applicability"] == "applies"
            }
            if "stop" in applicable_impacts:
                compatibility = "incompatible"
            elif "avoid" in applicable_impacts:
                compatibility = "requires_risk_resolution"
            elif "modify" in applicable_impacts:
                compatibility = "requires_modification"
            elif any(row["applicability"] == "uncertain" for row in conditions):
                compatibility = "uncertain"
            elif "monitor" in applicable_impacts:
                compatibility = "monitor"
            else:
                compatibility = "compatible"
            recent = [
                response
                for response in athlete.payload.get("recent_training_responses", [])
                if response.get("exercise_revision_id") == revision.pk
            ][:5]
            rows.append(
                {
                    "participant_plan_id": athlete.participant_plan_id,
                    "population_stage": athlete.prescription_profile.population_stage,
                    "experience_level": athlete.prescription_profile.experience_level,
                    "age_known": athlete.prescription_profile.age_years is not None,
                    "compatibility": compatibility,
                    "relevant_conditions": conditions,
                    "recent_responses": [] if compact else recent,
                }
            )
        return rows

    def _summary(self, revision, athletes, *, compact=False):
        required, optional = self._equipment(revision)
        considerations = self._considerations(
            revision, athletes, compact=compact
        )
        visible_considerations = considerations
        compatible_count = 0
        if compact:
            compatible_count = sum(
                row["compatibility"] == "compatible" for row in considerations
            )
            visible_considerations = [
                row for row in considerations
                if row["compatibility"] != "compatible"
            ]
        return {
            "exercise_revision_id": revision.pk,
            "exercise_code": revision.exercise.code,
            "name": revision.exercise.name,
            "family": revision.exercise.parent.name if revision.exercise.parent_id else "",
            "editorial_status": revision.editorial_status,
            "modality": revision.modality,
            "difficulty": revision.difficulty,
            "movement_pattern": revision.movement_pattern,
            "laterality": revision.laterality,
            "requires_equipment": revision.requires_equipment,
            "required_equipment_codes": required,
            "optional_equipment_codes": optional,
            "objectives": [
                {"objective": row.objective, "priority": row.priority}
                for row in revision.objectives.all()
            ],
            "safety_notes": "" if compact else revision.safety_notes,
            "compatible_participant_count": compatible_count if compact else None,
            "participant_considerations": visible_considerations,
        }

    def _search_exercises(self, arguments):
        athletes = self._participants(arguments["participant_plan_ids"])
        queryset = self._queryset()
        requested_professional_codes = set(arguments.get("action_codes", [])) | set(
            arguments.get("muscle_codes", [])
        )
        if not requested_professional_codes.issubset(self.allowed_professional_codes):
            unknown = sorted(
                requested_professional_codes - self.allowed_professional_codes
            )
            raise ValidationError(
                "Primer cal resoldre els codis professionals mitjançant "
                f"search_professional_concepts: {unknown}."
            )
        tokens = [part for part in arguments["query"].split() if len(part) >= 3][:8]
        if tokens:
            query_filter = Q()
            for token in tokens:
                query_filter |= (
                Q(exercise__name__icontains=token)
                | Q(exercise__code__icontains=token)
                | Q(description__icontains=token)
                | Q(execution__icontains=token)
                | Q(coaching_cues__icontains=token)
                )
            queryset = queryset.filter(query_filter)
        if arguments["movement_patterns"]:
            queryset = queryset.filter(movement_pattern__in=arguments["movement_patterns"])
        if arguments["modalities"]:
            queryset = queryset.filter(modality__in=arguments["modalities"])
        if arguments["difficulties"]:
            queryset = queryset.filter(difficulty__in=arguments["difficulties"])
        if arguments.get("action_codes"):
            queryset = queryset.filter(
                phases__actions__action__code__in=arguments["action_codes"]
            )
        if arguments.get("muscle_codes"):
            queryset = queryset.filter(
                phases__muscle_roles__muscle__code__in=arguments["muscle_codes"]
            )
        if arguments.get("expected_contractions"):
            queryset = queryset.filter(
                phases__muscle_roles__expected_contraction__in=arguments[
                    "expected_contractions"
                ]
            )
        objective = arguments["objective"]
        if objective:
            queryset = queryset.filter(
                Q(objectives__objective=objective)
                | Q(modality__in=OBJECTIVE_MODALITIES.get(objective, set()))
            )
        queryset = queryset.distinct().order_by("exercise__name", "pk")
        eligible_rows = []
        for revision in queryset:
            required, _ = self._equipment(revision)
            mode = arguments["equipment_mode"]
            if mode == "bodyweight_only" and (required or revision.requires_equipment):
                continue
            if mode == "available_only" and not set(required).issubset(
                self.context.available_equipment_codes
            ):
                continue
            eligible_rows.append(revision)
        draft_rows = [
            row
            for row in eligible_rows
            if row.editorial_status != EditorialStatus.VALIDATED
        ]
        self.draft_matches_available = max(
            self.draft_matches_available, len(draft_rows)
        )
        requested_validated_only = bool(arguments["validated_only"])
        effective_validated_only = requested_validated_only and not self.allow_drafts
        if self.allow_drafts:
            eligible_rows.sort(
                key=lambda row: (
                    row.editorial_status != EditorialStatus.VALIDATED,
                    row.exercise.name.casefold(),
                    row.pk,
                )
            )
        rows = (
            [
                row
                for row in eligible_rows
                if row.editorial_status == EditorialStatus.VALIDATED
            ]
            if effective_validated_only
            else eligible_rows
        )
        total = len(rows)
        offset = max(0, int(arguments["offset"]))
        limit = min(int(arguments["limit"]), self.max_results)
        page = rows[offset : offset + limit]
        remaining_capacity = self.max_unique_candidates - len(self.allowed_exercise_ids)
        if remaining_capacity <= 0:
            page = []
        else:
            page = page[:remaining_capacity]
        self.allowed_exercise_ids.update(row.pk for row in page)
        self.draft_candidate_ids.update(
            row.pk
            for row in page
            if row.editorial_status != EditorialStatus.VALIDATED
        )
        return {
            "total_matches": total,
            "offset": offset,
            "returned": len(page),
            "has_more": offset + len(page) < total,
            "results": [self._summary(row, athletes, compact=True) for row in page],
            "requested_validated_only": requested_validated_only,
            "effective_validated_only": effective_validated_only,
            "draft_matches_available": len(draft_rows),
            "draft_permission_applied": (
                self.allow_drafts and requested_validated_only
            ),
            "retrieval_note": (
                "L'autorització de l'entrenador amplia la cerca a revisions en esborrany."
                if self.allow_drafts and requested_validated_only
                else "Ordre estable per nom; no hi ha puntuació ni selecció automàtica."
            ),
            "relaxation_hints": (
                [
                    "Redueix o elimina el text lliure abans de retirar filtres professionals.",
                    "Relaxa una sola dimensió cada vegada i torna a consultar.",
                    "Si només queden esborranys, demana autorització a l'entrenador.",
                ]
                if total == 0
                else []
            ),
        }

    def _get_exercise_details(self, arguments):
        revisions = self._allowed_revisions(arguments["exercise_revision_ids"])
        self.detail_exercise_ids.update(row.pk for row in revisions)
        compatibility_knowledge = None
        if not self.require_planning:
            compatibility_knowledge = self._record_knowledge(
                build_exercise_knowledge_support(revisions=revisions)
            )
        athletes = list(self.context.athletes)
        results = []
        for revision in revisions:
            row = self._summary(revision, athletes)
            row.update(
                {
                    "description": revision.description,
                    "setup": revision.setup,
                    "execution": revision.execution,
                    "coaching_cues": revision.coaching_cues,
                    "constraints": [
                        {
                            "code": item.code,
                            "kind": item.kind,
                            "severity": item.severity,
                            "statement": item.statement,
                            "rationale": item.rationale,
                        }
                        for item in revision.constraints.all()
                    ],
                }
            )
            results.append(row)
        payload = {
            "results": results,
            "knowledge_note": (
                "Els claims no s'inclouen aquí; recupera'ls una vegada amb "
                "get_exercise_knowledge_support només per als finalistes."
            ),
        }
        if compatibility_knowledge is not None:
            payload["knowledge_support"] = compatibility_knowledge
        return payload

    def _get_exercise_knowledge_support(self, arguments):
        revisions = self._allowed_revisions(arguments["exercise_revision_ids"])
        already_loaded = sorted(
            row.pk for row in revisions if row.pk in self.knowledge_exercise_ids
        )
        pending = [
            row for row in revisions if row.pk not in self.knowledge_exercise_ids
        ]
        payload = (
            self._record_knowledge(
                build_exercise_knowledge_support(revisions=pending)
            )
            if pending
            else {"results": [], "sources": []}
        )
        payload["already_loaded_exercise_revision_ids"] = already_loaded
        if already_loaded:
            payload["retrieval_note"] = (
                "El servidor ja conserva aquests claims; no es tornen a enviar."
            )
        return payload

    def _get_prescription_guidance(self, arguments):
        revisions = self._allowed_revisions(arguments["exercise_revision_ids"])
        athletes = self._participants(arguments["participant_plan_ids"])
        self.guidance_pairs.update(
            (revision.pk, athlete.participant_plan_id)
            for revision in revisions
            for athlete in athletes
        )
        grouped = {}
        sources = {}
        for revision in revisions:
            for athlete in athletes:
                guide = resolve_guideline(
                    revision,
                    profile=athlete.prescription_profile,
                    objective=arguments["objective"],
                    block_role=arguments["block_role"],
                )
                guidance = _guideline_payload(guide)
                source_key = (guidance.pop("source", ""), guidance.pop("source_url", ""))
                if any(source_key):
                    sources[source_key] = {
                        "source": source_key[0],
                        "source_url": source_key[1],
                    }
                key = (revision.pk, json.dumps(guidance, sort_keys=True, default=str))
                row = grouped.setdefault(
                    key,
                    {
                        "exercise_revision_id": revision.pk,
                        "participant_plan_ids": [],
                        "profiles": [],
                        "guidance": guidance,
                    },
                )
                row["participant_plan_ids"].append(athlete.participant_plan_id)
                profile = {
                    "population_stage": athlete.prescription_profile.population_stage,
                    "experience_level": athlete.prescription_profile.experience_level,
                }
                if profile not in row["profiles"]:
                    row["profiles"].append(profile)
        packet = {"results": list(grouped.values()), "sources": list(sources.values())}
        accumulated = {}
        for row in [*self.guidance_packets, *packet["results"]]:
            key = (
                row["exercise_revision_id"],
                json.dumps(row["guidance"], sort_keys=True, default=str),
            )
            merged = accumulated.setdefault(
                key,
                {
                    "exercise_revision_id": row["exercise_revision_id"],
                    "participant_plan_ids": [],
                    "profiles": [],
                    "guidance": row["guidance"],
                },
            )
            for participant_plan_id in row["participant_plan_ids"]:
                if participant_plan_id not in merged["participant_plan_ids"]:
                    merged["participant_plan_ids"].append(participant_plan_id)
            for profile in row["profiles"]:
                if profile not in merged["profiles"]:
                    merged["profiles"].append(profile)
        self.guidance_packets = list(accumulated.values())
        return packet

    def _check_participant_compatibility(self, arguments):
        revisions = self._allowed_revisions(arguments["exercise_revision_ids"])
        athletes = self._participants(arguments["participant_plan_ids"])
        self.compatibility_pairs.update(
            (revision.pk, athlete.participant_plan_id)
            for revision in revisions
            for athlete in athletes
        )
        results = []
        for revision in revisions:
            considerations = self._considerations(revision, athletes)
            results.append(
                {
                    "exercise_revision_id": revision.pk,
                    "compatible_participant_plan_ids": [
                        row["participant_plan_id"]
                        for row in considerations
                        if row["compatibility"] == "compatible"
                    ],
                    "participants": [
                        row for row in considerations
                        if row["compatibility"] != "compatible"
                        or row.get("recent_responses")
                    ],
                }
            )
        accumulated = {
            row["exercise_revision_id"]: row for row in self.compatibility_packets
        }
        for row in results:
            existing = accumulated.setdefault(
                row["exercise_revision_id"],
                {
                    "exercise_revision_id": row["exercise_revision_id"],
                    "compatible_participant_plan_ids": [],
                    "participants": [],
                },
            )
            existing["compatible_participant_plan_ids"] = sorted(
                set(existing["compatible_participant_plan_ids"])
                | set(row["compatible_participant_plan_ids"])
            )
            participants = {
                participant["participant_plan_id"]: participant
                for participant in existing["participants"]
            }
            participants.update(
                {
                    participant["participant_plan_id"]: participant
                    for participant in row["participants"]
                }
            )
            existing["participants"] = list(participants.values())
        self.compatibility_packets = list(accumulated.values())
        return {"results": results}

    def _find_compatible_alternatives(self, arguments):
        base = self._allowed_revisions([arguments["exercise_revision_id"]])[0]
        athlete = self._participants([arguments["participant_plan_id"]])[0]
        self.alternative_search_participant_ids.add(athlete.participant_plan_id)
        queryset = self._queryset().exclude(pk=base.pk)
        if arguments["same_pattern_only"]:
            queryset = queryset.filter(movement_pattern=base.movement_pattern)
        if arguments["validated_only"] and not self.allow_drafts:
            queryset = queryset.filter(editorial_status=EditorialStatus.VALIDATED)
        if arguments["objective"]:
            queryset = queryset.filter(
                Q(objectives__objective=arguments["objective"])
                | Q(
                    modality__in=OBJECTIVE_MODALITIES.get(
                        arguments["objective"], set()
                    )
                )
            )
        rows = []
        rejected = {"equipment": 0, "incompatible": 0, "semantic": 0}
        base_regions = PATTERN_REGIONS.get(base.movement_pattern, set())
        for revision in queryset.distinct():
            required, _ = self._equipment(revision)
            if not set(required).issubset(self.context.available_equipment_codes):
                rejected["equipment"] += 1
                continue
            regions = PATTERN_REGIONS.get(revision.movement_pattern, set())
            if base_regions and not base_regions.intersection(regions):
                rejected["semantic"] += 1
                continue
            incompatible = any(
                condition.get("training_impact") == "stop"
                and condition_applies(condition, regions)
                for condition in athlete.payload.get("active_conditions", [])
            )
            if incompatible:
                rejected["incompatible"] += 1
                continue
            rows.append(revision)
        rows.sort(
            key=lambda revision: (
                revision.movement_pattern != base.movement_pattern,
                revision.editorial_status != EditorialStatus.VALIDATED,
                revision.exercise.name.casefold(),
                revision.pk,
            )
        )
        limit = min(int(arguments["limit"]), self.max_results)
        remaining_capacity = self.max_unique_candidates - len(self.allowed_exercise_ids)
        page = rows[: max(0, min(limit, remaining_capacity))]
        self.allowed_exercise_ids.update(row.pk for row in page)
        self.compatibility_pairs.update(
            (row.pk, athlete.participant_plan_id) for row in page
        )
        self.draft_candidate_ids.update(
            row.pk
            for row in page
            if row.editorial_status != EditorialStatus.VALIDATED
        )
        return {
            "base_exercise_revision_id": base.pk,
            "participant_plan_id": athlete.participant_plan_id,
            "returned": len(page),
            "total_compatible": len(rows),
            "rejected": rejected,
            "results": [
                {
                    **self._summary(row, [athlete]),
                    "equivalence": {
                        "base_pattern": base.movement_pattern,
                        "same_pattern": row.movement_pattern == base.movement_pattern,
                        "shared_body_regions": sorted(
                            base_regions.intersection(
                                PATTERN_REGIONS.get(row.movement_pattern, set())
                            )
                        ),
                        "objective_filter": arguments["objective"],
                    },
                }
                for row in page
            ],
            "requested_validated_only": bool(arguments["validated_only"]),
            "effective_validated_only": bool(arguments["validated_only"])
            and not self.allow_drafts,
            "draft_permission_applied": bool(self.allow_drafts),
        }

    def _calculate_block_timing(self, arguments):
        self.last_timing_arguments = json.loads(json.dumps(arguments))
        revisions = {
            row.pk: row for row in self._allowed_revisions(
                [item["exercise_revision_id"] for item in arguments["items"]]
            )
        }
        details = []
        one_round = 0
        for index, item in enumerate(arguments["items"], start=1):
            revision = revisions[item["exercise_revision_id"]]
            guide_rows = [row for row in revision.prescription_guidelines.all() if row.is_active]
            setup = max([row.setup_duration_seconds for row in guide_rows], default=20)
            seconds_per_rep = max(
                [row.seconds_per_repetition for row in guide_rows if row.seconds_per_repetition],
                default=Decimal("4"),
            )
            if item["repetitions"] is not None:
                work = int(Decimal(item["sets"]) * Decimal(item["repetitions"]) * seconds_per_rep)
            elif item["duration_seconds"] is not None:
                work = item["sets"] * item["duration_seconds"]
            else:
                raise ValidationError("Cada dosi necessita repeticions o durada.")
            between_sets = max(item["sets"] - 1, 0) * item["rest_between_sets_seconds"]
            total = setup + work + between_sets + item["rest_after_seconds"]
            one_round += total
            details.append(
                {
                    "item": index,
                    "exercise_revision_id": revision.pk,
                    "setup_seconds": setup,
                    "work_seconds": work,
                    "between_sets_seconds": between_sets,
                    "rest_after_seconds": item["rest_after_seconds"],
                    "single_round_seconds": total,
                }
            )
        rounds = arguments["rounds"]
        round_rest = max(rounds - 1, 0) * arguments["rest_between_rounds_seconds"]
        total = one_round * rounds + round_rest
        self.last_timing = {
            "single_round_seconds": one_round,
            "rounds": rounds,
            "between_rounds_seconds": round_rest,
            "total_seconds": total,
            "budget_seconds": self.request_hint["planned_duration_minutes"] * 60,
            "fits_budget": total <= self.request_hint["planned_duration_minutes"] * 60,
            "details": details,
        }
        return self.last_timing

    def _audit_block_draft(self, arguments):
        try:
            payload = json.loads(arguments["proposal_json"])
            if "request" not in payload and "plan" in payload:
                payload = proposal_payload_from_agent_output(
                    final=payload,
                    session_revision_id=self.context.revision.pk,
                    sequence_index=(
                        max(
                            self.context.revision.blocks.values_list(
                                "sequence_index", flat=True
                            ),
                            default=0,
                        )
                        + 1
                    ),
                    block_role=self.request_hint["block_role"],
                    planned_duration_minutes=self.request_hint[
                        "planned_duration_minutes"
                    ],
                    participant_plan_ids=self.request_hint[
                        "active_participant_plan_ids"
                    ],
                    excluded_participant_plan_ids=self.request_hint.get(
                        "excluded_participant_plan_ids", []
                    ),
                    available_equipment_ids=self.context.available_equipment_ids,
                    generator_reference=f"audit · {TOOL_VERSION}",
                )
            proposal = proposal_from_payload(payload)
            referenced = {
                item.dose.exercise_revision_id
                for item in proposal.items
                if item.dose is not None
            }
            referenced.update(
                alternative.exercise_revision_id
                for item in proposal.items
                for alternative in item.alternatives
            )
            referenced.update(
                adjustment.replacement_exercise_revision_id
                for item in proposal.items
                for adjustment in item.athlete_adjustments
                if adjustment.replacement_exercise_revision_id
            )
            if not referenced.issubset(self.allowed_exercise_ids):
                raise ValidationError("La proposta conté exercicis que no provenen de les cerques.")
            validate_block_generation_proposal(
                proposal,
                revision=self.context.revision,
                exercise_owner=self.context.owner,
            )
        except (ValueError, TypeError, KeyError, ValidationError) as error:
            messages = getattr(error, "messages", None) or [str(error)]
            code = "missing_field" if isinstance(error, KeyError) else "contract_validation"
            return {
                "valid": False,
                "errors": messages,
                "error_details": [
                    {"code": code, "message": message} for message in messages
                ],
            }
        return {"valid": True, "errors": [], "error_details": []}

    @staticmethod
    def _result_exercise_ids(result):
        identifiers = set()
        if not isinstance(result, dict):
            return identifiers
        for key in ("results", "exercises"):
            for row in result.get(key, []):
                if isinstance(row, dict) and row.get("exercise_revision_id"):
                    identifiers.add(int(row["exercise_revision_id"]))
        return identifiers
