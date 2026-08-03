from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import CoachAthleteRelation, Membership, Organization, Person


class CoreModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Club Trampolí",
            slug="club-trampoli",
        )
        self.athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        self.coach = Person.objects.create(first_name="Joan", last_name="Puig")

    def test_person_survives_account_deletion(self):
        user = get_user_model().objects.create_user(username="aina")
        self.athlete.user = user
        self.athlete.save()

        user.delete()

        self.athlete.refresh_from_db()
        self.assertIsNone(self.athlete.user)

    def test_person_rejects_future_birth_date(self):
        person = Person(
            first_name="Futura",
            last_name="Persona",
            birth_date=timezone.localdate() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            person.full_clean()

    def test_person_can_have_multiple_contextual_memberships(self):
        Membership.objects.create(
            person=self.coach,
            organization=self.organization,
            role=Membership.Role.COACH,
        )
        Membership.objects.create(
            person=self.coach,
            organization=self.organization,
            role=Membership.Role.ADMIN,
        )
        other = Organization.objects.create(name="Federació", slug="federacio")
        Membership.objects.create(
            person=self.coach,
            organization=other,
            role=Membership.Role.COACH,
        )

        self.assertEqual(self.coach.memberships.count(), 3)

    def test_membership_rejects_inverted_dates(self):
        membership = Membership(
            person=self.coach,
            organization=self.organization,
            role=Membership.Role.COACH,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_athlete_can_have_multiple_coaches(self):
        second_coach = Person.objects.create(first_name="Laia", last_name="Prat")
        CoachAthleteRelation.objects.create(coach=self.coach, athlete=self.athlete)
        CoachAthleteRelation.objects.create(
            coach=second_coach,
            athlete=self.athlete,
            function=CoachAthleteRelation.Function.ASSISTANT_COACH,
        )

        self.assertEqual(self.athlete.coach_relations.count(), 2)

    def test_relation_rejects_self_coaching_and_incoherent_permissions(self):
        self_relation = CoachAthleteRelation(coach=self.coach, athlete=self.coach)
        with self.assertRaises(ValidationError):
            self_relation.full_clean()

        invalid_permissions = CoachAthleteRelation(
            coach=self.coach,
            athlete=self.athlete,
            can_view_training=False,
            can_edit_training=True,
        )
        with self.assertRaises(ValidationError):
            invalid_permissions.full_clean()

    def test_global_relation_is_unique_for_function(self):
        CoachAthleteRelation.objects.create(coach=self.coach, athlete=self.athlete)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CoachAthleteRelation.objects.create(coach=self.coach, athlete=self.athlete)

