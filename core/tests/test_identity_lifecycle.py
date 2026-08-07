from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Organization, Person, PersonClaimInvitation, PersonMergeRecord
from core.services import accept_person_claim_invitation
from iatrain.models import (
    AthleteProfile,
    CoachAthleteRelation,
    TrainingGroup,
    TrainingGroupMembership,
)
from iatrain.services import create_unclaimed_athlete


class IdentityLifecycleTests(TestCase):
    def complete_person(self, user, first_name, last_name):
        person = user.person
        person.first_name = first_name
        person.last_name = last_name
        person.is_provisional = False
        person.save()
        return person

    def test_new_user_gets_a_provisional_person_automatically(self):
        user = get_user_model().objects.create_user(
            username="new-athlete",
            email="new@example.com",
        )

        self.assertEqual(user.person.user, user)
        self.assertTrue(user.person.is_provisional)
        self.assertEqual(user.person.email, "new@example.com")

    def test_coach_can_create_an_unclaimed_athlete_with_profile_and_relation(self):
        coach_user = get_user_model().objects.create_user(username="coach-create")
        coach = self.complete_person(coach_user, "Joan", "Puig")

        athlete_profile, relation, invitation, raw_token = create_unclaimed_athlete(
            coach=coach,
            first_name="Aina",
            last_name="Serra",
            email="aina@example.com",
        )

        self.assertIsNone(athlete_profile.person.user)
        self.assertEqual(relation.athlete_profile, athlete_profile)
        self.assertEqual(relation.coach_profile.person, coach)
        self.assertEqual(invitation.person, athlete_profile.person)
        self.assertTrue(raw_token)

    def test_claim_replaces_auto_identity_and_preserves_training_relation(self):
        coach_user = get_user_model().objects.create_user(username="coach-claim")
        coach = self.complete_person(coach_user, "Joan", "Puig")
        athlete_profile, relation, invitation, raw_token = create_unclaimed_athlete(
            coach=coach,
            first_name="Aina",
            last_name="Serra",
            email="aina@example.com",
        )
        claimed_person_id = athlete_profile.person_id
        athlete_user = get_user_model().objects.create_user(
            username="aina-claim",
            email="aina@example.com",
        )
        provisional_id = athlete_user.person.pk

        canonical = accept_person_claim_invitation(user=athlete_user, token=raw_token)

        athlete_user.refresh_from_db()
        relation.refresh_from_db()
        invitation.refresh_from_db()
        self.assertEqual(canonical.pk, claimed_person_id)
        self.assertEqual(athlete_user.person.pk, claimed_person_id)
        self.assertEqual(relation.athlete_profile.person_id, claimed_person_id)
        self.assertFalse(Person.objects.filter(pk=provisional_id).exists())
        self.assertTrue(
            PersonMergeRecord.objects.filter(
                canonical_person=canonical,
                duplicate_person_id=provisional_id,
            ).exists()
        )
        self.assertEqual(invitation.status, PersonClaimInvitation.Status.CLAIMED)

    def test_same_user_can_claim_and_merge_profiles_created_by_two_coaches(self):
        first_coach_user = get_user_model().objects.create_user(username="coach-one")
        first_coach = self.complete_person(first_coach_user, "Joan", "Primer")
        second_coach_user = get_user_model().objects.create_user(username="coach-two")
        second_coach = self.complete_person(second_coach_user, "Laia", "Segona")
        first_profile, _, _, first_token = create_unclaimed_athlete(
            coach=first_coach,
            first_name="Aina",
            last_name="Serra",
            email="aina@example.com",
        )
        second_profile, _, _, second_token = create_unclaimed_athlete(
            coach=second_coach,
            first_name="Aina",
            last_name="Serra",
            email="aina@example.com",
        )
        organization = Organization.objects.create(
            name="CEO La Marbella",
            slug="ceo-la-marbella",
        )
        group = TrainingGroup.objects.create(
            organization=organization,
            name="Adults",
        )
        TrainingGroupMembership.objects.create(
            training_group=group,
            athlete_profile=first_profile,
            notes="Primera fitxa",
        )
        TrainingGroupMembership.objects.create(
            training_group=group,
            athlete_profile=second_profile,
            notes="Segona fitxa",
        )
        user = get_user_model().objects.create_user(
            username="aina-two-coaches",
            email="aina@example.com",
        )

        first_canonical = accept_person_claim_invitation(user=user, token=first_token)
        final_canonical = accept_person_claim_invitation(user=user, token=second_token)

        self.assertEqual(final_canonical.pk, first_canonical.pk)
        self.assertFalse(Person.objects.filter(pk=second_profile.person_id).exists())
        self.assertEqual(AthleteProfile.objects.filter(person=final_canonical).count(), 1)
        self.assertEqual(
            CoachAthleteRelation.objects.filter(
                athlete_profile__person=final_canonical
            ).count(),
            2,
        )
        self.assertEqual(
            TrainingGroupMembership.objects.filter(
                training_group=group,
                athlete_profile__person=final_canonical,
                is_active=True,
            ).count(),
            1,
        )

    def test_claim_requires_the_invited_email(self):
        coach_user = get_user_model().objects.create_user(username="coach-email")
        coach = self.complete_person(coach_user, "Joan", "Puig")
        _, _, _, raw_token = create_unclaimed_athlete(
            coach=coach,
            first_name="Aina",
            last_name="Serra",
            email="aina@example.com",
        )
        wrong_user = get_user_model().objects.create_user(
            username="wrong-email",
            email="other@example.com",
        )

        with self.assertRaises(ValidationError):
            accept_person_claim_invitation(user=wrong_user, token=raw_token)
