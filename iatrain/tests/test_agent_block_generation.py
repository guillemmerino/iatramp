import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from iatrain.engine.agent import AgentNeedsCoachDecision, plan_block_with_agent
from iatrain.engine.agent_tools import AgentToolExecutor
from iatrain.engine.context import build_block_engine_context
from iatrain.models import (
    AthleteProfile,
    CoachProfile,
    SessionParticipantPlan,
    TrainingSession,
)
from iatrain.training.services import create_session_revision, create_training_session
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseObjective, ExerciseRevision
from organizations.models import Organization


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
            "warnings": [],
            "unmet_constraints": [],
            "confidence": 0.82,
        }

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
        ):
            result = plan_block_with_agent(
                context=context,
                prompt="Força de recepció moderada",
                duration_minutes=10,
                block_role="main",
                active_participant_ids=(self.participant.pk,),
                progress_callback=progress_events.append,
            )

        self.assertEqual(result.proposal.contract_version, "3.1")
        self.assertEqual(
            result.proposal.items[0].dose.exercise_revision_id,
            self.exercise_revision.pk,
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
        self.assertIn("searching", [row["stage"] for row in progress_events])
        self.assertIn("timing", [row["stage"] for row in progress_events])
        self.assertEqual(progress_events[-1]["stage"], "completed")

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
        ):
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

    def test_tool_finds_compatible_alternatives_and_adds_them_to_allowlist(self):
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
