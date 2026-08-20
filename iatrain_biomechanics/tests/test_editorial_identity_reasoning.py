from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from core.services import merge_people
from iatrain.models import KnowledgeEditorialEvent
from iatrain_motion.editorial import transition_motion_concept
from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation

from iatrain_biomechanics.editorial import (
    transition_biomechanical_context,
    transition_muscle_action_function,
)
from iatrain_biomechanics.models import EvidenceReference, MuscleActionFunction
from iatrain_biomechanics.reasoning import (
    build_biomechanics_context,
    infer_contraction_mode,
)


class SeededBiomechanicsTestCase(TestCase):
    def setUp(self):
        self.reviewer = get_user_model().objects.create_superuser(
            username="biomechanics-reviewer",
            password="unused",
        )
        call_command(
            "seed_motion_vocabulary",
            author_username=self.reviewer.username,
            stdout=StringIO(),
        )
        call_command(
            "seed_functional_biomechanics",
            author_username=self.reviewer.username,
            stdout=StringIO(),
        )


class BiomechanicalEditorialTests(SeededBiomechanicsTestCase):
    def test_validation_needs_validated_dependencies_and_records_snapshot(self):
        function = MuscleActionFunction.objects.get(
            muscle__code="gluteus_maximus",
            action__code="hip_extension",
        )
        with self.assertRaises(ValidationError):
            transition_muscle_action_function(
                user=self.reviewer,
                function=function,
                target_status=EditorialStatus.VALIDATED,
            )

        MotionConcept.objects.update(editorial_status=EditorialStatus.VALIDATED)
        MotionRelation.objects.update(editorial_status=EditorialStatus.VALIDATED)
        transition_biomechanical_context(
            user=self.reviewer,
            context=function.context,
            target_status=EditorialStatus.VALIDATED,
        )
        transition_muscle_action_function(
            user=self.reviewer,
            function=function,
            target_status=EditorialStatus.VALIDATED,
            reason="Funció i evidència revisades.",
        )
        function.refresh_from_db()
        self.assertEqual(function.editorial_status, EditorialStatus.VALIDATED)
        event = KnowledgeEditorialEvent.objects.get(
            target_model="iatrain_biomechanics.muscleactionfunction",
            target_id=function.pk,
        )
        self.assertEqual(event.snapshot["muscle_id"], function.muscle_id)
        self.assertTrue(event.snapshot["evidence_ids"])

        function.statement = "Canvi silenciós."
        with self.assertRaises(ValidationError):
            function.save()

    def test_validated_function_blocks_upstream_concept_reopening(self):
        function = MuscleActionFunction.objects.get(
            muscle__code="gluteus_maximus",
            action__code="hip_extension",
        )
        MotionConcept.objects.update(editorial_status=EditorialStatus.VALIDATED)
        MotionRelation.objects.update(editorial_status=EditorialStatus.VALIDATED)
        function.context.__class__.objects.filter(pk=function.context_id).update(
            editorial_status=EditorialStatus.VALIDATED
        )
        transition_muscle_action_function(
            user=self.reviewer,
            function=function,
            target_status=EditorialStatus.VALIDATED,
        )
        with self.assertRaises(ValidationError):
            transition_motion_concept(
                user=self.reviewer,
                concept=function.muscle,
                target_status=EditorialStatus.DRAFT,
            )


class BiomechanicalIdentityTests(SeededBiomechanicsTestCase):
    def test_person_merge_preserves_biomechanical_authorship(self):
        canonical = Person.objects.create(first_name="Autora", last_name="Canònica")
        duplicate = Person.objects.create(first_name="Autora", last_name="Duplicada")
        function = MuscleActionFunction.objects.first()
        source = EvidenceReference.objects.first()
        MuscleActionFunction.objects.filter(pk=function.pk).update(authored_by=duplicate)
        EvidenceReference.objects.filter(pk=source.pk).update(authored_by=duplicate)

        merge_people(canonical=canonical, duplicate=duplicate)

        function.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(function.authored_by, canonical)
        self.assertEqual(source.authored_by, canonical)


class BiomechanicalReasoningTests(SeededBiomechanicsTestCase):
    def setUp(self):
        super().setUp()
        self.function = MuscleActionFunction.objects.get(
            muscle__code="gluteus_maximus",
            action__code="hip_extension",
        )
        self.extension = MotionConcept.objects.get(code="hip_extension")
        self.flexion = MotionConcept.objects.get(code="hip_flexion")

    def test_infers_intended_concentric_eccentric_and_isometric_modes(self):
        concentric = infer_contraction_mode(
            function=self.function,
            phase_action=self.extension,
            intent="produce",
            muscle_is_targeted=True,
            include_drafts=True,
        )
        eccentric = infer_contraction_mode(
            function=self.function,
            phase_action=self.flexion,
            intent="control",
            muscle_is_targeted=True,
            include_drafts=True,
        )
        isometric = infer_contraction_mode(
            function=self.function,
            phase_action=self.extension,
            intent="hold",
            muscle_is_targeted=True,
            include_drafts=True,
        )
        self.assertEqual(concentric.mode, "concentric")
        self.assertEqual(eccentric.mode, "eccentric")
        self.assertEqual(isometric.mode, "isometric")
        self.assertIn("no confirma", concentric.limitations[0])

    def test_no_target_activation_returns_indeterminate(self):
        result = infer_contraction_mode(
            function=self.function,
            phase_action=self.extension,
            intent="produce",
            muscle_is_targeted=False,
            include_drafts=True,
        )
        self.assertEqual(result.mode, "indeterminate")

    def test_context_builder_hides_drafts_by_default(self):
        self.assertEqual(build_biomechanics_context()["muscle_action_functions"], [])
        draft_context = build_biomechanics_context(
            action_codes=("hip_extension",),
            include_drafts=True,
        )
        self.assertTrue(draft_context["muscle_action_functions"])
        self.assertFalse(draft_context["interpretation_policy"]["activation_is_observed"])
