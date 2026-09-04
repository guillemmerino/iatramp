from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from core.services import merge_people
from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation
from iatrain_biomechanics.models import (
    MuscleActionFunction,
    MuscleStabilizationFunction,
)

from iatrain_exercises.checks import audit_exercise_catalog
from iatrain_exercises.completeness import refresh_revision_gaps
from iatrain_exercises.editorial import transition_exercise_revision
from iatrain_exercises.models import (
    Exercise,
    ExerciseCatalog,
    ExerciseChangeProposal,
    ExerciseGap,
    ExercisePhaseMuscleRole,
    ExerciseProposalItem,
    ExerciseRevision,
)
from iatrain_exercises.reasoning import build_exercise_context
from iatrain_exercises.knowledge import (
    build_exercise_knowledge_support,
    search_professional_concepts,
)
from iatrain_exercises.vocabulary import EXERCISES


class SeededExerciseTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="exercise-owner",
            password="unused",
        )
        call_command(
            "seed_motion_vocabulary",
            author_username=self.user.username,
            stdout=StringIO(),
        )
        call_command(
            "seed_functional_biomechanics",
            author_username=self.user.username,
            stdout=StringIO(),
        )

    def seed_exercises(self):
        output = StringIO()
        call_command(
            "seed_private_exercise_examples",
            owner_username=self.user.username,
            stdout=output,
        )
        return output.getvalue()


class PrivateExerciseSeedTests(SeededExerciseTestCase):
    def test_sample_is_private_coherent_draft_and_idempotent(self):
        first = self.seed_exercises()
        self.assertIn("catàleg privat coherent", first)
        catalog = ExerciseCatalog.objects.get(owner=self.user.person)
        self.assertEqual(catalog.kind, ExerciseCatalog.Kind.PERSONAL)
        self.assertEqual(
            catalog.exercises.filter(kind=Exercise.Kind.VARIANT).count(),
            len(EXERCISES),
        )
        self.assertFalse(
            ExerciseRevision.objects.exclude(editorial_status=EditorialStatus.DRAFT).exists()
        )
        self.assertFalse(
            ExercisePhaseMuscleRole.objects.filter(
                action_function__isnull=True,
                stabilization_function__isnull=True,
            ).exists()
        )
        self.assertEqual(audit_exercise_catalog(catalog=catalog, include_drafts=True), [])

        second = self.seed_exercises()
        self.assertIn("variants=0", second)
        self.assertIn("revisions=0", second)

    def test_read_projection_is_owner_scoped_and_explainable(self):
        self.seed_exercises()
        context = build_exercise_context(
            owner=self.user.person,
            muscle_codes=("gluteus_maximus",),
            include_drafts=True,
        )
        codes = {row["code"] for row in context["exercises"]}
        self.assertIn("barbell_hip_thrust", codes)
        hip_thrust = next(row for row in context["exercises"] if row["code"] == "barbell_hip_thrust")
        self.assertTrue(hip_thrust["explanation_paths"])
        self.assertTrue(
            any(
                path["biomechanical_basis"] == "gluteus_maximus__hip_extension__general"
                for path in hip_thrust["explanation_paths"]
            )
        )

        outsider = Person.objects.create(first_name="Altra", last_name="Entrenadora")
        self.assertEqual(
            build_exercise_context(owner=outsider, include_drafts=True)["exercises"],
            [],
        )

    def test_professional_projection_supports_concentric_lower_limb_queries(self):
        self.seed_exercises()
        MotionConcept.objects.update(editorial_status=EditorialStatus.VALIDATED)
        MotionRelation.objects.update(editorial_status=EditorialStatus.VALIDATED)
        MuscleActionFunction.objects.update(editorial_status=EditorialStatus.VALIDATED)
        MuscleStabilizationFunction.objects.update(
            editorial_status=EditorialStatus.VALIDATED
        )
        concepts = search_professional_concepts(
            query="extensió maluc gluti",
            kinds=(
                MotionConcept.Kind.JOINT_ACTION,
                MotionConcept.Kind.MUSCLE,
            ),
        )
        concept_codes = {row["concept_code"] for row in concepts["results"]}
        self.assertIn("hip_extension", concept_codes)
        self.assertIn("gluteus_maximus", concept_codes)
        groups = search_professional_concepts(
            query="extensors del genoll",
            kinds=(MotionConcept.Kind.MUSCLE_GROUP,),
        )
        knee_extensors = next(
            row for row in groups["results"] if row["concept_code"] == "knee_extensors"
        )
        self.assertTrue(
            any(
                relation["direction"] == "incoming"
                and relation["source_code"] == "rectus_femoris"
                for relation in knee_extensors["relations"]
            )
        )

        revision = ExerciseRevision.objects.get(exercise__code="barbell_hip_thrust")
        support = build_exercise_knowledge_support(revisions=[revision])
        claims = support["results"][0]["claims"]
        self.assertTrue(
            any(
                row["muscle_code"] == "gluteus_maximus"
                and row["action_code"] == "hip_extension"
                and row["expected_contraction"] == "concentric"
                for row in claims
            )
        )
        self.assertTrue(support["sources"])

    def test_draft_cannot_validate_until_professional_dependencies_are_validated(self):
        self.seed_exercises()
        revision = ExerciseRevision.objects.get(exercise__code="barbell_hip_thrust")
        with self.assertRaises(ValidationError):
            transition_exercise_revision(
                user=self.user,
                revision=revision,
                target_status=EditorialStatus.VALIDATED,
            )


class ExerciseCompletenessAndProposalTests(SeededExerciseTestCase):
    def test_gaps_are_durable_and_llm_proposal_is_staged(self):
        catalog = ExerciseCatalog.objects.create(
            owner=self.user.person,
            code="personal",
            name="Catàleg personal",
        )
        family = Exercise.objects.create(
            catalog=catalog,
            code="hinge",
            name="Frontissa",
            kind=Exercise.Kind.FAMILY,
            created_by=self.user.person,
        )
        variant = Exercise.objects.create(
            catalog=catalog,
            code="new_hinge",
            name="Nova frontissa",
            kind=Exercise.Kind.VARIANT,
            parent=family,
            created_by=self.user.person,
        )
        revision = ExerciseRevision.objects.create(
            exercise=variant,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.HINGE,
            description="Descripció inicial.",
            setup="Preparació inicial.",
            execution="Execució inicial.",
            coaching_cues="Indicacions inicials.",
            requires_equipment=True,
            authored_by=self.user.person,
        )
        gaps = refresh_revision_gaps(revision)
        gap_codes = {gap.requirement_code for gap in gaps}
        self.assertIn("missing_objective", gap_codes)
        self.assertIn("missing_required_equipment", gap_codes)
        self.assertIn("missing_key_phase", gap_codes)

        gap = ExerciseGap.objects.get(revision=revision, requirement_code="missing_objective")
        proposal = ExerciseChangeProposal.objects.create(
            revision=revision,
            origin=ExerciseChangeProposal.Origin.LLM,
            rationale="Proposta per completar l'objectiu que falta.",
            model_name="test-model",
            created_by=self.user.person,
        )
        item = ExerciseProposalItem.objects.create(
            proposal=proposal,
            resolves_gap=gap,
            operation=ExerciseProposalItem.Operation.ADD,
            target_path="revision.objectives",
            proposed_value={"objective": "max_strength", "priority": "primary"},
            confidence="0.800",
            evidence={"graph_path": ["hip_extension", "gluteus_maximus"]},
        )
        self.assertEqual(item.status, ExerciseProposalItem.Status.PENDING)
        revision.refresh_from_db()
        self.assertFalse(revision.objectives.exists())


class ExerciseIdentityTests(SeededExerciseTestCase):
    def test_person_merge_preserves_colliding_private_catalogs(self):
        canonical_user = get_user_model().objects.create_user("canonical-exercise")
        canonical = canonical_user.person
        canonical.first_name = "Canònica"
        canonical.save(update_fields=("first_name", "updated_at"))
        duplicate = Person.objects.create(first_name="Duplicada")
        ExerciseCatalog.objects.create(owner=canonical, code="personal", name="Personal")
        duplicate_catalog = ExerciseCatalog.objects.create(
            owner=duplicate,
            code="personal",
            name="Personal",
        )
        merge_people(canonical=canonical, duplicate=duplicate, merged_by=self.user)
        duplicate_catalog.refresh_from_db()
        self.assertEqual(duplicate_catalog.owner, canonical)
        self.assertNotEqual(duplicate_catalog.code, "personal")
        self.assertEqual(ExerciseCatalog.objects.filter(owner=canonical).count(), 2)
