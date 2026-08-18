from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from iatrain.legacy_imports.contact_positions import (
    CONTACT_POSITION_DEFINITIONS,
    import_contact_positions,
)
from iatrain.legacy_imports.main_elements import MAIN_ELEMENTS, import_main_elements
from iatrain.models import KnowledgeConcept, KnowledgeRelation


class ContactPositionImportTests(TestCase):
    def setUp(self):
        self.author = Person.objects.create(first_name="Curadora", last_name="Tècnica")
        import_main_elements(author=self.author)

    def relation_target(self, element_name, relation_type):
        return KnowledgeRelation.objects.get(
            source__name=element_name,
            relation_type=relation_type,
        ).target.name

    def test_import_creates_five_contacts_and_start_end_relations(self):
        summary = import_contact_positions(author=self.author)

        self.assertEqual(summary.positions_created, 5)
        self.assertEqual(summary.start_relations_created, len(MAIN_ELEMENTS))
        self.assertEqual(summary.end_relations_created, len(MAIN_ELEMENTS))
        self.assertEqual(summary.unsupported_legacy_contacts, 0)
        self.assertEqual(
            KnowledgeConcept.objects.filter(kind=KnowledgeConcept.Kind.CONTACT_POSITION).count(),
            len(CONTACT_POSITION_DEFINITIONS),
        )
        self.assertEqual(
            KnowledgeRelation.objects.filter(
                relation_type__in=(
                    KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
                    KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
                )
            ).count(),
            len(MAIN_ELEMENTS) * 2,
        )

    def test_representative_elements_receive_correct_directed_contacts(self):
        import_contact_positions(author=self.author)

        self.assertEqual(
            self.relation_target(
                "Caiguda assegut",
                KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
            ),
            "Contacte dempeus",
        )
        self.assertEqual(
            self.relation_target(
                "Caiguda assegut",
                KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
            ),
            "Contacte assegut",
        )
        self.assertEqual(
            self.relation_target(
                "Tres quarts endavant",
                KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
            ),
            "Contacte d'esquena",
        )
        self.assertEqual(
            self.relation_target(
                "Barani ball out agrupat",
                KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
            ),
            "Contacte d'esquena",
        )
        self.assertEqual(
            self.relation_target(
                "Barani ball out agrupat",
                KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
            ),
            "Contacte dempeus",
        )

    def test_all_fours_is_a_valid_draft_concept_without_invented_relations(self):
        import_contact_positions(author=self.author)

        all_fours = KnowledgeConcept.objects.get(name="Contacte de quatre potes")

        self.assertEqual(all_fours.kind, KnowledgeConcept.Kind.CONTACT_POSITION)
        self.assertEqual(all_fours.editorial_status, KnowledgeConcept.EditorialStatus.DRAFT)
        self.assertEqual(all_fours.attributes["contact_code"], "all_fours")
        self.assertIn("progressions", all_fours.description)
        self.assertFalse(all_fours.incoming_relations.exists())

    def test_import_is_idempotent(self):
        first = import_contact_positions(author=self.author)

        second = import_contact_positions(author=self.author)

        self.assertEqual(first.positions_created, 5)
        self.assertEqual(second.positions_created, 0)
        self.assertEqual(second.positions_existing, 5)
        self.assertEqual(second.start_relations_created, 0)
        self.assertEqual(second.start_relations_existing, len(MAIN_ELEMENTS))
        self.assertEqual(second.end_relations_created, 0)
        self.assertEqual(second.end_relations_existing, len(MAIN_ELEMENTS))

    def test_existing_conflicting_relation_is_not_overwritten(self):
        alternate = KnowledgeConcept.objects.create(
            name="Contacte inicial alternatiu",
            kind=KnowledgeConcept.Kind.CONTACT_POSITION,
            authored_by=self.author,
        )
        element = KnowledgeConcept.objects.get(name="Caiguda assegut")
        KnowledgeConcept.objects.filter(pk__in=(alternate.pk, element.pk)).update(
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED
        )
        existing = KnowledgeRelation.objects.create(
            source=element,
            target=alternate,
            relation_type=KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
            editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            authored_by=self.author,
        )

        summary = import_contact_positions(author=self.author)

        self.assertEqual(summary.relations_skipped_conflict, 1)
        existing.refresh_from_db()
        self.assertEqual(existing.target, alternate)
        self.assertEqual(existing.editorial_status, KnowledgeRelation.EditorialStatus.VALIDATED)
        self.assertEqual(
            KnowledgeRelation.objects.filter(
                source=element,
                relation_type=KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
            ).count(),
            1,
        )

    def test_command_dry_run_rolls_back_contacts_and_relations(self):
        output = StringIO()

        call_command(
            "import_contact_positions",
            author_person_id=self.author.pk,
            dry_run=True,
            stdout=output,
        )

        self.assertFalse(
            KnowledgeConcept.objects.filter(kind=KnowledgeConcept.Kind.CONTACT_POSITION).exists()
        )
        self.assertFalse(
            KnowledgeRelation.objects.filter(
                relation_type__in=(
                    KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
                    KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
                )
            ).exists()
        )
        self.assertIn("Simulació completada: 5 contactes creats", output.getvalue())
