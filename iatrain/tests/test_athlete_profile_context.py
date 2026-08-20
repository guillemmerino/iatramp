from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from core.services import merge_people
from iatrain.athletes.context import build_athlete_profile_context
from iatrain.athletes.services import (
    attach_athlete_insight_evidence,
    propose_athlete_condition,
    propose_athlete_insight,
    record_athlete_measurement,
    review_athlete_condition,
    review_athlete_insight,
    set_athlete_sport_profile,
)
from iatrain.models import (
    AthleteCondition,
    AthleteInsight,
    AthleteMeasurement,
    AthleteProfile,
    AthleteSportProfile,
    CoachAthleteRelation,
    CoachProfile,
    SessionParticipantPlan,
    TrainingBlock,
    TrainingItemResult,
    TrainingSession,
    TrainingSessionExecution,
    TrainingSessionItem,
    TrainingSessionRevision,
)
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseRevision
from organizations.models import Organization


class AthleteLivingProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="profile-owner", password="unused"
        )
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.is_provisional = False
        self.person.save()
        self.coach_profile = CoachProfile.objects.create(person=self.person)
        self.organization = Organization.objects.create(
            name="Club perfil viu", slug="club-perfil-viu", created_by=self.person
        )
        athlete_person = Person.objects.create(
            first_name="Aina",
            last_name="Serra",
            birth_date=timezone.localdate().replace(year=timezone.localdate().year - 16),
        )
        self.athlete_profile = AthleteProfile.objects.create(person=athlete_person)

    def measurement(self, **overrides):
        values = {
            "user": self.user,
            "athlete": self.athlete_profile,
            "organization": self.organization,
            "domain": AthleteMeasurement.Domain.POWER,
            "metric_code": "countermovement_jump",
            "metric_label": "Salt amb contramoviment",
            "value": Decimal("31.4"),
            "unit": "cm",
            "source": AthleteMeasurement.Source.ASSESSMENT,
            "protocol": "Tres intents; es conserva el millor.",
        }
        values.update(overrides)
        return record_athlete_measurement(**values)

    def test_measurements_form_history_and_corrections_do_not_rewrite_evidence(self):
        first = self.measurement(value=Decimal("29.2"))
        second = self.measurement(value=Decimal("31.4"))
        correction = self.measurement(
            value=Decimal("31.1"),
            measured_at=second.measured_at,
            supersedes=second,
        )

        first.value = Decimal("40")
        with self.assertRaises(ValidationError):
            first.save()

        context = build_athlete_profile_context(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
        )
        self.assertEqual(context["latest_measurements"][0]["value"], "31.1000")
        values = context["measurement_history"][0]["values"]
        self.assertEqual([row["value"] for row in values], ["31.1000", "29.2000"])
        self.assertNotIn("31.4000", [row["value"] for row in values])

    def test_condition_is_not_authoritative_until_a_human_confirms_it(self):
        condition = propose_athlete_condition(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
            category=AthleteCondition.Category.DISCOMFORT,
            title="Molèstia ocasional al turmell",
            narrative="La gimnasta comunica molèstia després de les recepcions repetides.",
            evidence="Apareix després del tercer bloc; no apareix a l'escalfament.",
            source=AthleteCondition.Source.ATHLETE_REPORT,
            severity=2,
            training_impact=AthleteCondition.TrainingImpact.MODIFY,
        )
        proposed_context = build_athlete_profile_context(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
        )
        self.assertEqual(proposed_context["active_conditions"], [])

        review_athlete_condition(user=self.user, condition=condition, accept=True)
        confirmed_context = build_athlete_profile_context(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
        )
        self.assertEqual(confirmed_context["active_conditions"][0]["severity"], 2)
        self.assertTrue(
            confirmed_context["selection_guardrails"]["has_training_modifiers"]
        )

    def test_insight_requires_typed_evidence_and_remains_separate_from_facts(self):
        measurement = self.measurement()
        insight = propose_athlete_insight(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
            kind=AthleteInsight.Kind.PROGRESS,
            statement="La potència de salt mostra una millora recent.",
            rationale="La mesura actual supera la referència anterior amb el mateix protocol.",
            confidence=Decimal("0.780"),
            model_name="profile-test-model",
        )
        with self.assertRaises(ValidationError):
            review_athlete_insight(user=self.user, insight=insight, accept=True)

        attach_athlete_insight_evidence(
            user=self.user,
            insight=insight,
            measurement=measurement,
            contribution="Mesura recent del salt amb contramoviment.",
        )
        review_athlete_insight(user=self.user, insight=insight, accept=True)
        context = build_athlete_profile_context(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
        )
        self.assertEqual(context["confirmed_insights"][0]["status"], "confirmed")
        self.assertEqual(
            context["confirmed_insights"][0]["evidence"][0]["type"], "measurement"
        )
        self.assertEqual(context["proposed_insights"], [])

    def test_context_marks_health_data_as_unknown_without_explicit_permission(self):
        condition = propose_athlete_condition(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
            category=AthleteCondition.Category.PAIN,
            title="Dolor comunicat",
            narrative="Dolor lleu després de salts repetits.",
            source=AthleteCondition.Source.ATHLETE_REPORT,
            training_impact=AthleteCondition.TrainingImpact.MONITOR,
        )
        review_athlete_condition(user=self.user, condition=condition, accept=True)

        coach_user = get_user_model().objects.create_user("restricted-coach")
        coach = CoachProfile.objects.create(person=coach_user.person)
        CoachAthleteRelation.objects.create(
            coach_profile=coach,
            athlete_profile=self.athlete_profile,
            organization=self.organization,
            can_edit_training=True,
            can_view_health_data=False,
        )
        context = build_athlete_profile_context(
            user=coach_user,
            athlete=self.athlete_profile,
            organization=self.organization,
        )

        self.assertFalse(context["scope"]["health_data_available"])
        self.assertEqual(context["active_conditions"], [])
        self.assertTrue(context["selection_guardrails"]["requires_health_review"])

    def test_session_results_enter_the_context_without_copying_them_to_profile(self):
        catalog = ExerciseCatalog.objects.create(
            owner=self.person, code="profile-context", name="Perfil context"
        )
        family = Exercise.objects.create(
            catalog=catalog,
            code="squat",
            name="Esquat",
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
        exercise_revision = ExerciseRevision.objects.create(
            exercise=exercise,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Exercici de força.",
            setup="Peus estables.",
            execution="Flexionar i estendre.",
            coaching_cues="Control del tronc.",
            authored_by=self.person,
        )
        session = TrainingSession.objects.create(
            organization=self.organization,
            scheduled_start=timezone.now(),
            expected_duration_minutes=45,
            discipline=TrainingSession.Discipline.TRAMPOLINE,
            session_scope=TrainingSession.Scope.INDIVIDUAL,
            responsible_coach=self.coach_profile,
            created_by=self.person,
        )
        revision = TrainingSessionRevision.objects.create(
            session=session,
            revision_number=1,
            title="Sessió de context",
            planned_duration_minutes=45,
            created_by=self.person,
        )
        SessionParticipantPlan.objects.create(
            session_revision=revision,
            athlete_profile=self.athlete_profile,
        )
        block = TrainingBlock.objects.create(
            session_revision=revision,
            sequence_index=1,
            name="Força",
            block_role=TrainingBlock.Role.MAIN,
            domain=TrainingBlock.Domain.PHYSICAL,
            planned_duration_minutes=15,
        )
        item = TrainingSessionItem.objects.create(
            block=block,
            sequence_index=1,
            item_type=TrainingSessionItem.ItemType.PHYSICAL_EXERCISE,
            title="Esquat",
        )
        TrainingSessionRevision.objects.filter(pk=revision.pk).update(
            status=TrainingSessionRevision.Status.APPROVED,
            approved_by=self.person,
            approved_at=timezone.now(),
        )
        revision.refresh_from_db()
        execution = TrainingSessionExecution.objects.create(
            session=session,
            approved_revision=revision,
            status=TrainingSessionExecution.Status.IN_PROGRESS,
            started_at=timezone.now(),
            supervised_by=self.coach_profile,
        )
        TrainingItemResult.objects.create(
            execution=execution,
            session_item=item,
            athlete_profile=self.athlete_profile,
            completion_status=TrainingItemResult.CompletionStatus.COMPLETED,
            exercise_revision_performed=exercise_revision,
            actual_sets=3,
            actual_repetitions=7,
            perceived_exertion=Decimal("7.5"),
            execution_quality=4,
            recorded_by=self.person,
        )

        context = build_athlete_profile_context(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
        )
        response = context["recent_training_responses"][0]
        self.assertEqual(response["exercise"], "Esquat amb pes corporal")
        self.assertEqual(response["actual_repetitions"], 7)
        self.assertEqual(response["perceived_exertion"], "7.5")
        self.assertEqual(AthleteMeasurement.objects.count(), 0)

    def test_identity_merge_preserves_living_profile_evidence(self):
        set_athlete_sport_profile(
            user=self.user,
            athlete=self.athlete_profile,
            organization=self.organization,
            discipline=AthleteSportProfile.Discipline.TRAMPOLINE,
            level_code="development",
        )
        measurement = self.measurement()
        canonical = Person.objects.create(first_name="Aina", last_name="Canònica")
        canonical_profile = AthleteProfile.objects.create(person=canonical)

        merge_people(
            canonical=canonical,
            duplicate=self.athlete_profile.person,
            merged_by=self.user,
        )

        measurement.refresh_from_db()
        self.assertEqual(measurement.athlete_profile, canonical_profile)
        self.assertTrue(
            canonical_profile.sport_profiles.filter(discipline="trampoline").exists()
        )
