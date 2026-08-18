from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from iatrain.legacy_imports.main_elements import MAIN_ELEMENTS, import_main_elements
from iatrain.models import KnowledgeConcept


class LegacyMainElementsImportTests(TestCase):
    def setUp(self):
        self.author = Person.objects.create(first_name="Curadora", last_name="Tècnica")

    def test_import_creates_all_main_elements_as_attributable_drafts(self):
        summary = import_main_elements(author=self.author)

        self.assertEqual(summary.created, 47)
        self.assertEqual(KnowledgeConcept.objects.count(), len(MAIN_ELEMENTS))
        mortal = KnowledgeConcept.objects.get(name="Mortal enrere agrupat")
        self.assertEqual(mortal.kind, KnowledgeConcept.Kind.SKILL)
        self.assertEqual(mortal.editorial_status, KnowledgeConcept.EditorialStatus.DRAFT)
        self.assertEqual(mortal.authored_by, self.author)
        self.assertEqual(mortal.attributes["aliases"], ["Mortal Atrás Agrupado"])
        self.assertEqual(mortal.attributes["legacy_numeric_notation"], "40.")
        self.assertEqual(mortal.attributes["body_shape"], "tuck")
        self.assertEqual(mortal.attributes["start_position"], "feet")
        self.assertEqual(mortal.attributes["end_position"], "feet")
        self.assertEqual(mortal.attributes["legacy_sources"][0]["legacy_id"], 15)

    def test_import_merges_provenance_without_overwriting_curated_content(self):
        existing = KnowledgeConcept.objects.create(
            name="Agrupat",
            description="Descripció revisada per una entrenadora.",
            kind=KnowledgeConcept.Kind.SKILL,
            discipline="trampoline",
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            authored_by=self.author,
            attributes={"needs_review": False, "custom": "preserve"},
        )

        summary = import_main_elements(author=self.author)

        self.assertEqual(summary.created, 46)
        self.assertEqual(summary.updated, 1)
        existing.refresh_from_db()
        self.assertEqual(existing.description, "Descripció revisada per una entrenadora.")
        self.assertEqual(existing.editorial_status, KnowledgeConcept.EditorialStatus.VALIDATED)
        self.assertFalse(existing.attributes["needs_review"])
        self.assertEqual(existing.attributes["custom"], "preserve")
        self.assertNotIn("aliases", existing.attributes)
        self.assertEqual(existing.attributes["legacy_sources"][0]["original_name"], "Agrupado")

    def test_import_is_idempotent(self):
        import_main_elements(author=self.author)

        summary = import_main_elements(author=self.author)

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.updated, 0)
        self.assertEqual(summary.unchanged, 47)
        self.assertEqual(KnowledgeConcept.objects.count(), 47)

    def test_command_dry_run_rolls_back_every_change(self):
        output = StringIO()

        call_command(
            "import_legacy_main_elements",
            author_person_id=self.author.pk,
            dry_run=True,
            stdout=output,
        )

        self.assertEqual(KnowledgeConcept.objects.count(), 0)
        self.assertIn("Simulació completada: 47 creats", output.getvalue())
