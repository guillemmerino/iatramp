from datetime import date
from dataclasses import replace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Person
from iatrain.athletes.services import (
    propose_athlete_condition,
    review_athlete_condition,
)
from iatrain.engine.context import AthleteEngineContext, BlockEngineContext
from iatrain.engine.contracts import (
    AthleteAdjustmentProposal,
    BlockGenerationRequest,
    BlockObjective,
)
from iatrain.engine.eligibility import (
    ALLOW_AGENT_INTERPRETATION,
    analyze_participant_eligibility,
)
from iatrain.engine.generation import generate_block_proposal
from iatrain.engine.guidelines import athlete_prescription_profile
from iatrain.engine.agent import (
    AgentBlockResult,
    AgentNeedsCoachDecision,
    _validate_agent_context_invariants,
)
from iatrain.engine.services import (
    apply_generation_run,
    generate_block_run,
    resume_generation_run,
)
from iatrain.engine.validation import validate_block_generation_proposal
from iatrain.models import (
    AthleteCondition,
    AthleteProfile,
    BlockGenerationRun,
    BlockParticipantAssignment,
    CoachProfile,
    SessionParticipantPlan,
    TrainingGroup,
    TrainingSession,
)
from iatrain.training.services import create_session_revision, create_training_session
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseRevision
from organizations.models import Organization


class PersonalizedBlockGenerationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="personalized-engine")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.is_provisional = False
        self.person.save()
        CoachProfile.objects.create(person=self.person)
        self.organization = Organization.objects.create(
            name="Club personalització", slug="club-personalitzacio"
        )
        self.group = TrainingGroup.objects.create(
            organization=self.organization, name="Grup de prova"
        )
        self.session = create_training_session(
            user=self.user,
            organization=self.organization,
            scheduled_start=timezone.now(),
            expected_duration_minutes=60,
            discipline=TrainingSession.Discipline.TRAMPOLINE,
            session_scope=TrainingSession.Scope.GROUP,
            training_group=self.group,
        )
        self.revision = create_session_revision(
            user=self.user,
            session=self.session,
            title="Sessió personalitzada",
            general_objective="Preparació física individualitzada.",
            planned_duration_minutes=60,
        )
        self.athlete_a = self._athlete("Aina", date(2008, 4, 5))
        self.athlete_b = self._athlete("Berta", date(2007, 6, 7))
        self.plan_a = SessionParticipantPlan.objects.create(
            session_revision=self.revision, athlete_profile=self.athlete_a
        )
        self.plan_b = SessionParticipantPlan.objects.create(
            session_revision=self.revision, athlete_profile=self.athlete_b
        )
        self.catalog = ExerciseCatalog.objects.create(
            owner=self.person,
            code="personalized-engine",
            name="Catàleg personalitzat",
        )
        self.squat = self._exercise("squat", "Esquat", "squat")
        self.trunk = self._exercise("dead-bug", "Dead bug", "trunk_control")

    def _athlete(self, first_name, birth_date):
        person = Person.objects.create(first_name=first_name, birth_date=birth_date)
        return AthleteProfile.objects.create(person=person)

    def _exercise(self, code, name, movement_pattern):
        family = Exercise.objects.create(
            catalog=self.catalog,
            code=f"{code}-family",
            name=f"Família {name}",
            kind=Exercise.Kind.FAMILY,
            created_by=self.person,
        )
        exercise = Exercise.objects.create(
            catalog=self.catalog,
            code=code,
            name=name,
            kind=Exercise.Kind.VARIANT,
            parent=family,
            created_by=self.person,
        )
        return ExerciseRevision.objects.create(
            exercise=exercise,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=movement_pattern,
            description="Exercici de prova.",
            setup="Posició inicial estable.",
            execution="Execució controlada.",
            coaching_cues="Mantén el control.",
            authored_by=self.person,
        )

    def _request(self):
        return BlockGenerationRequest(
            session_revision_id=self.revision.pk,
            sequence_index=1,
            name="Força coordinada",
            block_role="main",
            planned_duration_minutes=10,
            objective=BlockObjective(
                description="Millorar força i control.",
                primary_quality="strength",
                movement_patterns=("squat",),
            ),
            participant_plan_ids=(self.plan_a.pk, self.plan_b.pk),
            target_intensity="moderate",
            contract_version="2.0",
        )

    def _confirm_stop_condition(self):
        condition = propose_athlete_condition(
            user=self.user,
            athlete=self.athlete_b,
            organization=self.organization,
            category=AthleteCondition.Category.MEDICAL_RESTRICTION,
            title="No entrenar temporalment",
            narrative="Indicació comunicada que impedeix l'activitat física.",
            source=AthleteCondition.Source.CLINICAL_DOCUMENT,
            severity=5,
            training_impact=AthleteCondition.TrainingImpact.STOP,
        )
        return review_athlete_condition(
            user=self.user, condition=condition, accept=True
        )

    def _awaiting_stop_run(self):
        self._confirm_stop_condition()
        return generate_block_run(
            user=self.user,
            revision=self.revision,
            prompt="Força general de baixa complexitat",
            duration_minutes=10,
            block_role="main",
        )

    def _agent_result_after_exclusion(self):
        from dataclasses import replace
        from iatrain.engine.context import build_block_engine_context

        request = replace(
            self._request(),
            participant_plan_ids=(self.plan_a.pk,),
            excluded_participant_plan_ids=(self.plan_b.pk,),
            contract_version="3.0",
        )
        context = build_block_engine_context(user=self.user, revision=self.revision)
        proposal = generate_block_proposal(context=context, request=request)
        return AgentBlockResult(
            proposal=proposal,
            interpretation_payload={"intent_status": "ready"},
            model_name="gpt-test",
            tool_trace=(),
            response_ids=("resp-test",),
            usage_payload={},
            validation_payload={"attempts": [{"valid": True, "errors": []}]},
        )

    def test_stop_becomes_coach_decision_and_resume_excludes_only_from_block(self):
        run = self._awaiting_stop_run()

        self.assertEqual(run.status, BlockGenerationRun.Status.AWAITING_DECISION)
        self.assertEqual(
            run.decision_payload["issues"][0]["reason_code"],
            "active_training_stop",
        )

        with patch(
            "iatrain.engine.services.plan_block_with_agent",
            return_value=self._agent_result_after_exclusion(),
        ) as agent_call:
            run = resume_generation_run(
                user=self.user,
                run=run,
                decisions={str(self.plan_b.pk): "exclude_from_block"},
            )

        agent_call.assert_called_once()
        self.assertEqual(run.status, BlockGenerationRun.Status.PROPOSED)
        self.assertEqual(run.request_payload["participant_plan_ids"], [self.plan_a.pk])
        self.assertEqual(
            run.request_payload["excluded_participant_plan_ids"], [self.plan_b.pk]
        )

        block = apply_generation_run(user=self.user, run=run)
        assignments = {
            row.participant_plan_id: row.mode
            for row in BlockParticipantAssignment.objects.filter(block=block)
        }
        self.assertEqual(assignments[self.plan_a.pk], "shared")
        self.assertEqual(assignments[self.plan_b.pk], "excluded")
        self.assertTrue(
            self.revision.participant_plans.filter(pk=self.plan_b.pk).exists()
        )

    def test_unknown_condition_scope_requires_a_visible_coach_decision(self):
        condition = propose_athlete_condition(
            user=self.user,
            athlete=self.athlete_a,
            organization=self.organization,
            category=AthleteCondition.Category.INJURY,
            title="Condició sense regió concretada",
            narrative="Cal evitar moviments que encara no s'han classificat.",
            source=AthleteCondition.Source.ATHLETE_REPORT,
            training_impact=AthleteCondition.TrainingImpact.AVOID,
        )
        review_athlete_condition(user=self.user, condition=condition, accept=True)
        from iatrain.engine.context import build_block_engine_context

        context = build_block_engine_context(user=self.user, revision=self.revision)
        review = analyze_participant_eligibility(context=context)

        issue = next(
            row
            for row in review.issues
            if row["reason_code"] == "condition_scope_unknown"
        )
        self.assertEqual(issue["decision_key"], f"condition_{condition.pk}")

        resolved = analyze_participant_eligibility(
            context=context,
            decisions={
                f"condition_{condition.pk}": ALLOW_AGENT_INTERPRETATION
            },
        )
        self.assertFalse(resolved.needs_decision)
        payload_condition = next(
            row
            for athlete in context.athletes
            if athlete.participant_plan_id == self.plan_a.pk
            for row in athlete.payload["active_conditions"]
            if row["id"] == condition.pk
        )
        self.assertEqual(
            payload_condition["coach_scope_decision"],
            ALLOW_AGENT_INTERPRETATION,
        )

    def test_an_active_participant_cannot_skip_the_entire_block(self):
        from dataclasses import replace
        from iatrain.engine.context import build_block_engine_context

        context = build_block_engine_context(user=self.user, revision=self.revision)
        proposal = generate_block_proposal(context=context, request=self._request())
        items = tuple(
            replace(
                item,
                athlete_adjustments=(
                    AthleteAdjustmentProposal(
                        participant_plan_id=self.plan_a.pk,
                        action="skip",
                        rationale="Prova d'omissió total.",
                    ),
                    AthleteAdjustmentProposal(
                        participant_plan_id=self.plan_b.pk,
                        action="skip",
                        rationale="Prova d'omissió total.",
                    ),
                ),
            )
            for item in proposal.items
        )
        proposal = replace(proposal, items=items)

        with self.assertRaisesMessage(
            ValidationError, "no pot ometre tots els exercicis"
        ):
            validate_block_generation_proposal(
                proposal,
                revision=self.revision,
                exercise_owner=self.person,
            )

    def test_awaiting_decision_is_rendered_and_can_continue_from_the_session(self):
        run = self._awaiting_stop_run()
        self.client.force_login(self.user)
        detail_url = (
            reverse("iatrain_session_detail", args=(self.session.pk,))
            + f"?revision={self.revision.pk}&generation={run.pk}"
        )

        response = self.client.get(detail_url)

        self.assertContains(response, "Decisions necessàries per continuar")
        self.assertContains(response, "Excloure-la només d&#x27;aquest bloc")

        with patch(
            "iatrain.views.engine.generation.execute_block_generation_task.delay"
        ) as delayed_task:
            response = self.client.post(
                reverse(
                    "iatrain_block_generation_decide", args=(self.session.pk, run.pk)
                ),
                {f"decision_{self.plan_b.pk}": "exclude_from_block"},
            )

        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.status, BlockGenerationRun.Status.PROCESSING)
        delayed_task.assert_called_once_with(run.pk, self.user.pk)

        progress_url = reverse(
            "iatrain_block_generation_status", args=(self.session.pk, run.pk)
        )
        progress = self.client.get(progress_url)
        self.assertEqual(progress.status_code, 200)
        self.assertFalse(progress.json()["terminal"])
        self.assertEqual(progress.json()["progress"]["stage"], "queued")

        detail = self.client.get(
            reverse("iatrain_session_detail", args=(self.session.pk,))
            + f"?revision={self.revision.pk}&generation={run.pk}"
        )
        self.assertContains(detail, "data-generation-progress")
        self.assertContains(detail, "Decisions rebudes; reprenent la planificació")

    def test_agentic_summary_renders_without_legacy_reasoning_summary(self):
        run = self._awaiting_stop_run()
        with patch(
            "iatrain.engine.services.plan_block_with_agent",
            return_value=self._agent_result_after_exclusion(),
        ):
            run = resume_generation_run(
                user=self.user,
                run=run,
                decisions={str(self.plan_b.pk): "exclude_from_block"},
            )
        run.interpretation_payload = {
            "intent_status": "ready",
            "planning_summary": "Resum agentiu vigent.",
        }
        run.save(update_fields=("interpretation_payload", "updated_at"))
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("iatrain_session_detail", args=(self.session.pk,))
            + f"?revision={self.revision.pk}&generation={run.pk}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resum agentiu vigent.")
        self.assertContains(response, "Afegir a la sessió")

    def test_agent_blocker_is_rendered_and_can_resume_with_a_structured_decision(self):
        blocker = AgentNeedsCoachDecision(
            "Cal autorització editorial.",
            issues=(
                {
                    "decision_key": "catalog_drafts",
                    "reason_code": "draft_exercises_required",
                    "title": "Només hi ha candidats útils en esborrany",
                    "explanation": "Cal decidir si es poden utilitzar.",
                    "choices": [
                        {
                            "value": "allow_draft_exercises",
                            "label": "Permetre aquests esborranys",
                        }
                    ],
                    "profile_review_available": False,
                },
            ),
        )
        with patch(
            "iatrain.engine.services.plan_block_with_agent", side_effect=blocker
        ):
            run = generate_block_run(
                user=self.user,
                revision=self.revision,
                prompt="Força general",
                duration_minutes=10,
                block_role="main",
            )

        self.assertEqual(run.status, BlockGenerationRun.Status.AWAITING_DECISION)
        self.assertEqual(run.decision_payload["kind"], "generation_blockers")
        self.client.force_login(self.user)
        detail = self.client.get(
            reverse("iatrain_session_detail", args=(self.session.pk,))
            + f"?revision={self.revision.pk}&generation={run.pk}"
        )
        self.assertContains(detail, "Només hi ha candidats útils en esborrany")

        with patch(
            "iatrain.views.engine.generation.execute_block_generation_task.delay"
        ) as delayed_task:
            response = self.client.post(
                reverse(
                    "iatrain_block_generation_decide", args=(self.session.pk, run.pk)
                ),
                {"decision_catalog_drafts": "allow_draft_exercises"},
            )

        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.status, BlockGenerationRun.Status.PROCESSING)
        self.assertEqual(
            run.coach_decisions["catalog_drafts"], "allow_draft_exercises"
        )
        delayed_task.assert_called_once_with(run.pk, self.user.pk)

    def test_avoid_condition_receives_an_individual_replacement(self):
        payload_a = {"athlete": {"age_years": 18}, "sport_profiles": []}
        payload_b = {
            "athlete": {"age_years": 19},
            "sport_profiles": [],
            "active_conditions": [
                {
                    "id": 901,
                    "title": "Evitar càrrega de genoll",
                    "training_impact": "avoid",
                    "body_region": {"code": "knee"},
                }
            ],
        }
        context = BlockEngineContext(
            revision=self.revision,
            owner=self.person,
            athletes=(
                AthleteEngineContext(
                    participant_plan_id=self.plan_a.pk,
                    payload=payload_a,
                    prescription_profile=athlete_prescription_profile(payload_a),
                ),
                AthleteEngineContext(
                    participant_plan_id=self.plan_b.pk,
                    payload=payload_b,
                    prescription_profile=athlete_prescription_profile(payload_b),
                ),
            ),
            available_equipment_ids=(),
            available_equipment_codes=frozenset(),
            warnings=(),
        )

        proposal = generate_block_proposal(context=context, request=self._request())

        adjustments = [
            adjustment
            for item in proposal.items
            for adjustment in item.athlete_adjustments
            if adjustment.participant_plan_id == self.plan_b.pk
        ]
        self.assertTrue(adjustments)
        self.assertTrue(
            any(
                adjustment.action == "replace"
                and adjustment.replacement_exercise_revision_id == self.trunk.pk
                for adjustment in adjustments
            )
        )
        participant = next(
            row
            for row in proposal.participants
            if row.participant_plan_id == self.plan_b.pk
        )
        self.assertEqual(participant.mode, "personalized")

    def test_v31_requires_a_structured_decision_for_each_avoid_condition(self):
        payload = {
            "athlete": {"age_years": 19},
            "sport_profiles": [],
            "active_conditions": [
                {
                    "id": 902,
                    "title": "Evitar càrrega de genoll",
                    "training_impact": "avoid",
                    "body_region": {"code": "knee"},
                }
            ],
        }
        context = BlockEngineContext(
            revision=self.revision,
            owner=self.person,
            athletes=(
                AthleteEngineContext(
                    participant_plan_id=self.plan_b.pk,
                    payload=payload,
                    prescription_profile=athlete_prescription_profile(payload),
                ),
            ),
            available_equipment_ids=(),
            available_equipment_codes=frozenset(),
            warnings=(),
        )
        request = replace(
            self._request(),
            participant_plan_ids=(self.plan_b.pk,),
            contract_version="3.1",
        )
        proposal = generate_block_proposal(context=context, request=request)
        proposal = replace(proposal, contract_version="3.1")

        with self.assertRaisesMessage(
            ValidationError, "necessita una decisió estructurada"
        ):
            _validate_agent_context_invariants(proposal=proposal, context=context)

    def test_missing_age_is_context_for_the_agent_not_a_preflight_block(self):
        payload = {"athlete": {"age_years": None}, "sport_profiles": []}
        context = BlockEngineContext(
            revision=self.revision,
            owner=self.person,
            athletes=(
                AthleteEngineContext(
                    participant_plan_id=self.plan_a.pk,
                    payload=payload,
                    prescription_profile=athlete_prescription_profile(payload),
                ),
            ),
            available_equipment_ids=(),
            available_equipment_codes=frozenset(),
            warnings=(),
        )

        review = analyze_participant_eligibility(context=context)
        self.assertFalse(review.needs_decision)
        self.assertEqual(review.active_participant_plan_ids, (self.plan_a.pk,))
