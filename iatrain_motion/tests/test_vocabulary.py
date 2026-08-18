from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from iatrain_motion.checks import audit_motion_graph
from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation
from iatrain_motion.vocabulary import CONCEPTS, RELATIONS, SEED_VERSION


class MotionVocabularyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="vocabulary-owner", password="unused"
        )

    def seed(self):
        output = StringIO()
        call_command("seed_motion_vocabulary", author_username=self.user.username, stdout=output)
        return output.getvalue()

    def test_seed_is_complete_coherent_draft_and_idempotent(self):
        first_output = self.seed()
        self.assertIn(SEED_VERSION, first_output)
        self.assertEqual(MotionConcept.objects.count(), len(CONCEPTS))
        self.assertEqual(MotionRelation.objects.count(), len(RELATIONS))
        self.assertFalse(MotionConcept.objects.exclude(editorial_status=EditorialStatus.DRAFT).exists())
        self.assertFalse(MotionRelation.objects.exclude(editorial_status=EditorialStatus.DRAFT).exists())
        self.assertEqual(audit_motion_graph(include_drafts=True), [])

        second_output = self.seed()
        self.assertIn("0 nodes i 0 relacions noves", second_output)
        self.assertEqual(MotionConcept.objects.count(), len(CONCEPTS))
        self.assertEqual(MotionRelation.objects.count(), len(RELATIONS))

    def test_seed_keeps_actions_generic_instead_of_duplicating_sides(self):
        self.seed()
        action = MotionConcept.objects.get(code="hip_flexion")
        joint = MotionConcept.objects.get(code="hip_joint")
        self.assertEqual(action.laterality, MotionConcept.Laterality.NOT_APPLICABLE)
        self.assertEqual(joint.laterality, MotionConcept.Laterality.PAIRED)
        self.assertFalse(MotionConcept.objects.filter(code__startswith="left_").exists())
        self.assertFalse(MotionConcept.objects.filter(code__startswith="right_").exists())
