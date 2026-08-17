from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from organizations.models import Membership, MembershipRole, Organization


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
        account_person = user.person

        user.delete()

        account_person.refresh_from_db()
        self.assertIsNone(account_person.user)

    def test_person_rejects_future_birth_date(self):
        person = Person(
            first_name="Futura",
            last_name="Persona",
            birth_date=timezone.localdate() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            person.full_clean()

    def test_person_can_be_registered_without_a_last_name(self):
        person = Person(first_name="Jaume")

        person.full_clean()
        person.save()

        self.assertEqual(person.display_name, "Jaume")

    def test_person_can_have_multiple_contextual_memberships(self):
        membership = Membership.objects.create(
            person=self.coach,
            organization=self.organization,
        )
        MembershipRole.objects.create(
            membership=membership,
            role=MembershipRole.Role.COACH,
        )
        MembershipRole.objects.create(
            membership=membership,
            role=MembershipRole.Role.ADMIN,
        )
        other = Organization.objects.create(name="Federació", slug="federacio")
        other_membership = Membership.objects.create(
            person=self.coach,
            organization=other,
        )
        MembershipRole.objects.create(
            membership=other_membership,
            role=MembershipRole.Role.COACH,
        )

        self.assertEqual(self.coach.memberships.count(), 2)
        self.assertEqual(membership.roles.count(), 2)

    def test_membership_rejects_inverted_dates(self):
        membership = Membership(
            person=self.coach,
            organization=self.organization,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            membership.full_clean()
