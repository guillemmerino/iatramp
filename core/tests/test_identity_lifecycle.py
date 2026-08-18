from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Person, PersonClaimInvitation, PersonMergeRecord
from core.identity_merge import registered_person_merge_handlers
from core.services import accept_person_claim_invitation, merge_people
from iatrain.models import (
    AthleteProfile,
    CoachAthleteRelation,
    CoachProfile,
    ElementNotation,
    ElementRotation,
    ElementRotationSegment,
    Gym,
    KnowledgeConcept,
    KnowledgeEditorialEvent,
    TrainingGroup,
    TrainingGroupMembership,
)
from iatrain.services import create_unclaimed_athlete
from iatrain_motion.models import MotionConcept
from organizations.models import Organization


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

    def test_domain_merge_handlers_are_registered_by_their_own_apps(self):
        registered = registered_person_merge_handlers()
        self.assertIn("organizations", registered)
        self.assertIn("iatrain", registered)
        self.assertIn("iatrain_motion", registered)

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

    def test_merge_preserves_knowledge_authorship_and_coach_owned_data(self):
        canonical = Person.objects.create(first_name="Joan", last_name="Canònic")
        duplicate = Person.objects.create(first_name="Joan", last_name="Duplicat")
        canonical_coach = CoachProfile.objects.create(person=canonical)
        duplicate_coach = CoachProfile.objects.create(person=duplicate)
        organization = Organization.objects.create(name="Club Fusió", slug="club-fusio")
        group = TrainingGroup.objects.create(organization=organization, name="Tecnificació")
        group.managing_coaches.add(duplicate_coach)
        gym = Gym.objects.create(name="Sala principal", created_by=duplicate_coach)
        element = KnowledgeConcept.objects.create(
            name="Element de fusió",
            kind=KnowledgeConcept.Kind.SKILL,
            authored_by=duplicate,
            last_validated_by=duplicate,
            last_validated_at=timezone.now(),
        )
        rotation = ElementRotation.objects.create(
            element=element,
            transverse_quarters=4,
            transverse_direction=ElementRotation.Direction.FORWARD,
            authored_by=duplicate,
            last_validated_by=duplicate,
            last_validated_at=timezone.now(),
        )
        ElementRotationSegment.objects.create(
            rotation=rotation,
            sequence_index=1,
            longitudinal_half_turns=0,
        )
        notation = ElementNotation.objects.create(
            element=element,
            rotation=rotation,
            raw_notation=".40o",
            normalized_notation=".40o",
            direction_source=ElementNotation.ResolutionSource.EXPLICIT,
            position_source=ElementNotation.ResolutionSource.EXPLICIT,
            position_symbol="o",
            authored_by=duplicate,
        )
        editorial_event = KnowledgeEditorialEvent.objects.create(
            target_model="iatrain.knowledgeconcept",
            target_id=element.pk,
            target_repr=str(element),
            from_status="draft",
            to_status="validated",
            decided_by=duplicate,
            snapshot={"name": element.name},
        )
        motion_concept = MotionConcept.objects.create(
            code="merge_test_plane",
            name="Pla de prova de fusió",
            definition="Concepte anatòmic utilitzat per comprovar la fusió d'identitats.",
            kind=MotionConcept.Kind.PLANE,
            authored_by=duplicate,
            last_validated_by=duplicate,
            last_validated_at=timezone.now(),
        )

        merged = merge_people(canonical=canonical, duplicate=duplicate)

        element.refresh_from_db()
        rotation.refresh_from_db()
        notation.refresh_from_db()
        editorial_event.refresh_from_db()
        motion_concept.refresh_from_db()
        gym.refresh_from_db()
        self.assertEqual(merged, canonical)
        self.assertFalse(Person.objects.filter(pk=duplicate.pk).exists())
        self.assertEqual(element.authored_by, canonical)
        self.assertEqual(element.last_validated_by, canonical)
        self.assertEqual(rotation.authored_by, canonical)
        self.assertEqual(rotation.last_validated_by, canonical)
        self.assertEqual(notation.authored_by, canonical)
        self.assertEqual(editorial_event.decided_by, canonical)
        self.assertEqual(motion_concept.authored_by, canonical)
        self.assertEqual(motion_concept.last_validated_by, canonical)
        self.assertEqual(gym.created_by, canonical_coach)
        self.assertEqual(list(group.managing_coaches.all()), [canonical_coach])
