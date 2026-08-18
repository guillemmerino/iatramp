from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from iatrain.models import KnowledgeEditorialEvent
from iatrain_motion.editorial import transition_motion_concept, transition_motion_relation
from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation


class MotionEditorialTests(TestCase):
    def setUp(self):
        self.reviewer_user = get_user_model().objects.create_superuser(
            username="motion-reviewer", password="unused"
        )
        self.author_user = get_user_model().objects.create_user(
            username="motion-editor", password="unused"
        )
        self.author = self.author_user.person

    def concept(self, code, name, kind, laterality=MotionConcept.Laterality.NOT_APPLICABLE):
        return MotionConcept.objects.create(
            code=code,
            name=name,
            definition=f"Definició professional de {name}.",
            kind=kind,
            laterality=laterality,
            authored_by=self.author,
        )

    def test_only_superusers_can_validate(self):
        plane = self.concept("sagittal_plane", "Pla sagital", MotionConcept.Kind.PLANE)
        with self.assertRaises(PermissionDenied):
            transition_motion_concept(
                user=self.author_user,
                concept=plane,
                target_status=EditorialStatus.VALIDATED,
            )

    def test_validation_is_audited_and_locks_semantics(self):
        plane = self.concept("sagittal_plane", "Pla sagital", MotionConcept.Kind.PLANE)
        transition_motion_concept(
            user=self.reviewer_user,
            concept=plane,
            target_status=EditorialStatus.VALIDATED,
            reason="Terminologia anatòmica revisada.",
        )
        plane.refresh_from_db()
        self.assertEqual(plane.last_validated_by, self.reviewer_user.person)
        event = KnowledgeEditorialEvent.objects.get(
            target_model="iatrain_motion.motionconcept", target_id=plane.pk
        )
        self.assertEqual(event.snapshot["code"], "sagittal_plane")

        plane.definition = "Canvi silenciós."
        with self.assertRaises(ValidationError):
            plane.save()

    def test_relation_needs_validated_typed_endpoints(self):
        action = self.concept("hip_flexion", "Flexió de maluc", MotionConcept.Kind.JOINT_ACTION)
        joint = self.concept(
            "hip_joint",
            "Articulació del maluc",
            MotionConcept.Kind.JOINT,
            MotionConcept.Laterality.PAIRED,
        )
        relation = MotionRelation.objects.create(
            source=action,
            target=joint,
            relation_type=MotionRelation.RelationType.ACTION_AT_JOINT,
            authored_by=self.author,
        )
        with self.assertRaises(ValidationError):
            transition_motion_relation(
                user=self.reviewer_user,
                relation=relation,
                target_status=EditorialStatus.VALIDATED,
            )
        for concept in (action, joint):
            transition_motion_concept(
                user=self.reviewer_user,
                concept=concept,
                target_status=EditorialStatus.VALIDATED,
            )
        transition_motion_relation(
            user=self.reviewer_user,
            relation=relation,
            target_status=EditorialStatus.VALIDATED,
        )
        relation.refresh_from_db()
        self.assertEqual(relation.editorial_status, EditorialStatus.VALIDATED)

        with self.assertRaises(ValidationError):
            transition_motion_concept(
                user=self.reviewer_user,
                concept=action,
                target_status=EditorialStatus.DRAFT,
            )
