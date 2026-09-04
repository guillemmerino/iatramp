import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Person
from iatrain.engine.agent import (
    AgentNeedsCoachDecision,
    OpenAITrainingRateLimited,
    _hydrate_professional_claims,
    _validate_professional_knowledge_evidence,
    plan_block_with_agent,
)
from iatrain.engine.agent_tools import AgentToolExecutor
from iatrain.engine.context import build_block_engine_context
from iatrain.engine.serialization import (
    proposal_from_payload,
    proposal_payload_from_agent_output,
)
from iatrain.models import (
    AthleteProfile,
    CoachProfile,
    SessionParticipantPlan,
    TrainingSession,
)
from iatrain.training.services import create_session_revision, create_training_session
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseObjective, ExerciseRevision
from organizations.models import Organization


@override_settings(OPENAI_TRAINING_PLANNING_BRIEF_ENABLED=False)
class AgentBlockGenerationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="agent-engine")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.is_provisional = False
        self.person.save()
        CoachProfile.objects.create(person=self.person)
        self.organization = Organization.objects.create(
            name="Club agent", slug="club-agent"
        )
        athlete = AthleteProfile.objects.create(
            person=Person.objects.create(first_name="Aina", last_name="Serra")
        )
        self.session = create_training_session(
            user=self.user,
            organization=self.organization,
            scheduled_start=timezone.now(),
            expected_duration_minutes=60,
            discipline=TrainingSession.Discipline.TRAMPOLINE,
            session_scope=TrainingSession.Scope.INDIVIDUAL,
        )
        self.revision = create_session_revision(
            user=self.user,
            session=self.session,
            title="Sessió agentiva",
            general_objective="Preparar recepcions estables.",
            planned_duration_minutes=60,
        )
        self.participant = SessionParticipantPlan.objects.create(
            session_revision=self.revision,
            athlete_profile=athlete,
        )
        catalog = ExerciseCatalog.objects.create(
            owner=self.person, code="agent", name="Catàleg agent"
        )
        family = Exercise.objects.create(
            catalog=catalog,
            code="squat-family",
            name="Família esquat",
            kind=Exercise.Kind.FAMILY,
            created_by=self.person,
        )
        exercise = Exercise.objects.create(
            catalog=catalog,
            code="squat",
            name="Esquat controlat",
            kind=Exercise.Kind.VARIANT,
            parent=family,
            created_by=self.person,
        )
        self.exercise_revision = ExerciseRevision.objects.create(
            exercise=exercise,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Control de cames i tronc.",
            setup="Peus estables.",
            execution="Flexiona i estén amb control.",
            coaching_cues="Genolls alineats.",
            authored_by=self.person,
        )
        ExerciseObjective.objects.create(
            revision=self.exercise_revision,
            objective=ExerciseObjective.Objective.GENERAL_STRENGTH,
            priority=ExerciseObjective.Priority.PRIMARY,
            rationale="Patró principal de força.",
        )
        ExerciseRevision.objects.filter(pk=self.exercise_revision.pk).update(
            editorial_status="validated"
        )
        self.exercise_revision.refresh_from_db()
        alternative_exercise = Exercise.objects.create(
            catalog=catalog,
            code="split-squat",
            name="Esquat dividit controlat",
            kind=Exercise.Kind.VARIANT,
            parent=family,
            created_by=self.person,
        )
        self.alternative_revision = ExerciseRevision.objects.create(
            exercise=alternative_exercise,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.ALTERNATING,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Variant unilateral assistida.",
            setup="Base dividida estable.",
            execution="Flexiona i estén amb control.",
            coaching_cues="Mantén l'alineació.",
            authored_by=self.person,
        )

    def _function_response(self, response_id, call_id, name, arguments):
        return {
            "id": response_id,
            "model": "gpt-5.6-luna",
            "output": [
                {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": json.dumps(arguments),
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        }

    def _review_response(self, response_id, *, verdict="pass", issues=None):
        payload = {
            "verdict": verdict,
            "summary": "La proposta és coherent." if verdict == "pass" else "Cal corregir-la.",
            "issues": issues or [],
            "clarification_question": "",
        }
        return {
            "id": response_id,
            "model": "gpt-5.6-luna",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": json.dumps(payload)}
                    ],
                }
            ],
            "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
        }

    def _final_payload(self):
        return {
            "intent_status": "ready",
            "clarification_question": "",
            "planning_summary": "Un únic patró controlat és suficient per al temps i l'objectiu.",
            "premise_effects": ["La manca de respostes prèvies manté una dosi moderada."],
            "search_summary": "Una cerca, un candidat compatible i un finalista.",
            "plan": {
                "name": "Força de recepció",
                "execution_mode": "sequential",
                "objective": {
                    "description": "Millorar el control de les recepcions.",
                    "primary_quality": "strength",
                    "secondary_qualities": ["motor_control"],
                    "movement_patterns": ["squat"],
                    "body_region_codes": ["knee", "hip"],
                },
                "target_intensity": "moderate",
                "hard_constraints": [],
                "preferences": ["qualitat tècnica"],
                "instructions": "Atura si es perd l'alineació.",
                "rounds": 1,
                "rest_between_rounds_seconds": 0,
            },
            "items": [
                {
                    "sequence_index": 1,
                    "item_type": "physical_exercise",
                    "title": "Esquat controlat",
                    "instructions": "Flexiona i estén amb control.",
                    "coaching_cues": "Genolls alineats.",
                    "setup_seconds": 20,
                    "planned_duration_seconds": 98,
                    "rest_after_seconds": 0,
                    "selection_rationale": "Cobreix el patró i és adequat al nivell inicial.",
                    "knowledge_support": {
                        "status": "hypothesis",
                        "summary": (
                            "La revisió de prova no conté camins professionals; "
                            "la selecció es manté com a hipòtesi explícita."
                        ),
                        "claims": [],
                    },
                    "is_optional": False,
                    "dose": {
                        "exercise_revision_id": self.exercise_revision.pk,
                        "dose_mode": "repetitions",
                        "sets": 2,
                        "repetitions": 6,
                        "duration_seconds": None,
                        "distance": None,
                        "distance_unit": "",
                        "load_value": None,
                        "load_unit": "",
                        "intensity_metric": "rpe",
                        "intensity_value": 5,
                        "tempo_eccentric_seconds": None,
                        "tempo_pause_seconds": None,
                        "tempo_concentric_seconds": None,
                        "concentric_intent": "controlled",
                        "rest_between_sets_seconds": 30,
                        "execution_notes": "Prioritza qualitat.",
                    },
                    "alternatives": [],
                    "athlete_adjustments": [],
                }
            ],
            "participants": [
                {
                    "participant_plan_id": self.participant.pk,
                    "mode": "shared",
                    "rationale": "Compatible amb la proposta base.",
                    "condition_decisions": [],
                }
            ],
            "estimated_duration_seconds": 98,
            "estimated_load": {
                "mechanical_impact": 2,
                "neuromuscular": 2.5,
                "metabolic": 2,
                "coordinative": 3,
                "notes": "Estimació relativa.",
            },
            "coverage": {
                "physical_qualities": ["strength", "motor_control"],
                "movement_patterns": ["squat"],
                "body_region_codes": ["knee", "hip"],
            },
            "satisfied_constraints": [],
            "warnings": [
                "La revisió de prova no conté encara camins professionals validats."
            ],
            "unmet_constraints": [],
            "confidence": 0.82,
        }

    def _standard_tool_responses(self, prefix):
        return [
            self._function_response(
                f"{prefix}-search", f"{prefix}-search-call", "search_exercises",
                {
                    "query": "", "objective": "strength",
                    "movement_patterns": ["squat"], "modalities": [],
                    "difficulties": [], "equipment_mode": "available_only",
                    "validated_only": True,
                    "participant_plan_ids": [self.participant.pk],
                    "offset": 0, "limit": 20,
                },
            ),
            self._function_response(
                f"{prefix}-details", f"{prefix}-details-call",
                "get_exercise_details",
                {"exercise_revision_ids": [self.exercise_revision.pk]},
            ),
            self._function_response(
                f"{prefix}-compat", f"{prefix}-compat-call",
                "check_participant_compatibility",
                {
                    "participant_plan_ids": [self.participant.pk],
                    "exercise_revision_ids": [self.exercise_revision.pk],
                },
            ),
            self._function_response(
                f"{prefix}-guidance", f"{prefix}-guidance-call",
                "get_prescription_guidance",
                {
                    "objective": "strength", "block_role": "main",
                    "participant_plan_ids": [self.participant.pk],
                    "exercise_revision_ids": [self.exercise_revision.pk],
                },
            ),
            self._function_response(
                f"{prefix}-timing", f"{prefix}-timing-call",
                "calculate_block_timing",
                {
                    "execution_mode": "sequential", "rounds": 1,
                    "rest_between_rounds_seconds": 0,
                    "items": [{
                        "exercise_revision_id": self.exercise_revision.pk,
                        "sets": 2, "repetitions": 6, "duration_seconds": None,
                        "rest_between_sets_seconds": 30, "rest_after_seconds": 0,
                    }],
                },
            ),
        ]

    def _planning_arguments(self):
        return {
            "contract_version": "1.1",
            "objective_summary": "Força controlada de recepció.",
            "success_criteria": ["Cobrir el patró d'esquat amb una dosi prudent."],
            "coverage_mode": "focused",
            "required_coverage_domains": ["lower_body"],
            "required_movement_patterns": [],
            "preferred_movement_patterns": ["squat"],
            "target_intensity": "moderate",
            "load_strategy": "Càrrega moderada i prioritat tècnica.",
            "time_budget_seconds": 600,
            "shared_strategy": "Una base comuna amb ajustaments individuals si cal.",
            "individual_priorities": [],
            "global_hard_constraints": [],
            "global_preferences": [
                {
                    "statement": "Prioritzar qualitat tècnica.",
                    "source": "coach_prompt",
                }
            ],
            "professional_queries": ["Funció del patró d'esquat."],
            "search_strategy": ["Cercar esquats validats i comparar-ne la dosi."],
            "uncertainties": ["No hi ha respostes prèvies suficients."],
        }

    @override_settings(OPENAI_TRAINING_PLANNING_BRIEF_ENABLED=True)
    def test_agent_registers_and_aligns_pre_search_planning_brief(self):
        planning = self._function_response(
            "plan-brief",
            "plan-brief-call",
            "submit_block_planning_brief",
            self._planning_arguments(),
        )
        final = {
            "id": "plan-final",
            "model": "gpt-5.6-luna",
            "output": [{
                "type": "message",
                "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(self._final_payload()),
                }],
            }],
            "usage": {},
        }
        context = build_block_engine_context(user=self.user, revision=self.revision)
        standard = self._standard_tool_responses("planned")
        knowledge = self._function_response(
            "planned-knowledge",
            "planned-knowledge-call",
            "get_exercise_knowledge_support",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )

        with patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                planning,
                standard[0],
                standard[1],
                knowledge,
                *standard[2:],
                final,
                self._review_response("planned-review"),
            ],
        ) as api_call:
            result = plan_block_with_agent(
                context=context,
                prompt="Força de recepció moderada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
            )

        self.assertEqual(result.proposal.contract_version, "3.5")
        self.assertEqual(result.planning_payload["contract_version"], "1.1")
        self.assertEqual(result.tool_trace[0]["tool"], "submit_block_planning_brief")
        self.assertTrue(result.validation_payload["planning"]["alignment_valid"])
        self.assertLess(len(api_call.call_args_list[0].args[0]["input"][0]["content"]), 15000)

    @override_settings(
        OPENAI_TRAINING_PLANNING_BRIEF_ENABLED=True,
        OPENAI_TRAINING_MAX_RATE_LIMIT_RETRIES=2,
    )
    def test_agent_compacts_and_retries_a_temporary_rate_limit(self):
        planning = self._function_response(
            "retry-plan",
            "retry-plan-call",
            "submit_block_planning_brief",
            self._planning_arguments(),
        )
        standard = self._standard_tool_responses("retry")
        knowledge = self._function_response(
            "retry-knowledge",
            "retry-knowledge-call",
            "get_exercise_knowledge_support",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )
        final = {
            "id": "retry-final",
            "model": "gpt-5.6-luna",
            "output": [{
                "type": "message",
                "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(self._final_payload()),
                }],
            }],
            "usage": {},
        }
        context = build_block_engine_context(user=self.user, revision=self.revision)

        with patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                OpenAITrainingRateLimited("límit temporal", retry_after_seconds=0),
                planning,
                standard[0],
                standard[1],
                knowledge,
                *standard[2:],
                final,
                self._review_response("retry-review"),
            ],
        ), patch("iatrain.engine.agent.time.sleep") as sleep:
            result = plan_block_with_agent(
                context=context,
                prompt="Força de recepció moderada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
            )

        sleep.assert_called_once_with(0.5)
        self.assertEqual(
            result.validation_payload["context_metrics"]["rate_limit_retries"],
            1,
        )
        self.assertEqual(result.proposal.contract_version, "3.5")

    def test_agent_searches_catalog_calculates_time_and_returns_v3_proposal(self):
        search = self._function_response(
            "resp-1",
            "call-search",
            "search_exercises",
            {
                "query": "",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "equipment_mode": "available_only",
                "validated_only": True,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )
        timing = self._function_response(
            "resp-2",
            "call-time",
            "calculate_block_timing",
            {
                "execution_mode": "sequential",
                "rounds": 1,
                "rest_between_rounds_seconds": 0,
                "items": [
                    {
                        "exercise_revision_id": self.exercise_revision.pk,
                        "sets": 2,
                        "repetitions": 6,
                        "duration_seconds": None,
                        "rest_between_sets_seconds": 30,
                        "rest_after_seconds": 0,
                    }
                ],
            },
        )
        details = self._function_response(
            "resp-details",
            "call-details",
            "get_exercise_details",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )
        compatibility = self._function_response(
            "resp-compatibility",
            "call-compatibility",
            "check_participant_compatibility",
            {
                "participant_plan_ids": [self.participant.pk],
                "exercise_revision_ids": [self.exercise_revision.pk],
            },
        )
        guidance = self._function_response(
            "resp-guidance",
            "call-guidance",
            "get_prescription_guidance",
            {
                "objective": "strength",
                "block_role": "main",
                "participant_plan_ids": [self.participant.pk],
                "exercise_revision_ids": [self.exercise_revision.pk],
            },
        )
        final = {
            "id": "resp-3",
            "model": "gpt-5.6-luna",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": json.dumps(self._final_payload())}
                    ],
                }
            ],
            "usage": {"input_tokens": 200, "output_tokens": 300, "total_tokens": 500},
        }
        context = build_block_engine_context(user=self.user, revision=self.revision)
        progress_events = []

        with self.settings(
            OPENAI_TRAINING_MODEL="gpt-5.6-luna",
            OPENAI_TRAINING_MAX_TOOL_ROUNDS=6,
        ), patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                search,
                details,
                compatibility,
                guidance,
                timing,
                final,
                self._review_response("resp-review"),
            ],
        ) as api_call:
            result = plan_block_with_agent(
                context=context,
                prompt="Força de recepció moderada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
                progress_callback=progress_events.append,
            )

        self.assertEqual(result.proposal.contract_version, "3.4")
        self.assertEqual(
            result.proposal.items[0].dose.exercise_revision_id,
            self.exercise_revision.pk,
        )
        self.assertEqual(
            result.proposal.items[0].knowledge_support.status, "hypothesis"
        )
        self.assertEqual(
            result.validation_payload["professional_knowledge"][
                "exercise_revision_ids"
            ],
            [self.exercise_revision.pk],
        )
        self.assertEqual(result.proposal.estimated_duration_seconds, 98)
        self.assertEqual([row["tool"] for row in result.tool_trace], [
            "search_exercises",
            "get_exercise_details",
            "check_participant_compatibility",
            "get_prescription_guidance",
            "calculate_block_timing",
        ])
        self.assertEqual(result.usage_payload["total_tokens"], 1200)
        self.assertEqual(result.usage_payload["planner"]["total_tokens"], 1100)
        self.assertEqual(result.usage_payload["reviewer"]["total_tokens"], 100)
        self.assertEqual(result.usage_payload["reviewer_model"], "gpt-5.6-luna")
        self.assertIn("searching", [row["stage"] for row in progress_events])
        self.assertIn("timing", [row["stage"] for row in progress_events])
        self.assertEqual(progress_events[-1]["stage"], "completed")
        review_packet = json.loads(
            api_call.call_args_list[6].args[0]["input"][0]["content"]
        )
        self.assertEqual(
            review_packet["request_context"]["coach_prompt"],
            "Força de recepció moderada",
        )
        self.assertEqual(
            review_packet["request_context"]["server_authority"]["block_role"],
            "main",
        )
        self.assertTrue(
            review_packet["evidence"]["timing_contract"]["server_timing_valid"]
        )
        self.assertTrue(
            review_packet["evidence"]["timing_contract"][
                "components_are_already_included"
            ]
        )

    def test_independent_reviewer_returns_a_proposal_to_the_planner_for_repair(self):
        calls = [
            self._function_response(
                "repair-search",
                "repair-search-call",
                "search_exercises",
                {
                    "query": "",
                    "objective": "strength",
                    "movement_patterns": ["squat"],
                    "modalities": [],
                    "difficulties": [],
                    "equipment_mode": "available_only",
                    "validated_only": True,
                    "participant_plan_ids": [self.participant.pk],
                    "offset": 0,
                    "limit": 20,
                },
            ),
            self._function_response(
                "repair-details",
                "repair-details-call",
                "get_exercise_details",
                {"exercise_revision_ids": [self.exercise_revision.pk]},
            ),
            self._function_response(
                "repair-compatibility",
                "repair-compatibility-call",
                "check_participant_compatibility",
                {
                    "participant_plan_ids": [self.participant.pk],
                    "exercise_revision_ids": [self.exercise_revision.pk],
                },
            ),
            self._function_response(
                "repair-guidance",
                "repair-guidance-call",
                "get_prescription_guidance",
                {
                    "objective": "strength",
                    "block_role": "main",
                    "participant_plan_ids": [self.participant.pk],
                    "exercise_revision_ids": [self.exercise_revision.pk],
                },
            ),
            self._function_response(
                "repair-timing",
                "repair-timing-call",
                "calculate_block_timing",
                {
                    "execution_mode": "sequential",
                    "rounds": 1,
                    "rest_between_rounds_seconds": 0,
                    "items": [
                        {
                            "exercise_revision_id": self.exercise_revision.pk,
                            "sets": 2,
                            "repetitions": 6,
                            "duration_seconds": None,
                            "rest_between_sets_seconds": 30,
                            "rest_after_seconds": 0,
                        }
                    ],
                },
            ),
        ]
        final = {
            "id": "repair-final-1",
            "model": "gpt-5.6-luna",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": json.dumps(self._final_payload())}
                    ],
                }
            ],
            "usage": {},
        }
        repaired_final = {**final, "id": "repair-final-2"}
        revise = self._review_response(
            "repair-review-1",
            verdict="revise",
            issues=[
                {
                    "code": "level_mismatch",
                    "severity": "error",
                    "message": "La progressió no està prou justificada.",
                    "correction": "Explicita l'adequació al nivell.",
                }
            ],
        )
        context = build_block_engine_context(user=self.user, revision=self.revision)

        with patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                *calls,
                final,
                revise,
                repaired_final,
                self._review_response("repair-review-2"),
            ],
        ) as api_call:
            result = plan_block_with_agent(
                context=context,
                prompt="Força controlada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
            )

        self.assertEqual(len(result.validation_payload["review_attempts"]), 2)
        self.assertEqual(
            result.validation_payload["independent_review"]["verdict"], "pass"
        )
        repair_input = api_call.call_args_list[7].args[0]["input"]
        self.assertEqual(len(repair_input), 1)
        repair_packet = json.loads(repair_input[0]["content"])
        self.assertEqual(repair_packet["mode"], "repair_current_proposal")
        self.assertEqual(repair_packet["repair_source"], "independent_reviewer")

    def test_noncritical_review_error_keeps_an_editable_review_proposal(self):
        final = {
            "id": "reviewable-final",
            "model": "gpt-5.6-luna",
            "output": [{
                "type": "message", "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(self._final_payload()),
                }],
            }],
            "usage": {},
        }
        issue = {
            "code": "LOCAL-DOSE",
            "severity": "error",
            "message": "Cal revisar una dosi individual.",
            "correction": "Ajusta-la manualment abans d'entrenar.",
            "participant_plan_ids": [self.participant.pk],
            "sequence_indices": [1],
            "exercise_revision_ids": [self.exercise_revision.pk],
        }
        context = build_block_engine_context(user=self.user, revision=self.revision)

        with self.settings(OPENAI_TRAINING_MAX_REVIEW_REPAIRS=0), patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                *self._standard_tool_responses("reviewable"),
                final,
                self._review_response(
                    "reviewable-review", verdict="revise", issues=[issue]
                ),
            ],
        ):
            result = plan_block_with_agent(
                context=context,
                prompt="Força controlada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
            )

        self.assertTrue(result.review_required)
        self.assertEqual(result.review_issues[0]["code"], "LOCAL-DOSE")
        self.assertTrue(result.validation_payload["review_required"])

    def test_reviewer_missing_context_does_not_block_the_proposal(self):
        final = {
            "id": "uncertain-final",
            "model": "gpt-5.6-luna",
            "output": [{
                "type": "message", "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(self._final_payload()),
                }],
            }],
            "usage": {},
        }
        review = self._review_response(
            "uncertain-review", verdict="needs_clarification"
        )
        review_payload = json.loads(review["output"][0]["content"][0]["text"])
        review_payload["summary"] = "Falta una dada de perfil."
        review_payload["clarification_question"] = "Quina és l'edat exacta?"
        review["output"][0]["content"][0]["text"] = json.dumps(review_payload)
        context = build_block_engine_context(user=self.user, revision=self.revision)

        with patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                *self._standard_tool_responses("uncertain"),
                final,
                review,
            ],
        ):
            result = plan_block_with_agent(
                context=context,
                prompt="Força controlada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
            )

        self.assertTrue(result.review_required)
        self.assertEqual(
            result.review_issues[0]["code"], "REVIEWER-CONTEXT-UNCERTAINTY"
        )

    def test_missing_evidence_is_grouped_and_does_not_consume_a_proposal_repair(self):
        ExerciseRevision.objects.filter(pk=self.alternative_revision.pk).update(
            editorial_status="validated"
        )
        self.alternative_revision.refresh_from_db()
        proposal_payload = self._final_payload()
        proposal_payload["participants"][0]["mode"] = "personalized"
        proposal_payload["participants"][0]["rationale"] = (
            "Substitució individual necessària."
        )
        proposal_payload["items"][0]["athlete_adjustments"] = [
            {
                "participant_plan_id": self.participant.pk,
                "rationale": "Variant individual equivalent.",
                "action": "replace",
                "replacement_exercise_revision_id": self.alternative_revision.pk,
                "sets": None,
                "repetitions": None,
                "duration_seconds": None,
                "load_value": None,
                "load_unit": "",
                "intensity_metric": "",
                "intensity_value": None,
                "rest_between_sets_seconds": None,
                "station_remainder_action": "",
                "adaptation_notes": "Execució assistida.",
                "professional_justification": {
                    "condition_ids": [],
                    "profile_factor_codes": ["individual_tolerance"],
                    "professional_claim_ids": [],
                    "affected_phase_codes": ["unspecified"],
                    "biomechanical_relevance": (
                        "La rellevància exacta no està coberta per la base de prova."
                    ),
                    "adaptation_goal": "Mantenir l'objectiu amb una variant assistida.",
                    "monitoring_criteria": ["Conservar el control tècnic."],
                    "stop_criteria": ["Aturar davant dolor o pèrdua de control."],
                    "evidence_status": "hypothesis",
                },
            }
        ]
        final = {
            "id": "evidence-final-1",
            "model": "gpt-5.6-luna",
            "output": [{
                "type": "message", "role": "assistant",
                "content": [{
                    "type": "output_text", "text": json.dumps(proposal_payload)
                }],
            }],
            "usage": {},
        }
        grouped_evidence = {
            "id": "evidence-tools",
            "model": "gpt-5.6-luna",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "evidence-details-call",
                    "name": "get_exercise_details",
                    "arguments": json.dumps({
                        "exercise_revision_ids": [self.alternative_revision.pk]
                    }),
                },
                {
                    "type": "function_call",
                    "call_id": "evidence-compat-call",
                    "name": "check_participant_compatibility",
                    "arguments": json.dumps({
                        "participant_plan_ids": [self.participant.pk],
                        "exercise_revision_ids": [self.alternative_revision.pk],
                    }),
                },
                {
                    "type": "function_call",
                    "call_id": "evidence-guidance-call",
                    "name": "get_prescription_guidance",
                    "arguments": json.dumps({
                        "objective": "strength",
                        "block_role": "main",
                        "participant_plan_ids": [self.participant.pk],
                        "exercise_revision_ids": [self.alternative_revision.pk],
                    }),
                },
            ],
            "usage": {},
        }
        repaired_final = {**final, "id": "evidence-final-2"}
        context = build_block_engine_context(user=self.user, revision=self.revision)

        with self.settings(
            OPENAI_TRAINING_MAX_REPAIRS=0,
            OPENAI_TRAINING_MAX_EVIDENCE_ROUNDS=1,
        ), patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                *self._standard_tool_responses("evidence"),
                final,
                grouped_evidence,
                repaired_final,
                self._review_response("evidence-review"),
            ],
        ) as api_call:
            result = plan_block_with_agent(
                context=context,
                prompt="Força controlada amb una variant individual",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
            )

        counts = result.validation_payload["repair_counts"]
        self.assertEqual(counts["server"], 0)
        self.assertEqual(counts["evidence"], 1)
        first_attempt = result.validation_payload["evidence_attempts"][0]
        self.assertEqual(
            first_attempt["missing"]["details"], [self.alternative_revision.pk]
        )
        expected_pair = [[self.alternative_revision.pk, self.participant.pk]]
        self.assertEqual(first_attempt["missing"]["compatibility"], expected_pair)
        self.assertEqual(first_attempt["missing"]["guidance"], expected_pair)
        self.assertEqual(len(first_attempt["required_tool_calls"]), 3)
        repair_packet = json.loads(
            api_call.call_args_list[6].args[0]["input"][0]["content"]
        )
        self.assertEqual(repair_packet["repair_source"], "tool_evidence")
        self.assertEqual(len(repair_packet["required_tool_calls"]), 3)
        self.assertTrue(result.validation_payload["evidence_attempts"][-1]["complete"])

    def test_tool_executor_rejects_ids_not_returned_by_search(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={"planned_duration_minutes": 10, "block_role": "main"},
        )

        with self.assertRaisesMessage(Exception, "Primer cal obtenir"):
            executor.execute(
                "get_exercise_details",
                {"exercise_revision_ids": [self.exercise_revision.pk]},
            )

    def test_planning_gate_blocks_search_and_rejects_incomplete_full_body_plan(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={
                "planned_duration_minutes": 10,
                "block_role": "preparation",
                "active_participant_plan_ids": [self.participant.pk],
                "excluded_participant_plan_ids": [],
                "coach_prompt": "Escalfament full body",
            },
            require_planning=True,
        )
        with self.assertRaisesMessage(Exception, "Primer cal registrar"):
            executor.execute(
                "search_exercises",
                {
                    "query": "",
                    "objective": "preparation",
                    "movement_patterns": [],
                    "modalities": [],
                    "difficulties": [],
                    "action_codes": [],
                    "muscle_codes": [],
                    "expected_contractions": [],
                    "equipment_mode": "available_only",
                    "validated_only": True,
                    "participant_plan_ids": [self.participant.pk],
                    "offset": 0,
                    "limit": 20,
                },
            )
        brief = self._planning_arguments()
        brief["coverage_mode"] = "full_body"
        with self.assertRaisesMessage(Exception, "tren inferior"):
            executor.execute("submit_block_planning_brief", brief)
        brief["required_coverage_domains"] = [
            "lower_body", "upper_body", "trunk"
        ]
        brief["global_hard_constraints"] = ["validated_only"]
        with self.assertRaisesMessage(Exception, "restriccions dures"):
            executor.execute("submit_block_planning_brief", brief)
        brief["global_hard_constraints"] = []
        accepted = executor.execute("submit_block_planning_brief", brief)
        self.assertTrue(accepted["accepted"])

    def test_planned_tools_do_not_repeat_professional_support(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={
                "planned_duration_minutes": 10,
                "block_role": "main",
                "active_participant_plan_ids": [self.participant.pk],
                "excluded_participant_plan_ids": [],
                "coach_prompt": "Força de recepció moderada",
                "coach_decisions": {},
            },
            require_planning=True,
        )
        executor.execute("submit_block_planning_brief", self._planning_arguments())
        executor.execute(
            "search_exercises",
            {
                "query": "",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "action_codes": [],
                "muscle_codes": [],
                "expected_contractions": [],
                "equipment_mode": "available_only",
                "validated_only": True,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )
        details = executor.execute(
            "get_exercise_details",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )
        first = executor.execute(
            "get_exercise_knowledge_support",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )
        second = executor.execute(
            "get_exercise_knowledge_support",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )

        self.assertNotIn("knowledge_support", details)
        self.assertEqual(first["already_loaded_exercise_revision_ids"], [])
        self.assertEqual(
            second["already_loaded_exercise_revision_ids"],
            [self.exercise_revision.pk],
        )
        self.assertEqual(second["results"], [])

    def test_tool_finds_compatible_alternatives_and_adds_them_to_allowlist(self):
        unrelated_exercise = Exercise.objects.create(
            catalog=self.exercise_revision.exercise.catalog,
            code="shoulder-press",
            name="Press d'espatlla",
            kind=Exercise.Kind.VARIANT,
            parent=self.exercise_revision.exercise.parent,
            created_by=self.person,
        )
        unrelated_revision = ExerciseRevision.objects.create(
            exercise=unrelated_exercise,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.OPEN,
            movement_pattern=ExerciseRevision.MovementPattern.VERTICAL_PUSH,
            description="Treball de l'espatlla.",
            setup="Posició estable.",
            execution="Empeny amb control.",
            coaching_cues="Control escapular.",
            authored_by=self.person,
        )
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={
                "planned_duration_minutes": 10,
                "block_role": "main",
                "active_participant_plan_ids": [self.participant.pk],
                "excluded_participant_plan_ids": [],
            },
        )
        executor.execute(
            "search_exercises",
            {
                "query": "",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "equipment_mode": "available_only",
                "validated_only": False,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )

        result = executor.execute(
            "find_compatible_alternatives",
            {
                "exercise_revision_id": self.exercise_revision.pk,
                "participant_plan_id": self.participant.pk,
                "objective": "strength",
                "same_pattern_only": True,
                "validated_only": False,
                "limit": 10,
            },
        )

        self.assertIn(
            self.alternative_revision.pk,
            [row["exercise_revision_id"] for row in result["results"]],
        )
        self.assertIn(self.participant.pk, executor.alternative_search_participant_ids)
        broad_result = executor.execute(
            "find_compatible_alternatives",
            {
                "exercise_revision_id": self.exercise_revision.pk,
                "participant_plan_id": self.participant.pk,
                "objective": "strength",
                "same_pattern_only": False,
                "validated_only": False,
                "limit": 10,
            },
        )
        broad_ids = [
            row["exercise_revision_id"] for row in broad_result["results"]
        ]
        self.assertNotIn(unrelated_revision.pk, broad_ids)
        self.assertGreaterEqual(broad_result["rejected"]["semantic"], 1)

    def test_avoid_marks_risk_resolution_without_hiding_same_region_alternatives(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        context.athletes[0].payload["active_conditions"] = [
            {
                "id": 77,
                "title": "Evitar càrrega alta de genoll",
                "training_impact": "avoid",
                "applicability_scope": "body_region",
                "body_region": {"code": "knee"},
            }
        ]
        executor = AgentToolExecutor(
            context=context,
            request_hint={
                "planned_duration_minutes": 10,
                "block_role": "main",
                "active_participant_plan_ids": [self.participant.pk],
                "excluded_participant_plan_ids": [],
            },
        )
        executor.execute(
            "search_exercises",
            {
                "query": "",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "equipment_mode": "available_only",
                "validated_only": False,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )
        compatibility = executor.execute(
            "check_participant_compatibility",
            {
                "participant_plan_ids": [self.participant.pk],
                "exercise_revision_ids": [self.exercise_revision.pk],
            },
        )
        alternatives = executor.execute(
            "find_compatible_alternatives",
            {
                "exercise_revision_id": self.exercise_revision.pk,
                "participant_plan_id": self.participant.pk,
                "objective": "strength",
                "same_pattern_only": True,
                "validated_only": False,
                "limit": 10,
            },
        )

        athlete_result = compatibility["results"][0]["participants"][0]
        self.assertEqual(athlete_result["compatibility"], "requires_risk_resolution")
        self.assertIn(
            self.alternative_revision.pk,
            [row["exercise_revision_id"] for row in alternatives["results"]],
        )

    def test_audit_accepts_the_same_plan_schema_as_the_final_agent_output(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={
                "planned_duration_minutes": 10,
                "block_role": "main",
                "active_participant_plan_ids": [self.participant.pk],
                "excluded_participant_plan_ids": [],
            },
        )
        executor.execute(
            "search_exercises",
            {
                "query": "Esquat controlat",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "equipment_mode": "available_only",
                "validated_only": True,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )

        result = executor.execute(
            "audit_block_draft",
            {"proposal_json": json.dumps(self._final_payload())},
        )

        self.assertTrue(result["valid"], result["errors"])

    def test_server_rejects_a_professional_claim_not_returned_by_the_tools(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={
                "planned_duration_minutes": 10,
                "block_role": "main",
                "active_participant_plan_ids": [self.participant.pk],
                "excluded_participant_plan_ids": [],
            },
        )
        executor.execute(
            "search_exercises",
            {
                "query": "Esquat controlat",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "equipment_mode": "available_only",
                "validated_only": True,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )
        executor.execute(
            "get_exercise_details",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )
        final = self._final_payload()
        final["items"][0]["knowledge_support"] = {
            "status": "grounded",
            "summary": "Afirmació manipulada.",
            "claims": [
                {
                    "claim_id": "exercise:fake:claim",
                    "exercise_revision_id": self.exercise_revision.pk,
                    "phase_code": "fake",
                    "claim_type": "muscle_role",
                    "action_code": "hip_extension",
                    "muscle_code": "gluteus_maximus",
                    "basis_type": "action_function",
                    "basis_code": "fake",
                    "expected_contraction": "concentric",
                    "verification_state": "confirmed",
                    "evidence_codes": [],
                    "limitations": [],
                }
            ],
        }
        canonical = proposal_payload_from_agent_output(
            final=final,
            session_revision_id=self.revision.pk,
            sequence_index=1,
            block_role="main",
            planned_duration_minutes=10,
            participant_plan_ids=[self.participant.pk],
            excluded_participant_plan_ids=[],
            available_equipment_ids=[],
            generator_reference="test",
        )
        errors = _validate_professional_knowledge_evidence(
            proposal=proposal_from_payload(canonical), executor=executor
        )
        self.assertTrue(any("no recuperada" in row for row in errors))

    def test_server_hydrates_claim_fields_and_summary_from_canonical_evidence(self):
        context = build_block_engine_context(user=self.user, revision=self.revision)
        executor = AgentToolExecutor(
            context=context,
            request_hint={"planned_duration_minutes": 10, "block_role": "main"},
        )
        executor.knowledge_claims["claim:1"] = {
            "claim_id": "claim:1",
            "exercise_revision_id": self.exercise_revision.pk,
            "phase_code": "up",
            "claim_type": "joint_action",
            "action_code": "knee_extension",
            "muscle_code": "",
            "basis_type": "motion_concept",
            "basis_code": "knee_extension",
            "expected_contraction": "not_applicable",
            "verification_state": "confirmed",
            "evidence_codes": ["source:1"],
            "limitations": ["No quantifica forces internes."],
        }
        final = self._final_payload()
        final["items"][0]["knowledge_support"] = {
            "status": "grounded",
            "summary": "També demostra flexió i rotació.",
            "claims": [{"claim_id": "claim:1", "action_code": "invented"}],
        }

        hydrated = _hydrate_professional_claims(final=final, executor=executor)

        support = final["items"][0]["knowledge_support"]
        self.assertEqual(hydrated, 1)
        self.assertEqual(support["claims"][0]["action_code"], "knee_extension")
        self.assertNotIn("flexió", support["summary"])
        self.assertIn("knee_extension", support["summary"])

    def test_draft_exercises_require_explicit_coach_permission(self):
        ExerciseRevision.objects.filter(pk=self.exercise_revision.pk).update(
            editorial_status="draft"
        )
        self.exercise_revision.refresh_from_db()
        search = self._function_response(
            "resp-draft-1",
            "call-draft-search",
            "search_exercises",
            {
                "query": "Esquat controlat",
                "objective": "strength",
                "movement_patterns": ["squat"],
                "modalities": [],
                "difficulties": [],
                "equipment_mode": "available_only",
                "validated_only": True,
                "participant_plan_ids": [self.participant.pk],
                "offset": 0,
                "limit": 20,
            },
        )
        timing = self._function_response(
            "resp-draft-2",
            "call-draft-time",
            "calculate_block_timing",
            {
                "execution_mode": "sequential",
                "rounds": 1,
                "rest_between_rounds_seconds": 0,
                "items": [
                    {
                        "exercise_revision_id": self.exercise_revision.pk,
                        "sets": 2,
                        "repetitions": 6,
                        "duration_seconds": None,
                        "rest_between_sets_seconds": 30,
                        "rest_after_seconds": 0,
                    }
                ],
            },
        )
        details = self._function_response(
            "resp-draft-details",
            "call-draft-details",
            "get_exercise_details",
            {"exercise_revision_ids": [self.exercise_revision.pk]},
        )
        compatibility = self._function_response(
            "resp-draft-compatibility",
            "call-draft-compatibility",
            "check_participant_compatibility",
            {
                "participant_plan_ids": [self.participant.pk],
                "exercise_revision_ids": [self.exercise_revision.pk],
            },
        )
        guidance = self._function_response(
            "resp-draft-guidance",
            "call-draft-guidance",
            "get_prescription_guidance",
            {
                "objective": "strength",
                "block_role": "main",
                "participant_plan_ids": [self.participant.pk],
                "exercise_revision_ids": [self.exercise_revision.pk],
            },
        )
        final = {
            "id": "resp-draft-3",
            "model": "gpt-5.6-luna",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": json.dumps(self._final_payload())}
                    ],
                }
            ],
            "usage": {},
        }
        context = build_block_engine_context(user=self.user, revision=self.revision)

        with patch("iatrain.engine.agent._post_responses_api") as api_call:
            with self.assertRaises(AgentNeedsCoachDecision) as raised:
                plan_block_with_agent(
                    context=context,
                    prompt="Força controlada",
                    duration_minutes=10,
                    block_role="main",
                    active_participant_ids=(self.participant.pk,),
                )
        api_call.assert_not_called()

        self.assertEqual(
            raised.exception.issues[0]["reason_code"],
            "draft_exercises_required",
        )

        with patch(
            "iatrain.engine.agent._post_responses_api",
            side_effect=[
                search,
                details,
                compatibility,
                guidance,
                timing,
                final,
                self._review_response("resp-draft-review"),
            ],
        ):
            result = plan_block_with_agent(
                context=context,
                prompt="Força controlada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
                coach_decisions={"catalog_drafts": "allow_draft_exercises"},
            )

        self.assertEqual(result.proposal.items[0].dose.exercise_revision_id, self.exercise_revision.pk)
        self.assertTrue(result.tool_trace[0]["requested_validated_only"])
        self.assertFalse(result.tool_trace[0]["effective_validated_only"])
        self.assertTrue(result.tool_trace[0]["draft_permission_applied"])
