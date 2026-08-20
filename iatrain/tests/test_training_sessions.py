from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from core.services import merge_people
from iatrain.models import (
    AthleteProfile,
    CoachProfile,
    PhysicalExercisePrescription,
    SessionAttendance,
    SessionGoal,
    SessionParticipantPlan,
    TrainingBlock,
    TrainingItemResult,
    TrainingSession,
    TrainingSessionItem,
)
from iatrain.training.services import (
    approve_session_revision,
    complete_session_execution,
    create_session_revision,
    create_training_session,
    propose_session_revision,
    start_session_execution,
)
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseRevision
from organizations.models import Organization


class TrainingSessionFoundationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="training-coach", password="unused"
        )
        self.person = self.user.person
        self.person.is_provisional = False
        self.person.first_name = "Marta"
        self.person.last_name = "Costa"
        self.person.save()
        self.coach_profile = CoachProfile.objects.create(person=self.person)
        self.organization = Organization.objects.create(
            name="Club de proves", slug="club-proves", created_by=self.person
        )
        athlete_person = Person.objects.create(first_name="Aina", last_name="Serra")
        self.athlete_profile = AthleteProfile.objects.create(person=athlete_person)
        self.exercise_revision = self._exercise_revision()

    def _exercise_revision(self):
        catalog = ExerciseCatalog.objects.create(
            owner=self.person, code="training-tests", name="Entrenament de proves"
        )
        family = Exercise.objects.create(
            catalog=catalog,
            code="squat-family",
            name="Família d'esquat",
            kind=Exercise.Kind.FAMILY,
            created_by=self.person,
        )
        exercise = Exercise.objects.create(
            catalog=catalog,
            code="bodyweight-squat",
            name="Esquat amb pes corporal",
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
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Patró bàsic de força de cames.",
            setup="Peus estables i tronc neutre.",
            execution="Flexionar i estendre maluc i genoll.",
            coaching_cues="Genolls alineats i control del tronc.",
            authored_by=self.person,
        )

    def _draft_plan(self):
        session = create_training_session(
            user=self.user,
            organization=self.organization,
            scheduled_start=timezone.now(),
            expected_duration_minutes=60,
            discipline=TrainingSession.Discipline.TRAMPOLINE,
            session_scope=TrainingSession.Scope.INDIVIDUAL,
        )
        revision = create_session_revision(
            user=self.user,
            session=session,
            title="Força de base i control de recepció",
            general_objective="Millorar la capacitat de produir i absorbir força.",
            planned_duration_minutes=60,
        )
        participant = SessionParticipantPlan.objects.create(
            session_revision=revision,
            athlete_profile=self.athlete_profile,
            individual_objective="Mantenir alineació de maluc, genoll i peu.",
        )
        SessionGoal.objects.create(
            session_revision=revision,
            domain=SessionGoal.Domain.PHYSICAL,
            code="lower-body-strength",
            description="Desenvolupar força general del tren inferior.",
            priority=SessionGoal.Priority.PRIMARY,
        )
        block = TrainingBlock.objects.create(
            session_revision=revision,
            sequence_index=1,
            name="Activació física",
            block_role=TrainingBlock.Role.PREPARATION,
            domain=TrainingBlock.Domain.PHYSICAL,
            execution_mode=TrainingBlock.ExecutionMode.SEQUENTIAL,
            planned_duration_minutes=15,
            objective="Preparar el patró d'esquat.",
        )
        item = TrainingSessionItem.objects.create(
            block=block,
            sequence_index=1,
            item_type=TrainingSessionItem.ItemType.PHYSICAL_EXERCISE,
            title="Esquat amb pes corporal",
            selection_rationale="Patró accessible per observar el control de l'atleta.",
        )
        prescription = PhysicalExercisePrescription.objects.create(
            session_item=item,
            exercise_revision=self.exercise_revision,
            dose_mode=PhysicalExercisePrescription.DoseMode.REPETITIONS,
            sets=3,
            repetitions=8,
            intensity_metric=PhysicalExercisePrescription.IntensityMetric.RPE,
            intensity_value=6,
            rest_between_sets_seconds=60,
        )
        return session, revision, participant, block, item, prescription

    def _validate_exercise(self):
        ExerciseRevision.objects.filter(pk=self.exercise_revision.pk).update(
            editorial_status="validated",
            last_validated_by=self.person,
            last_validated_at=timezone.now(),
        )
        self.exercise_revision.refresh_from_db()

    def test_session_plan_separates_block_role_domain_and_physical_dose(self):
        session, revision, participant, block, item, prescription = self._draft_plan()

        self.assertEqual(session.revisions.get(), revision)
        self.assertEqual(block.block_role, TrainingBlock.Role.PREPARATION)
        self.assertEqual(block.domain, TrainingBlock.Domain.PHYSICAL)
        self.assertEqual(item.physical_prescription, prescription)
        self.assertEqual(prescription.repetitions, 8)
        self.assertEqual(revision.participant_plans.get(), participant)

    def test_proposed_revision_locks_all_planning_details(self):
        _, revision, _, block, _, _ = self._draft_plan()

        propose_session_revision(user=self.user, revision=revision)
        block.name = "Canvi silenciós"
        with self.assertRaises(ValidationError):
            block.save()

    def test_approval_requires_validated_physical_exercises(self):
        _, revision, _, _, _, _ = self._draft_plan()
        propose_session_revision(user=self.user, revision=revision)

        with self.assertRaises(ValidationError) as context:
            approve_session_revision(user=self.user, revision=revision)

        self.assertIn("encara no està validat", str(context.exception))

    def test_approved_plan_is_executed_without_overwriting_the_prescription(self):
        session, revision, _, _, item, prescription = self._draft_plan()
        self._validate_exercise()
        propose_session_revision(user=self.user, revision=revision)
        approve_session_revision(user=self.user, revision=revision)

        execution = start_session_execution(user=self.user, session=session)
        SessionAttendance.objects.create(
            execution=execution,
            athlete_profile=self.athlete_profile,
            status=SessionAttendance.Status.PRESENT,
            joined_at=execution.started_at,
        )
        result = TrainingItemResult.objects.create(
            execution=execution,
            session_item=item,
            athlete_profile=self.athlete_profile,
            completion_status=TrainingItemResult.CompletionStatus.COMPLETED,
            exercise_revision_performed=self.exercise_revision,
            actual_sets=3,
            actual_repetitions=7,
            perceived_exertion=7.5,
            execution_quality=4,
            recorded_by=self.person,
        )
        complete_session_execution(
            user=self.user, execution=execution, general_notes="Sessió completada."
        )

        prescription.refresh_from_db()
        result.refresh_from_db()
        execution.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(prescription.repetitions, 8)
        self.assertEqual(result.actual_repetitions, 7)
        self.assertEqual(execution.approved_revision, revision)
        self.assertEqual(execution.status, execution.Status.COMPLETED)
        self.assertEqual(session.lifecycle_status, session.LifecycleStatus.COMPLETED)

    def test_result_rejects_an_athlete_not_in_the_approved_plan(self):
        session, revision, _, _, item, _ = self._draft_plan()
        self._validate_exercise()
        propose_session_revision(user=self.user, revision=revision)
        approve_session_revision(user=self.user, revision=revision)
        execution = start_session_execution(user=self.user, session=session)
        outsider = AthleteProfile.objects.create(
            person=Person.objects.create(first_name="Berta", last_name="Rius")
        )

        with self.assertRaises(ValidationError):
            TrainingItemResult.objects.create(
                execution=execution,
                session_item=item,
                athlete_profile=outsider,
                completion_status=TrainingItemResult.CompletionStatus.COMPLETED,
                exercise_revision_performed=self.exercise_revision,
                recorded_by=self.person,
            )

    def test_identity_merge_retargets_training_participation(self):
        _, revision, participant, _, _, _ = self._draft_plan()
        canonical_person = Person.objects.create(first_name="Aina", last_name="Canònica")
        canonical_profile = AthleteProfile.objects.create(person=canonical_person)

        merge_people(
            canonical=canonical_person,
            duplicate=self.athlete_profile.person,
            merged_by=self.user,
        )

        participant.refresh_from_db()
        self.assertEqual(participant.athlete_profile, canonical_profile)
        self.assertEqual(revision.participant_plans.count(), 1)
