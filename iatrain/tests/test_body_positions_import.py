from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from iatrain.legacy_imports.body_positions import (
    BODY_POSITIONS,
    DEFINING_POSITION_LEGACY_IDS,
    import_body_positions,
)
from iatrain.legacy_imports.main_elements import import_main_elements
from iatrain.models import KnowledgeConcept, KnowledgeRelation


class BodyPositionImportTests(TestCase):
    def setUp(self):
        self.author = Person.objects.create(first_name="Curadora", last_name="Tècnica")
        import_main_elements(author=self.author)

    def test_import_creates_positions_and_only_explicit_defining_relations(self):
        summary = import_body_positions(author=self.author)

        expected_relations = sum(len(ids) for ids in DEFINING_POSITION_LEGACY_IDS.values())
        self.assertEqual(summary.positions_created, 3)
        self.assertEqual(summary.relations_created, expected_relations)
        self.assertEqual(
            KnowledgeConcept.objects.filter(kind=KnowledgeConcept.Kind.BODY_POSITION).count(),
            len(BODY_POSITIONS),
        )
        self.assertEqual(
            KnowledgeRelation.objects.filter(
                relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION
            ).count(),
            expected_relations,
        )

        tucked = KnowledgeConcept.objects.get(name="Posició agrupada")
        barani = KnowledgeConcept.objects.get(name="Barani agrupat")
        relation = KnowledgeRelation.objects.get(
            source=barani,
            relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
        )
        self.assertEqual(relation.target, tucked)
        self.assertEqual(relation.editorial_status, KnowledgeRelation.EditorialStatus.DRAFT)
        self.assertEqual(relation.authored_by, self.author)
        self.assertIn("Barany Agrupado", relation.rationale)

    def test_body_shape_alone_does_not_create_a_defining_relation(self):
        import_body_positions(author=self.author)

        for element_name in ("Bot", "Cody", "Rudy"):
            element = KnowledgeConcept.objects.get(name=element_name)
            self.assertIn("body_shape", element.attributes)
            self.assertFalse(
                KnowledgeRelation.objects.filter(
                    source=element,
                    relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
                ).exists()
            )

    def test_position_concepts_remain_distinct_from_elements_with_similar_names(self):
        import_body_positions(author=self.author)

        element = KnowledgeConcept.objects.get(
            name="Agrupat",
            kind=KnowledgeConcept.Kind.SKILL,
        )
        position = KnowledgeConcept.objects.get(
            name="Posició agrupada",
            kind=KnowledgeConcept.Kind.BODY_POSITION,
        )

        self.assertNotEqual(element.pk, position.pk)
        self.assertEqual(position.attributes["body_shape_code"], "tuck")
        self.assertIn("Agrupat", position.attributes["aliases"])

    def test_import_is_idempotent(self):
        first = import_body_positions(author=self.author)

        second = import_body_positions(author=self.author)

        self.assertEqual(first.positions_created, 3)
        self.assertEqual(second.positions_created, 0)
        self.assertEqual(second.positions_existing, 3)
        self.assertEqual(second.relations_created, 0)
        self.assertEqual(second.relations_existing, first.relations_created)

    def test_existing_relation_to_another_position_is_not_overwritten(self):
        alternate = KnowledgeConcept.objects.create(
            name="Posició alternativa pendent",
            kind=KnowledgeConcept.Kind.BODY_POSITION,
            authored_by=self.author,
        )
        barani = KnowledgeConcept.objects.get(name="Barani agrupat")
        existing = KnowledgeRelation.objects.create(
            source=barani,
            target=alternate,
            relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
            editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            authored_by=self.author,
        )

        summary = import_body_positions(author=self.author)

        self.assertEqual(summary.relations_skipped_conflict, 1)
        existing.refresh_from_db()
        self.assertEqual(existing.target, alternate)
        self.assertEqual(existing.editorial_status, KnowledgeRelation.EditorialStatus.VALIDATED)
        self.assertEqual(
            KnowledgeRelation.objects.filter(
                source=barani,
                relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION,
            ).count(),
            1,
        )

    def test_command_dry_run_rolls_back_positions_and_relations(self):
        output = StringIO()

        call_command(
            "import_body_positions",
            author_person_id=self.author.pk,
            dry_run=True,
            stdout=output,
        )

        self.assertFalse(
            KnowledgeConcept.objects.filter(kind=KnowledgeConcept.Kind.BODY_POSITION).exists()
        )
        self.assertFalse(
            KnowledgeRelation.objects.filter(
                relation_type=KnowledgeRelation.RelationType.HAS_DEFINING_POSITION
            ).exists()
        )
        self.assertIn("Simulació completada: 3 posicions creades", output.getvalue())

