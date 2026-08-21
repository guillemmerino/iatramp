from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from iatrain.engine import (
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
    apply_block_generation_proposal,
    validate_block_generation_proposal,
)
from iatrain.engine.context import AthleteEngineContext, BlockEngineContext
from iatrain.engine.generation import generate_block_proposal
from iatrain.engine.guidelines import athlete_prescription_profile, resolve_guideline
from iatrain.engine.openai import OpenAITrainingUnavailable, interpret_block_prompt
from iatrain.engine.services import generate_block_run
from iatrain.models import (
    AthleteProfile,
    BlockGenerationRun,
    CoachProfile,
    SessionItemAlternative,
    SessionItemAthleteAdjustment,
    SessionParticipantPlan,
    TrainingBlock,
    TrainingSession,
    TrainingSessionItem,
)
from iatrain.training.services import create_session_revision, create_training_session
from iatrain_exercises.models import (
    Exercise,
    ExerciseCatalog,
    ExerciseObjective,
    ExercisePrescriptionGuideline,
    ExerciseRevision,
)
from organizations.models import Organization


class EngineBlockContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="engine-contract")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.is_provisional = False
        self.person.save()
        CoachProfile.objects.create(person=self.person)
        self.organization = Organization.objects.create(
            name="Club motor", slug="club-motor"
        )
        athlete_person = Person.objects.create(first_name="Aina", last_name="Serra")
        self.athlete = AthleteProfile.objects.create(person=athlete_person)
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
            title="Sessió del motor",
            general_objective="Preparar les recepcions.",
            planned_duration_minutes=60,
        )
        self.participant = SessionParticipantPlan.objects.create(
            session_revision=self.revision,
            athlete_profile=self.athlete,
        )
        self.catalog = ExerciseCatalog.objects.create(
            owner=self.person,
            code="engine-contract",
            name="Catàleg del motor",
        )
        self.family = Exercise.objects.create(
            catalog=self.catalog,
            code="lower-body",
            name="Tren inferior",
            kind=Exercise.Kind.FAMILY,
            created_by=self.person,
        )
        self.exercise = self._exercise_revision("squat", "Esquat")
        self.alternative = self._exercise_revision("split-squat", "Esquat dividit")

    def _exercise_revision(self, code, name):
        exercise = Exercise.objects.create(
            catalog=self.catalog,
            code=code,
            name=name,
            kind=Exercise.Kind.VARIANT,
            parent=self.family,
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
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Patró de força del tren inferior.",
            setup="Peus estables.",
            execution="Flexionar i estendre genolls i maluc.",
            coaching_cues="Genolls alineats.",
            authored_by=self.person,
        )

    def _proposal(self):
        request = BlockGenerationRequest(
            session_revision_id=self.revision.pk,
            sequence_index=1,
            name="Activació de recepcions",
            block_role="preparation",
            planned_duration_minutes=15,
            objective=BlockObjective(
                description="Preparar el control de les recepcions.",
                primary_quality="motor_control",
                movement_patterns=("squat", "ankle_dominant"),
            ),
            participant_plan_ids=(self.participant.pk,),
            execution_mode="circuit",
            target_intensity="moderate",
            hard_constraints=("avoid_high_impact",),
            rounds=2,
            rest_between_rounds_seconds=45,
        )
        return BlockGenerationProposal(
            request=request,
            items=(
                BlockItemProposal(
                    sequence_index=1,
                    item_type="physical_exercise",
                    title="Esquat",
                    instructions="Execució controlada.",
                    coaching_cues="Tronc estable.",
                    selection_rationale="Prepara el patró de recepció amb poc impacte.",
                    dose=ExerciseDoseProposal(
                        exercise_revision_id=self.exercise.pk,
                        dose_mode="repetitions",
                        sets=3,
                        repetitions=8,
                        intensity_metric="rpe",
                        intensity_value=Decimal("6"),
                        rest_between_sets_seconds=45,
                    ),
                    alternatives=(
                        ExerciseAlternativeProposal(
                            exercise_revision_id=self.alternative.pk,
                            trigger="coach_decision",
                            rationale="Permet treball unilateral si l'entrenador ho prefereix.",
                        ),
                    ),
                    athlete_adjustments=(
                        AthleteAdjustmentProposal(
                            participant_plan_id=self.participant.pk,
                            repetitions=6,
                            rationale="Reducció inicial de volum per tolerància individual.",
                        ),
                    ),
                ),
                BlockItemProposal(
                    sequence_index=2,
                    item_type="instruction",
                    title="Explicar criteris de recepció",
                    planned_duration_seconds=60,
                ),
            ),
            estimated_duration_seconds=780,
            estimated_load=BlockLoadEstimate(
                mechanical_impact=Decimal("1.5"),
                neuromuscular=Decimal("2.5"),
                metabolic=Decimal("2"),
                coordinative=Decimal("3"),
            ),
            coverage=BlockCoverage(
                physical_qualities=("motor_control",),
                movement_patterns=("squat",),
                body_region_codes=("ankle", "knee"),
            ),
            satisfied_constraints=("avoid_high_impact",),
            warnings=("Confirmar tolerància després de la primera ronda.",),
            confidence=Decimal("0.88"),
            generator_reference="deterministic-test-v1",
        )

    def test_adapter_persists_complete_validated_block_graph(self):
        proposal = self._proposal()

        block = apply_block_generation_proposal(user=self.user, proposal=proposal)

        self.assertEqual(block.domain, TrainingBlock.Domain.PHYSICAL)
        self.assertEqual(block.items.count(), 2)
        item = block.items.get(sequence_index=1)
        self.assertEqual(item.physical_prescription.repetitions, 8)
        self.assertEqual(SessionItemAlternative.objects.get().exercise_revision, self.alternative)
        adjustment = SessionItemAthleteAdjustment.objects.get()
        self.assertEqual(adjustment.participant_plan, self.participant)
        self.assertEqual(adjustment.repetitions, 6)

    def test_validator_rejects_unmet_hard_constraints_before_writing(self):
        proposal = replace(
            self._proposal(),
            satisfied_constraints=(),
            unmet_constraints=("avoid_high_impact",),
        )

        with self.assertRaises(ValidationError):
            validate_block_generation_proposal(
                proposal,
                revision=self.revision,
                exercise_owner=self.person,
            )
        self.assertFalse(TrainingBlock.objects.exists())

    def test_v31_rejects_personalized_participant_without_structured_adjustment(self):
        base = self._proposal()
        item = replace(base.items[0], athlete_adjustments=())
        request = replace(base.request, contract_version="3.1")
        proposal = replace(
            base,
            request=request,
            items=(item, *base.items[1:]),
            participants=(
                BlockParticipantProposal(
                    participant_plan_id=self.participant.pk,
                    mode="personalized",
                    rationale="Necessita una adaptació.",
                ),
            ),
            contract_version="3.1",
        )

        with self.assertRaisesMessage(
            ValidationError, "no té cap ajustament estructurat"
        ):
            validate_block_generation_proposal(
                proposal,
                revision=self.revision,
                exercise_owner=self.person,
            )

    def test_v31_rejects_individual_instruction_hidden_in_shared_dose_notes(self):
        base = self._proposal()
        dose = replace(
            base.items[0].dose,
            execution_notes=f"Per a la participant {self.participant.pk}, redueix el rang.",
        )
        item = replace(base.items[0], dose=dose)
        request = replace(base.request, contract_version="3.1")
        proposal = replace(
            base,
            request=request,
            items=(item, *base.items[1:]),
            participants=(
                BlockParticipantProposal(
                    participant_plan_id=self.participant.pk,
                    mode="personalized",
                    rationale="Volum reduït.",
                ),
            ),
            contract_version="3.1",
        )

        with self.assertRaisesMessage(
            ValidationError, "han d'anar a athlete_adjustments"
        ):
            validate_block_generation_proposal(
                proposal,
                revision=self.revision,
                exercise_owner=self.person,
            )

    def test_validator_rejects_a_block_that_does_not_cover_all_participants(self):
        second_athlete = AthleteProfile.objects.create(
            person=Person.objects.create(first_name="Berta", last_name="Rius")
        )
        SessionParticipantPlan.objects.create(
            session_revision=self.revision,
            athlete_profile=second_athlete,
        )

        with self.assertRaises(ValidationError):
            validate_block_generation_proposal(
                self._proposal(),
                revision=self.revision,
                exercise_owner=self.person,
            )

    def test_adapter_rolls_back_the_whole_block_on_a_late_persistence_error(self):
        proposal = self._proposal()

        with patch(
            "iatrain.training.models.planning.PhysicalExercisePrescription.save",
            side_effect=RuntimeError("persistence failed"),
        ):
            with self.assertRaises(RuntimeError):
                apply_block_generation_proposal(user=self.user, proposal=proposal)

        self.assertFalse(TrainingBlock.objects.exists())
        self.assertFalse(TrainingSessionItem.objects.exists())

    def test_age_stage_and_training_experience_are_independent(self):
        child_elite = athlete_prescription_profile(
            {
                "athlete": {"age_years": 10},
                "sport_profiles": [{"level_code": "alt_rendiment"}],
            }
        )
        adult_sedentary = athlete_prescription_profile(
            {"athlete": {"age_years": 42}, "sport_profiles": []}
        )

        self.assertEqual(child_elite.population_stage, "child")
        self.assertEqual(child_elite.experience_level, "advanced")
        self.assertEqual(adult_sedentary.population_stage, "adult")
        self.assertEqual(adult_sedentary.experience_level, "novice")

        adult_elite = athlete_prescription_profile(
            {
                "athlete": {"age_years": 25},
                "sport_profiles": [{"level_code": "alt_rendiment"}],
            }
        )
        child_guide = resolve_guideline(
            self.exercise,
            profile=child_elite,
            objective=ExerciseObjective.Objective.MAX_STRENGTH,
            block_role="main",
        )
        adult_guide = resolve_guideline(
            self.exercise,
            profile=adult_elite,
            objective=ExerciseObjective.Objective.MAX_STRENGTH,
            block_role="main",
        )
        self.assertGreater(child_guide.min_repetitions, adult_guide.min_repetitions)
        self.assertLess(child_guide.max_rpe, adult_guide.max_rpe)

    def test_generator_uses_exercise_specific_guideline_and_returns_valid_proposal(self):
        ExerciseObjective.objects.create(
            revision=self.exercise,
            objective=ExerciseObjective.Objective.GENERAL_STRENGTH,
            priority=ExerciseObjective.Priority.PRIMARY,
            rationale="Patró principal de força.",
        )
        ExercisePrescriptionGuideline.objects.create(
            revision=self.exercise,
            population_stage=ExercisePrescriptionGuideline.PopulationStage.ALL,
            experience_level=ExercisePrescriptionGuideline.ExperienceLevel.ALL,
            objective=ExerciseObjective.Objective.GENERAL_STRENGTH,
            block_role=ExercisePrescriptionGuideline.BlockRole.MAIN,
            dose_mode=ExercisePrescriptionGuideline.DoseMode.REPETITIONS,
            min_sets=1,
            default_sets=2,
            max_sets=3,
            min_repetitions=4,
            default_repetitions=6,
            max_repetitions=8,
            min_rest_seconds=30,
            default_rest_seconds=60,
            max_rest_seconds=90,
            min_rpe=Decimal("4"),
            max_rpe=Decimal("7"),
            setup_duration_seconds=15,
            seconds_per_repetition=Decimal("4"),
            mechanical_impact=Decimal("2"),
            neuromuscular_load=Decimal("3"),
            metabolic_load=Decimal("2"),
            coordinative_load=Decimal("2"),
            quality_stop_rule="Atura si es perd el patró.",
            evidence_type=ExercisePrescriptionGuideline.EvidenceType.PROFESSIONAL_STANDARD,
            source_title="Guia interna validada",
            rationale="Rang de prova governat per la revisió.",
        )
        athlete_payload = {"athlete": {"age_years": 25}, "sport_profiles": []}
        context = BlockEngineContext(
            revision=self.revision,
            owner=self.person,
            athletes=(
                AthleteEngineContext(
                    participant_plan_id=self.participant.pk,
                    payload=athlete_payload,
                    prescription_profile=athlete_prescription_profile(athlete_payload),
                ),
            ),
            available_equipment_ids=(),
            available_equipment_codes=frozenset(),
            warnings=(),
        )
        request = BlockGenerationRequest(
            session_revision_id=self.revision.pk,
            sequence_index=1,
            name="Força bàsica",
            block_role="main",
            planned_duration_minutes=10,
            objective=BlockObjective(
                description="Millorar la força general.",
                primary_quality="strength",
                movement_patterns=("squat",),
            ),
            participant_plan_ids=(self.participant.pk,),
            target_intensity="moderate",
        )

        proposal = generate_block_proposal(context=context, request=request)

        self.assertEqual(proposal.items[0].dose.exercise_revision_id, self.exercise.pk)
        self.assertEqual(proposal.items[0].dose.sets, 2)
        self.assertEqual(proposal.items[0].dose.repetitions, 6)
        self.assertIn("Guia interna validada", proposal.items[0].selection_rationale)
        self.assertLessEqual(proposal.estimated_duration_seconds, 600)

    def test_llm_interpretation_cannot_override_server_owned_context(self):
        athlete_payload = {"athlete": {"age_years": 16}, "sport_profiles": []}
        context = BlockEngineContext(
            revision=self.revision,
            owner=self.person,
            athletes=(
                AthleteEngineContext(
                    participant_plan_id=self.participant.pk,
                    payload=athlete_payload,
                    prescription_profile=athlete_prescription_profile(athlete_payload),
                ),
            ),
            available_equipment_ids=(),
            available_equipment_codes=frozenset(),
            warnings=(),
        )
        interpreted_payload = {
            "clarification_needed": False,
            "clarification_question": "",
            "reasoning_summary": "Bloc progressiu adequat al context.",
            "request": {
                "name": "Control i força",
                "block_role": "recovery",
                "planned_duration_minutes": 55,
                "execution_mode": "circuit",
                "objective_description": "Millorar el control en recepcions.",
                "primary_quality": "motor_control",
                "secondary_qualities": ["strength"],
                "movement_patterns": ["squat"],
                "body_region_codes": ["knee"],
                "target_intensity": "moderate",
                "hard_constraints": ["avoid_failure"],
                "preferences": ["progressió simple"],
                "instructions": "Prioritza qualitat.",
                "rounds": 2,
                "rest_between_rounds_seconds": 45,
            },
            "sources": [
                {
                    "title": "Font no segura",
                    "url": "javascript:alert(1)",
                    "applicability": "No s'ha de convertir en un enllaç.",
                }
            ],
        }

        with patch(
            "iatrain.engine.openai._call_responses_api",
            return_value=(interpreted_payload, "gpt-test"),
        ):
            result = interpret_block_prompt(
                context=context,
                prompt="Vull control de recepcions",
                duration_minutes=12,
                block_role="main",
            )

        self.assertEqual(result.request.session_revision_id, self.revision.pk)
        self.assertEqual(result.request.participant_plan_ids, (self.participant.pk,))
        self.assertEqual(result.request.planned_duration_minutes, 12)
        self.assertEqual(result.request.block_role, "main")
        self.assertEqual(result.source_references[0]["url"], "")

    def test_failed_provider_call_is_kept_as_an_auditable_generation_run(self):
        with patch(
            "iatrain.engine.services.plan_block_with_agent",
            side_effect=OpenAITrainingUnavailable("Servei temporalment no disponible."),
        ):
            with self.assertRaises(OpenAITrainingUnavailable):
                generate_block_run(
                    user=self.user,
                    revision=self.revision,
                    prompt="Força general amb control de recepció",
                    duration_minutes=12,
                    block_role="main",
                )

        run = BlockGenerationRun.objects.get()
        self.assertEqual(run.status, BlockGenerationRun.Status.FAILED)
        self.assertEqual(run.error_code, "openai_unavailable")
        self.assertNotIn("api", run.error_message.casefold())
