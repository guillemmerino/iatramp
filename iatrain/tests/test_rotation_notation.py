from django.test import SimpleTestCase

from iatrain.rotation_notation import NotationParseError, parse_rotation_notation


class RotationNotationParserTests(SimpleTestCase):
    def test_12_is_one_quarter_and_two_longitudinal_half_turns(self):
        parsed = parse_rotation_notation("12")

        self.assertEqual(parsed.transverse_quarters, 1)
        self.assertEqual(parsed.longitudinal_half_turns, (2,))
        self.assertEqual(parsed.transverse_direction, "unknown")
        self.assertEqual(parsed.normalized_notation, "12")

    def test_explicit_forward_direction_and_tuck_position(self):
        parsed = parse_rotation_notation(".41o")

        self.assertEqual(parsed.transverse_quarters, 4)
        self.assertEqual(parsed.longitudinal_half_turns, (1,))
        self.assertEqual(parsed.transverse_direction, "forward")
        self.assertEqual(parsed.direction_source, "explicit")
        self.assertEqual(parsed.position_code, "tuck")
        self.assertEqual(parsed.position_source, "explicit")

    def test_single_zero_expands_for_multi_segment_rotation(self):
        parsed = parse_rotation_notation("70")

        self.assertEqual(parsed.transverse_quarters, 7)
        self.assertEqual(parsed.longitudinal_half_turns, (0, 0))
        self.assertEqual(parsed.normalized_notation, "700")
        self.assertTrue(parsed.is_abbreviated)

    def test_nonzero_multi_segment_notation_must_be_explicit(self):
        parsed = parse_rotation_notation("720")

        self.assertEqual(parsed.transverse_quarters, 7)
        self.assertEqual(parsed.longitudinal_half_turns, (2, 0))
        self.assertEqual(parsed.normalized_notation, "720")
        self.assertFalse(parsed.is_abbreviated)

    def test_hyphens_and_zeroes_have_the_same_semantics(self):
        hyphens = parse_rotation_notation("8--")
        zeroes = parse_rotation_notation("800")

        self.assertEqual(hyphens.transverse_quarters, zeroes.transverse_quarters)
        self.assertEqual(hyphens.longitudinal_half_turns, zeroes.longitudinal_half_turns)
        self.assertEqual(hyphens.normalized_notation, "800")
        self.assertTrue(hyphens.is_abbreviated)
        self.assertFalse(zeroes.is_abbreviated)

    def test_multiple_somersault_example_is_parsed_by_segment(self):
        parsed = parse_rotation_notation("813.<")

        self.assertEqual(parsed.transverse_quarters, 8)
        self.assertEqual(parsed.longitudinal_half_turns, (1, 3))
        self.assertEqual(parsed.transverse_direction, "backward")
        self.assertEqual(parsed.position_code, "pike")
        self.assertEqual(parsed.normalized_notation, "813.<")

    def test_multi_digit_quarter_count_uses_expected_segment_count(self):
        explicit = parse_rotation_notation("12000")
        abbreviated = parse_rotation_notation("120")

        self.assertEqual(explicit.transverse_quarters, 12)
        self.assertEqual(explicit.longitudinal_half_turns, (0, 0, 0))
        self.assertEqual(abbreviated.transverse_quarters, 12)
        self.assertEqual(abbreviated.longitudinal_half_turns, (0, 0, 0))
        self.assertEqual(abbreviated.normalized_notation, "12000")
        self.assertTrue(abbreviated.is_abbreviated)

    def test_direction_dot_is_invalid_when_there_is_no_transverse_rotation(self):
        with self.assertRaises(NotationParseError):
            parse_rotation_notation(".00")

    def test_malformed_notation_is_rejected(self):
        for notation in ("", "abc", "4.1", ".41."):
            with self.subTest(notation=notation):
                with self.assertRaises(NotationParseError):
                    parse_rotation_notation(notation)

