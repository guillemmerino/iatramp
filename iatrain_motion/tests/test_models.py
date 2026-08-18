from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation


class MotionModelTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(username="motion-author").person

    def concept(self, code, name, kind, laterality=MotionConcept.Laterality.NOT_APPLICABLE):
        return MotionConcept.objects.create(
            code=code,
            name=name,
            definition=f"Definició de {name}.",
            kind=kind,
            laterality=laterality,
            authored_by=self.author,
        )

    def test_codes_and_labels_are_normalized_and_stable(self):
        concept = self.concept(
            "  HIP-JOINT ",
            "  Articulació   del maluc ",
            MotionConcept.Kind.JOINT,
            MotionConcept.Laterality.PAIRED,
        )
        self.assertEqual(concept.code, "hip_joint")
        self.assertEqual(concept.name, "Articulació del maluc")

    def test_laterality_only_applies_to_anatomical_structures(self):
        with self.assertRaises(ValidationError):
            self.concept(
                "hip_flexion",
                "Flexió de maluc",
                MotionConcept.Kind.JOINT_ACTION,
                MotionConcept.Laterality.PAIRED,
            )
        with self.assertRaises(ValidationError):
            self.concept(
                "hip_joint",
                "Articulació del maluc",
                MotionConcept.Kind.JOINT,
            )

    def test_relation_domains_are_enforced(self):
        segment = self.concept(
            "thigh", "Cuixa", MotionConcept.Kind.SEGMENT, MotionConcept.Laterality.PAIRED
        )
        plane = self.concept("sagittal_plane", "Pla sagital", MotionConcept.Kind.PLANE)
        relation = MotionRelation(
            source=segment,
            target=plane,
            relation_type=MotionRelation.RelationType.ACTION_AT_JOINT,
            authored_by=self.author,
        )
        with self.assertRaises(ValidationError):
            relation.full_clean()

    def test_new_records_cannot_start_validated(self):
        with self.assertRaises(ValidationError):
            MotionConcept.objects.create(
                code="knee_joint",
                name="Articulació del genoll",
                definition="Complex articular del genoll.",
                kind=MotionConcept.Kind.JOINT,
                laterality=MotionConcept.Laterality.PAIRED,
                editorial_status=EditorialStatus.VALIDATED,
                authored_by=self.author,
            )

    def test_professional_nodes_cannot_be_deleted_directly(self):
        plane = self.concept("sagittal_plane", "Pla sagital", MotionConcept.Kind.PLANE)
        with self.assertRaises(ValidationError):
            plane.delete()
