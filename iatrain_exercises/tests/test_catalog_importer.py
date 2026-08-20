from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from iatrain_exercises.catalog_data.v2 import BATCHES, CATALOG_VERSION, PROFESSIONAL_GAPS
from iatrain_exercises.catalog_importer import (
    PrivateCatalogImporter,
    build_coverage_matrix,
    validate_catalog_data,
)
from iatrain_exercises.checks import audit_exercise_catalog
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseGap, ExerciseRevision


class CatalogDataTests(SimpleTestCase):
    def test_versioned_batches_are_large_balanced_and_reference_safe(self):
        validation = validate_catalog_data()
        coverage = build_coverage_matrix()
        self.assertEqual(validation["variants"], 292)
        self.assertEqual(len(BATCHES), 10)
        self.assertTrue(all(25 <= len(batch["variants"]) <= 50 for batch in BATCHES))
        self.assertGreaterEqual(coverage["families"], 90)
        self.assertTrue({"squat", "hinge", "horizontal_push", "vertical_push", "horizontal_pull", "vertical_pull", "ankle_dominant", "trunk_control"}.issubset(coverage["patterns"]))
        self.assertTrue({"strength", "power", "muscular_endurance", "motor_control", "mobility", "warm_up"}.issubset(coverage["modalities"]))
        self.assertTrue({"beginner", "intermediate", "advanced"}.issubset(coverage["difficulties"]))
        self.assertTrue(PROFESSIONAL_GAPS)


class CatalogImporterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("catalog-owner", password="unused")
        call_command("seed_motion_vocabulary", author_username=self.user.username, stdout=StringIO())
        call_command("seed_functional_biomechanics", author_username=self.user.username, stdout=StringIO())

    def test_batch_is_private_draft_audited_idempotent_and_protects_edits(self):
        first = PrivateCatalogImporter(owner=self.user.person, batch_codes=("04_lower_accessory",)).run()
        catalog = ExerciseCatalog.objects.get(owner=self.user.person)
        self.assertEqual(first.created["variants"], 28)
        self.assertEqual(catalog.exercises.filter(kind=Exercise.Kind.VARIANT).count(), 28)
        self.assertFalse(ExerciseRevision.objects.exclude(editorial_status="draft").exists())
        self.assertEqual(audit_exercise_catalog(catalog=catalog, include_drafts=True), [])
        self.assertFalse(ExerciseGap.objects.filter(status__in=("open", "proposed")).exists())

        revision = ExerciseRevision.objects.get(exercise__code="seated_leg_extension")
        self.assertEqual(revision.provenance["import_version"], CATALOG_VERSION)
        self.assertTrue(revision.provenance["sources"])

        second = PrivateCatalogImporter(owner=self.user.person, batch_codes=("04_lower_accessory",)).run()
        self.assertEqual(second.skipped["unchanged_variants"], 28)
        self.assertFalse(second.conflicts)

        revision.coaching_cues = revision.coaching_cues + " Edició manual de l'entrenador."
        revision.save(update_fields=("coaching_cues", "updated_at"))
        third = PrivateCatalogImporter(owner=self.user.person, batch_codes=("04_lower_accessory",)).run()
        self.assertTrue(any(row["variant"] == "seated_leg_extension" for row in third.conflicts))
        revision.refresh_from_db()
        self.assertIn("Edició manual", revision.coaching_cues)

