from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from iatrain.models import AthleteObservation, KnowledgeConcept, KnowledgeRelation, TrainingContext
from iatrain.services import (
    accessible_athletes,
    can_consult_observations,
    can_record_observations,
    create_knowledge_concept,
    create_knowledge_relation,
    record_athlete_observation,
    revise_athlete_observation,
    set_coach_athlete_relation,
)


class IatrainServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="coach")
        self.coach = self.user.person
        self.coach.first_name = "Joan"
        self.coach.last_name = "Puig"
        self.coach.is_provisional = False
        self.coach.save()
        self.athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        self.other_athlete = Person.objects.create(first_name="Berta", last_name="Prat")
        self.relation = set_coach_athlete_relation(
            coach=self.coach,
            athlete=self.athlete,
            can_view_training=True,
            can_edit_training=False,
        )

    def test_consult_and_record_permissions_use_distinct_relation_capabilities(self):
        self.assertTrue(can_consult_observations(self.user, self.athlete))
        self.assertFalse(can_record_observations(self.user, self.athlete))
        self.assertIn(self.athlete, accessible_athletes(self.user))
        self.assertNotIn(self.other_athlete, accessible_athletes(self.user))

        with self.assertRaises(PermissionDenied):
            record_athlete_observation(
                user=self.user,
                athlete=self.athlete,
                narrative="No s'ha de poder crear.",
            )

    def test_expired_relation_does_not_grant_access(self):
        self.relation.start_date = timezone.localdate() - timedelta(days=3)
        self.relation.end_date = timezone.localdate() - timedelta(days=1)
        self.relation.save()

        self.assertFalse(can_consult_observations(self.user, self.athlete))
        self.assertFalse(accessible_athletes(self.user).exists())

    def test_record_observation_traces_author_and_allows_free_note(self):
        self.relation.can_edit_training = True
        self.relation.save()

        observation = record_athlete_observation(
            user=self.user,
            athlete=self.athlete,
            narrative="Manté l'eix durant tres repeticions.",
            evidence="Vídeo de la sessió i observació directa.",
            confidence="0.800",
        )

        self.assertEqual(observation.authored_by, self.coach)
        self.assertIsNone(observation.concept)
        self.assertEqual(observation.category, AthleteObservation.Category.NOTE)

    def test_context_organization_must_match_authorizing_relation(self):
        from organizations.models import Organization

        club = Organization.objects.create(name="Club", slug="club")
        context = TrainingContext.objects.create(
            name="Club context",
            responsible_coach=self.coach,
            organization=club,
        )
        context.athletes.add(self.athlete)
        self.relation.can_edit_training = True
        self.relation.save()

        with self.assertRaises(PermissionDenied):
            record_athlete_observation(
                user=self.user,
                athlete=self.athlete,
                training_context=context,
                narrative="La relació global no es converteix implícitament en relació de club.",
            )

        self.relation.organization = club
        self.relation.save()
        observation = record_athlete_observation(
            user=self.user,
            athlete=self.athlete,
            training_context=context,
            narrative="Ara hi ha permís contextual explícit.",
        )
        self.assertEqual(observation.training_context, context)

    def test_revision_creates_new_row_and_preserves_original(self):
        self.relation.can_edit_training = True
        self.relation.save()
        original = record_athlete_observation(
            user=self.user,
            athlete=self.athlete,
            narrative="Encara perd l'eix.",
            status=AthleteObservation.Status.OBSERVED,
        )

        revision = revise_athlete_observation(
            user=self.user,
            observation=original,
            narrative="Manté l'eix de manera estable.",
            status=AthleteObservation.Status.STABLE,
            supersedes=None,
        )

        original.refresh_from_db()
        self.assertEqual(original.narrative, "Encara perd l'eix.")
        self.assertEqual(revision.supersedes, original)
        self.assertEqual(revision.status, AthleteObservation.Status.STABLE)
        self.assertEqual(AthleteObservation.objects.count(), 2)

        with self.assertRaises(ValidationError):
            revise_athlete_observation(
                user=self.user,
                observation=original,
                narrative="Una segona branca no és vàlida.",
            )

    def test_concept_and_relation_services_apply_domain_validation(self):
        error = create_knowledge_concept(
            author=self.coach,
            name="Obertura prematura",
            kind=KnowledgeConcept.Kind.ERROR,
        )
        exercise = create_knowledge_concept(
            author=self.coach,
            name="Salt de control d'obertura",
            kind=KnowledgeConcept.Kind.EXERCISE,
        )
        relation = create_knowledge_relation(
            author=self.coach,
            source=exercise,
            target=error,
            relation_type=KnowledgeRelation.RelationType.CORRECTS,
            rationale="L'exercici aïlla el moment d'obertura.",
        )
        self.assertEqual(relation.authored_by, self.coach)

        with self.assertRaises(ValidationError):
            create_knowledge_relation(
                author=self.coach,
                source=error,
                target=error,
                relation_type=KnowledgeRelation.RelationType.CORRECTS,
            )
