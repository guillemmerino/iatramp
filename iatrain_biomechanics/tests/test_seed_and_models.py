from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation

from iatrain_biomechanics.checks import audit_biomechanics
from iatrain_biomechanics.models import (
    BiomechanicalContext,
    MuscleActionFunction,
    MuscleStabilizationFunction,
)
from iatrain_biomechanics.vocabulary import (
    CONTEXTS,
    FUNCTIONS_BY_MUSCLE,
    GROUPS,
    MUSCLES,
    STABILIZATIONS,
)


class FunctionalBiomechanicsSeedTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="biomechanics-owner",
            password="unused",
        )

    def seed(self):
        call_command(
            "seed_motion_vocabulary",
            author_username=self.user.username,
            stdout=StringIO(),
        )
        output = StringIO()
        call_command(
            "seed_functional_biomechanics",
            author_username=self.user.username,
            stdout=output,
        )
        return output.getvalue()

    def test_seed_is_complete_coherent_draft_and_idempotent(self):
        first = self.seed()
        self.assertIn("auditoria correcta", first)
        self.assertEqual(
            MotionConcept.objects.filter(kind=MotionConcept.Kind.MUSCLE).count(),
            len(MUSCLES),
        )
        self.assertEqual(
            MotionConcept.objects.filter(kind=MotionConcept.Kind.MUSCLE_GROUP).count(),
            len(GROUPS),
        )
        self.assertEqual(BiomechanicalContext.objects.count(), len(CONTEXTS))
        self.assertEqual(
            MuscleActionFunction.objects.count(),
            sum(len(functions) for functions in FUNCTIONS_BY_MUSCLE.values()),
        )
        self.assertEqual(MuscleStabilizationFunction.objects.count(), len(STABILIZATIONS))
        self.assertFalse(
            MuscleActionFunction.objects.exclude(editorial_status=EditorialStatus.DRAFT).exists()
        )
        self.assertFalse(
            MuscleStabilizationFunction.objects.exclude(
                editorial_status=EditorialStatus.DRAFT
            ).exists()
        )
        self.assertFalse(
            MuscleActionFunction.objects.filter(evidence_links__isnull=True).exists()
        )
        self.assertFalse(
            MuscleStabilizationFunction.objects.filter(evidence_links__isnull=True).exists()
        )
        self.assertEqual(audit_biomechanics(include_drafts=True), [])

        second = self.seed()
        self.assertIn("concepts=0", second)
        self.assertIn("action_functions=0", second)
        self.assertIn("auditoria correcta", second)

    def test_every_muscle_has_group_joint_and_function_or_stabilization(self):
        self.seed()
        for muscle in MotionConcept.objects.filter(kind=MotionConcept.Kind.MUSCLE):
            self.assertTrue(
                muscle.outgoing_motion_relations.filter(
                    relation_type=MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP
                ).exists(),
                muscle.code,
            )
            self.assertTrue(
                muscle.outgoing_motion_relations.filter(
                    relation_type=MotionRelation.RelationType.SPANS_JOINT
                ).exists(),
                muscle.code,
            )
            self.assertTrue(
                muscle.biomechanical_action_functions.exists()
                or muscle.biomechanical_stabilization_functions.exists(),
                muscle.code,
            )

    def test_function_requires_muscle_and_action_endpoint_types(self):
        self.seed()
        action = MotionConcept.objects.get(code="hip_extension")
        segment = MotionConcept.objects.get(code="thigh")
        context = BiomechanicalContext.objects.get(code="general_functional_context")
        invalid = MuscleActionFunction(
            code="invalid_segment_function",
            muscle=segment,
            action=action,
            context=context,
            statement="Invàlida.",
            authored_by=self.user.person,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_stabilization_requires_exactly_one_typed_target(self):
        self.seed()
        muscle = MotionConcept.objects.get(code="gluteus_medius")
        hip = MotionConcept.objects.get(code="hip_joint")
        pelvis = MotionConcept.objects.get(code="pelvis")
        invalid = MuscleStabilizationFunction(
            code="invalid_double_target",
            muscle=muscle,
            target_joint=hip,
            target_segment=pelvis,
            stabilization_type=MuscleStabilizationFunction.StabilizationType.JOINT_CENTERING,
            statement="Invàlida.",
            authored_by=self.user.person,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
