from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from iatrain.models import AthleteProfile
from iatrain.services import activate_coach_profile
from organizations.models import Membership, MembershipRole, Organization


class SeedSimulatedAthletesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="seed-coach")
        self.user.person.is_provisional = False
        self.user.person.save()
        activate_coach_profile(person=self.user.person)
        self.organization = Organization.objects.create(
            name="Club simulat", slug="club-simulat"
        )
        membership = Membership.objects.create(
            person=self.user.person, organization=self.organization
        )
        MembershipRole.objects.create(
            membership=membership, role=MembershipRole.Role.COACH
        )

    def test_command_creates_complete_profiles_without_duplicates(self):
        arguments = (
            "seed_simulated_athletes",
            "--coach-username",
            self.user.username,
            "--organization-id",
            str(self.organization.pk),
        )
        call_command(*arguments, stdout=StringIO())
        call_command(*arguments, stdout=StringIO())

        people = Person.objects.filter(email__startswith="iatrain.simulat.")
        profiles = AthleteProfile.objects.filter(person__in=people)
        self.assertEqual(people.count(), 10)
        self.assertEqual(profiles.count(), 10)
        for profile in profiles:
            self.assertEqual(profile.sport_profiles.count(), 1)
            self.assertEqual(profile.measurements.count(), 2)
            self.assertEqual(profile.conditions.filter(status="confirmed").count(), 1)
            self.assertEqual(profile.person.training_observations.count(), 1)
