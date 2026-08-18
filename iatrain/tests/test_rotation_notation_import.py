from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Person
from iatrain.legacy_imports.main_elements import MAIN_ELEMENTS, import_main_elements
from iatrain.legacy_imports.rotation_notations import import_rotation_notations
from iatrain.models import (
    ElementNotation,
    ElementRotation,
    ElementRotationSegment,
    KnowledgeConcept,
)
from iatrain.rotation_notation import parse_rotation_notation


class RotationNotationImportTests(TestCase):
    def setUp(self):
        self.author = Person.objects.create(first_name="Curadora", last_name="Tècnica")
        import_main_elements(author=self.author)

    def test_import_parses_all_legacy_elements_as_draft_profiles(self):
        summary = import_rotation_notations(author=self.author)
        expected_segments = sum(
            parse_rotation_notation(row[5]).segment_count for row in MAIN_ELEMENTS
        )

        self.assertEqual(summary.profiles_created, len(MAIN_ELEMENTS))
        self.assertEqual(summary.segments_created, expected_segments)
        self.assertEqual(summary.notations_created, len(MAIN_ELEMENTS))
        self.assertEqual(summary.invalid_notations, 0)
        self.assertEqual(ElementRotation.objects.count(), len(MAIN_ELEMENTS))
        self.assertEqual(ElementRotationSegment.objects.count(), expected_segments)
        self.assertEqual(ElementNotation.objects.count(), len(MAIN_ELEMENTS))
        self.assertFalse(
            ElementRotation.objects.exclude(
                editorial_status=KnowledgeConcept.EditorialStatus.DRAFT
            ).exists()
        )

    def test_barani_and_multiple_somersaults_have_structured_segments(self):
        import_rotation_notations(author=self.author)

        barani = ElementRotation.objects.get(element__name="Barani agrupat")
        half_in_rudy_out = ElementRotation.objects.get(
            element__name="Half in rudy out carpat"
        )

        self.assertEqual(barani.transverse_quarters, 4)
        self.assertEqual(barani.transverse_direction, ElementRotation.Direction.FORWARD)
        self.assertEqual(
            list(barani.segments.values_list("longitudinal_half_turns", flat=True)),
            [1],
        )
        self.assertEqual(half_in_rudy_out.transverse_quarters, 8)
        self.assertEqual(
            list(
                half_in_rudy_out.segments.values_list(
                    "longitudinal_half_turns", flat=True
                )
            ),
            [1, 3],
        )

    def test_legacy_body_shape_is_only_a_hint_and_does_not_resolve_cody_position(self):
        import_rotation_notations(author=self.author)

        notation = ElementNotation.objects.get(element__name="Cody")

        self.assertEqual(notation.position_source, ElementNotation.ResolutionSource.UNKNOWN)
        self.assertEqual(notation.position_symbol, "")
        self.assertEqual(notation.parse_details["legacy_body_shape_hint"], "tuck")
        self.assertIsNone(notation.parse_details["position_code"])

    def test_import_is_idempotent(self):
        first = import_rotation_notations(author=self.author)

        second = import_rotation_notations(author=self.author)

        self.assertEqual(first.profiles_created, len(MAIN_ELEMENTS))
        self.assertEqual(second.profiles_created, 0)
        self.assertEqual(second.profiles_existing, len(MAIN_ELEMENTS))
        self.assertEqual(second.segments_created, 0)
        self.assertEqual(second.notations_created, 0)
        self.assertEqual(second.notations_existing, len(MAIN_ELEMENTS))

    def test_existing_conflicting_profile_is_not_overwritten(self):
        barani = KnowledgeConcept.objects.get(name="Barani agrupat")
        existing = ElementRotation.objects.create(
            element=barani,
            transverse_quarters=4,
            transverse_direction=ElementRotation.Direction.BACKWARD,
            authored_by=self.author,
        )
        ElementRotationSegment.objects.create(
            rotation=existing,
            sequence_index=1,
            longitudinal_half_turns=1,
        )

        summary = import_rotation_notations(author=self.author)

        self.assertEqual(summary.profile_conflicts, 1)
        existing.refresh_from_db()
        self.assertEqual(existing.transverse_direction, ElementRotation.Direction.BACKWARD)
        notation = ElementNotation.objects.get(element=barani)
        self.assertEqual(notation.parse_status, ElementNotation.ParseStatus.AMBIGUOUS)
        self.assertIsNone(notation.rotation)

    def test_invalid_legacy_notation_is_preserved_for_review(self):
        cody = KnowledgeConcept.objects.get(name="Cody")
        cody.attributes["legacy_numeric_notation"] = "not-a-code"
        cody.save(update_fields=("attributes", "updated_at"))

        summary = import_rotation_notations(author=self.author)

        self.assertEqual(summary.invalid_notations, 1)
        notation = ElementNotation.objects.get(element=cody)
        self.assertEqual(notation.parse_status, ElementNotation.ParseStatus.INVALID)
        self.assertIn("error", notation.parse_details)
        self.assertIsNone(notation.rotation)

    def test_command_dry_run_rolls_back_every_rotation_record(self):
        output = StringIO()

        call_command(
            "import_rotation_notations",
            author_person_id=self.author.pk,
            dry_run=True,
            stdout=output,
        )

        self.assertEqual(ElementRotation.objects.count(), 0)
        self.assertEqual(ElementRotationSegment.objects.count(), 0)
        self.assertEqual(ElementNotation.objects.count(), 0)
        self.assertIn("Simulació completada: 47 perfils creats", output.getvalue())

