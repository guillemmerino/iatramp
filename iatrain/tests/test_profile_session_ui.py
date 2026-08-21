from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Person
from iatrain.models import (
    AthleteCondition,
    AthleteMeasurement,
    TrainingBlock,
    TrainingSession,
    TrainingSessionItem,
)
from iatrain.services import (
    activate_athlete_profile,
    activate_coach_profile,
    set_coach_athlete_relation,
)
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseRevision
from organizations.models import Membership, MembershipRole, Organization


class ProfileAndSessionUiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ui-builder")
        self.coach = self.user.person
        self.coach.first_name = "Marta"
        self.coach.last_name = "Costa"
        self.coach.is_provisional = False
        self.coach.save()
        activate_coach_profile(person=self.coach)
        self.organization = Organization.objects.create(
            name="Club Tramuntana", slug="club-tramuntana"
        )
        membership = Membership.objects.create(
            person=self.coach, organization=self.organization
        )
        MembershipRole.objects.create(
            membership=membership, role=MembershipRole.Role.COACH
        )
        athlete_person = Person.objects.create(first_name="Aina", last_name="Serra")
        self.athlete = activate_athlete_profile(person=athlete_person)
        set_coach_athlete_relation(
            coach=self.coach,
            athlete=self.athlete,
            organization=self.organization,
            can_edit_training=True,
            can_view_health_data=True,
        )
        self.client.force_login(self.user)

    def test_living_profile_records_measurement_and_reviews_condition(self):
        detail_url = reverse("iatrain_athlete_detail", args=(self.athlete.pk,))
        response = self.client.get(detail_url)
        self.assertContains(response, "Mesures")
        self.assertContains(response, "Nova sessió")

        response = self.client.post(
            detail_url,
            {
                "action": "measurement",
                "active_tab": "measurements",
                "organization_scope": self.organization.pk,
                "measurement-domain": "strength",
                "measurement-metric_label": "Salt vertical",
                "measurement-value": "31.5",
                "measurement-unit": "cm",
                "measurement-side": "not_applicable",
                "measurement-source": "assessment",
            },
        )
        self.assertRedirects(
            response,
            f"{detail_url}?tab=measurements&organization={self.organization.pk}",
        )
        measurement = AthleteMeasurement.objects.get(athlete_profile=self.athlete)
        self.assertEqual(measurement.metric_code, "salt_vertical")

        response = self.client.post(
            detail_url,
            {
                "action": "condition",
                "active_tab": "conditions",
                "organization_scope": self.organization.pk,
                "condition-category": "discomfort",
                "condition-title": "Molèstia al turmell",
                "condition-narrative": "Apareix en recepcions repetides.",
                "condition-laterality": "right",
                "condition-severity": "2",
                "condition-training_impact": "modify",
                "condition-applicability_scope": "unknown",
                "condition-source": "coach_observation",
            },
        )
        self.assertEqual(response.status_code, 302)
        condition = AthleteCondition.objects.get(athlete_profile=self.athlete)
        review_url = reverse("iatrain_profile_review")
        self.assertContains(self.client.get(review_url), "Molèstia al turmell")
        self.client.post(
            reverse("iatrain_condition_review", args=(condition.pk,)),
            {"decision": "accept"},
        )
        condition.refresh_from_db()
        self.assertEqual(condition.status, AthleteCondition.Status.CONFIRMED)

    def test_start_form_prefills_context_and_creates_editable_session(self):
        start_url = reverse("iatrain_training_start")
        response = self.client.get(
            start_url,
            {"organization": self.organization.pk, "athlete": self.athlete.pk},
        )
        self.assertEqual(response.context["form"]["organization"].value(), str(self.organization.pk))
        self.assertEqual(
            [str(value) for value in response.context["form"]["additional_athletes"].value()],
            [str(self.athlete.pk)],
        )

        scheduled = timezone.localtime().replace(second=0, microsecond=0)
        response = self.client.post(
            start_url,
            {
                "title": "Força de recepció",
                "scheduled_start": scheduled.strftime("%Y-%m-%dT%H:%M"),
                "duration_minutes": "60",
                "discipline": "trampoline",
                "objective": "Millorar el control en les recepcions",
                "organization": self.organization.pk,
                "training_group": "",
                "additional_athletes": [self.athlete.pk],
                "gym": "",
            },
        )
        session = TrainingSession.objects.get()
        revision = session.revisions.get()
        self.assertRedirects(response, reverse("iatrain_session_detail", args=(session.pk,)))
        self.assertEqual(revision.participant_plans.get().athlete_profile, self.athlete)
        self.assertEqual(revision.goals.get().description, "Millorar el control en les recepcions")

        detail_url = reverse("iatrain_session_detail", args=(session.pk,))
        with self.settings(OPENAI_API_KEY=""):
            generation_page = self.client.get(detail_url)
            self.assertContains(generation_page, "Generar un bloc")
            self.assertContains(generation_page, "OPENAI_API_KEY")
            self.assertContains(generation_page, "Generar proposta")
        response = self.client.post(
            detail_url,
            {
                "revision": revision.pk,
                "action": "block",
                "block-sequence_index": "1",
                "block-name": "Activació",
                "block-block_role": "preparation",
                "block-domain": "physical",
                "block-execution_mode": "sequential",
                "block-planned_duration_minutes": "12",
                "block-objective": "Preparar les recepcions",
                "block-rounds": "1",
                "block-rest_between_rounds_seconds": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        block = TrainingBlock.objects.get(session_revision=revision)
        self.assertEqual(block.name, "Activació")

        exercise_revision = self._exercise_revision()
        response = self.client.post(
            reverse("iatrain_session_item_create", args=(session.pk, block.pk)),
            {
                "sequence_index": "1",
                "item_type": "physical_exercise",
                "title": "Esquat controlat",
                "rest_after_seconds": "0",
                "exercise_revision": exercise_revision.pk,
                "dose_mode": "repetitions",
                "sets": "3",
                "repetitions": "8",
                "intensity_metric": "rpe",
                "intensity_value": "6",
                "rest_between_sets_seconds": "45",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = TrainingSessionItem.objects.get(block=block)
        self.assertEqual(item.physical_prescription.repetitions, 8)
        self.assertContains(self.client.get(detail_url), "3 × 8")

        self.client.post(
            reverse("iatrain_session_block_delete", args=(session.pk, block.pk))
        )
        self.assertTrue(TrainingBlock.objects.filter(pk=block.pk).exists())
        self.client.post(
            reverse("iatrain_session_item_delete", args=(session.pk, item.pk))
        )
        self.client.post(
            reverse("iatrain_session_block_delete", args=(session.pk, block.pk))
        )
        self.assertFalse(TrainingBlock.objects.filter(pk=block.pk).exists())

    def _exercise_revision(self):
        catalog = ExerciseCatalog.objects.create(
            owner=self.coach, code="ui-builder", name="Catàleg UI"
        )
        family = Exercise.objects.create(
            catalog=catalog,
            code="squat",
            name="Esquat",
            kind=Exercise.Kind.FAMILY,
            created_by=self.coach,
        )
        exercise = Exercise.objects.create(
            catalog=catalog,
            code="controlled-squat",
            name="Esquat controlat",
            kind=Exercise.Kind.VARIANT,
            parent=family,
            created_by=self.coach,
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
            description="Esquat amb control.",
            setup="Peus estables.",
            execution="Flexió i extensió.",
            coaching_cues="Genolls alineats.",
            authored_by=self.coach,
        )
