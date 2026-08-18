from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from core.services import merge_people
from iatrain.models import KnowledgeEditorialEvent
from iatrain_motion.checks import audit_skeleton_schema
from iatrain_motion.editorial import transition_motion_relation, transition_skeleton_schema
from iatrain_motion.models import (
    CanonicalLandmark,
    CanonicalSegment,
    EditorialStatus,
    MotionConcept,
    MotionRelation,
    SkeletonSchema,
    SkeletonSide,
)
from iatrain_motion.skeleton_vocabulary import ANGLES, JOINTS, LANDMARKS, SCHEMA, SEGMENTS


class SkeletonModelTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(username="skeleton-author").person
        self.schema = SkeletonSchema.objects.create(
            code="test_skeleton",
            version="1.0.0-draft",
            name="Esquelet de prova",
            description="Contracte mesurable de prova.",
            coordinate_convention={},
            neutral_pose={},
            authored_by=self.author,
        )
        self.left_hip = CanonicalLandmark.objects.create(
            schema=self.schema,
            code="left_hip_center",
            name="Maluc esquerre",
            landmark_type=CanonicalLandmark.LandmarkType.JOINT_CENTER,
            measurement_source=CanonicalLandmark.MeasurementSource.ESTIMATED,
            side=SkeletonSide.LEFT,
            authored_by=self.author,
        )
        self.left_knee = CanonicalLandmark.objects.create(
            schema=self.schema,
            code="left_knee_center",
            name="Genoll esquerre",
            landmark_type=CanonicalLandmark.LandmarkType.JOINT_CENTER,
            measurement_source=CanonicalLandmark.MeasurementSource.ESTIMATED,
            side=SkeletonSide.LEFT,
            authored_by=self.author,
        )
        self.thigh = MotionConcept.objects.create(
            code="thigh",
            name="Cuixa",
            definition="Segment entre maluc i genoll.",
            kind=MotionConcept.Kind.SEGMENT,
            laterality=MotionConcept.Laterality.PAIRED,
            authored_by=self.author,
        )

    def test_paired_semantics_require_a_concrete_side(self):
        segment = CanonicalSegment(
            schema=self.schema,
            code="thigh_without_side",
            concept=self.thigh,
            side=SkeletonSide.MIDLINE,
            axis_start_landmark=self.left_hip,
            axis_end_landmark=self.left_knee,
            authored_by=self.author,
        )
        with self.assertRaises(ValidationError):
            segment.full_clean()

    def test_full_3d_orientation_requires_a_third_landmark(self):
        segment = CanonicalSegment(
            schema=self.schema,
            code="left_thigh",
            concept=self.thigh,
            side=SkeletonSide.LEFT,
            axis_start_landmark=self.left_hip,
            axis_end_landmark=self.left_knee,
            orientation_capability=CanonicalSegment.OrientationCapability.FULL_3D,
            authored_by=self.author,
        )
        with self.assertRaises(ValidationError):
            segment.full_clean()

    def test_validated_schema_locks_its_child_definitions(self):
        segment = CanonicalSegment.objects.create(
            schema=self.schema,
            code="left_thigh",
            concept=self.thigh,
            side=SkeletonSide.LEFT,
            axis_start_landmark=self.left_hip,
            axis_end_landmark=self.left_knee,
            authored_by=self.author,
        )
        SkeletonSchema.objects.filter(pk=self.schema.pk).update(
            editorial_status=EditorialStatus.VALIDATED
        )
        self.schema.refresh_from_db()
        segment.frame_notes = "Canvi silenciós."
        with self.assertRaises(ValidationError):
            segment.save()


class SkeletonSeedAndEditorialTests(TestCase):
    def setUp(self):
        self.reviewer_user = get_user_model().objects.create_superuser(
            username="skeleton-reviewer", password="unused"
        )

    def seed(self):
        call_command(
            "seed_motion_vocabulary",
            author_username=self.reviewer_user.username,
            stdout=StringIO(),
        )
        output = StringIO()
        call_command(
            "seed_canonical_skeleton",
            author_username=self.reviewer_user.username,
            stdout=output,
        )
        return output.getvalue()

    def test_seed_is_complete_coherent_and_idempotent(self):
        first = self.seed()
        schema = SkeletonSchema.objects.get(code=SCHEMA["code"], version=SCHEMA["version"])
        self.assertEqual(schema.landmarks.count(), len(LANDMARKS))
        self.assertEqual(schema.segments.count(), len(SEGMENTS))
        self.assertEqual(schema.joints.count(), len(JOINTS))
        self.assertEqual(schema.angle_definitions.count(), len(ANGLES))
        self.assertEqual(audit_skeleton_schema(schema), [])
        self.assertIn("auditoria correcta", first)

        second = self.seed()
        self.assertIn("schema=0, landmarks=0, segments=0, joints=0, angles=0", second)

    def test_schema_cannot_be_validated_before_its_semantic_graph(self):
        self.seed()
        schema = SkeletonSchema.objects.get(code=SCHEMA["code"], version=SCHEMA["version"])

        with self.assertRaises(ValidationError):
            transition_skeleton_schema(
                user=self.reviewer_user,
                schema=schema,
                target_status=EditorialStatus.VALIDATED,
            )

        MotionConcept.objects.update(editorial_status=EditorialStatus.VALIDATED)
        MotionRelation.objects.update(editorial_status=EditorialStatus.VALIDATED)
        transition_skeleton_schema(
            user=self.reviewer_user,
            schema=schema,
            target_status=EditorialStatus.VALIDATED,
            reason="Topologia i convencions revisades.",
        )

        schema.refresh_from_db()
        self.assertEqual(schema.editorial_status, EditorialStatus.VALIDATED)
        event = KnowledgeEditorialEvent.objects.get(
            target_model="iatrain_motion.skeletonschema",
            target_id=schema.pk,
        )
        self.assertEqual(event.snapshot["landmark_count"], len(LANDMARKS))
        self.assertEqual(event.snapshot["angle_definition_count"], len(ANGLES))

        required_relation = MotionRelation.objects.get(
            source__code="hip_flexion",
            relation_type=MotionRelation.RelationType.ACTION_AT_JOINT,
        )
        with self.assertRaises(ValidationError):
            transition_motion_relation(
                user=self.reviewer_user,
                relation=required_relation,
                target_status=EditorialStatus.DRAFT,
            )

        transition_skeleton_schema(
            user=self.reviewer_user,
            schema=schema,
            target_status=EditorialStatus.DRAFT,
        )
        transition_motion_relation(
            user=self.reviewer_user,
            relation=required_relation,
            target_status=EditorialStatus.DRAFT,
        )


class SkeletonIdentityTests(TestCase):
    def test_person_merge_preserves_schema_and_definition_authorship(self):
        canonical = Person.objects.create(first_name="Autora", last_name="Canònica")
        duplicate = Person.objects.create(first_name="Autora", last_name="Duplicada")
        schema = SkeletonSchema.objects.create(
            code="identity_skeleton",
            version="1.0.0-draft",
            name="Esquelet d'identitat",
            authored_by=duplicate,
            last_validated_by=duplicate,
        )
        landmark = CanonicalLandmark.objects.create(
            schema=schema,
            code="pelvis_center",
            name="Centre de pelvis",
            landmark_type=CanonicalLandmark.LandmarkType.VIRTUAL,
            measurement_source=CanonicalLandmark.MeasurementSource.DERIVED,
            side=SkeletonSide.MIDLINE,
            derivation={"method": "midpoint", "inputs": ["left_hip", "right_hip"]},
            authored_by=duplicate,
        )

        merge_people(canonical=canonical, duplicate=duplicate)

        schema.refresh_from_db()
        landmark.refresh_from_db()
        self.assertEqual(schema.authored_by, canonical)
        self.assertEqual(schema.last_validated_by, canonical)
        self.assertEqual(landmark.authored_by, canonical)
