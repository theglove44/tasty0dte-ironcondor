from __future__ import annotations

import unittest

from orb_stacking.sizing import (
    BASE_MULT,
    MAX_CONTRACTS,
    STACK_MULT,
    compute_contracts,
)


class TestFormulaFixtures(unittest.TestCase):
    def test_half_half_calendar0(self) -> None:
        result = compute_contracts("HALF", "HALF", 0)
        self.assertEqual(result["raw"], 0.25)
        self.assertEqual(result["contracts"], 0)
        self.assertEqual(result["clamped"], 1)  # diagnostic: would have been 1 without raw<0.5 gate

    def test_normal_normal_calendar0(self) -> None:
        result = compute_contracts("NORMAL", "NORMAL", 0)
        self.assertEqual(result["raw"], 1.0)
        self.assertEqual(result["contracts"], 1)

    def test_plus_double_calendar_plus1(self) -> None:
        result = compute_contracts("PLUS", "DOUBLE", 1)
        self.assertEqual(result["raw"], 2.8125)
        self.assertEqual(result["contracts"], 3)

    def test_double_double_calendar_plus1(self) -> None:
        result = compute_contracts("DOUBLE", "DOUBLE", 1)
        self.assertEqual(result["raw"], 3.75)
        self.assertEqual(result["contracts"], 4)

    def test_double_double_calendar_plus2_clamped(self) -> None:
        result = compute_contracts("DOUBLE", "DOUBLE", 2)
        self.assertEqual(result["raw"], 4.5)
        self.assertEqual(result["contracts"], 4)

    def test_double_double_triple_witching(self) -> None:
        result = compute_contracts("DOUBLE", "DOUBLE", -2)
        self.assertEqual(result["raw"], 1.5)
        self.assertEqual(result["contracts"], 2)

    def test_exited_hard_zero(self) -> None:
        result = compute_contracts("EXITED", "DOUBLE", 2)
        self.assertEqual(result["contracts"], 0)
        self.assertEqual(result["stack_mult"], 0.0)
        self.assertEqual(result["clamped"], 1)

    def test_half_half_calendar_minus2(self) -> None:
        result = compute_contracts("HALF", "HALF", -2)
        self.assertEqual(result["raw"], 0.125)
        self.assertEqual(result["contracts"], 0)
        self.assertEqual(result["clamped"], 1)  # diagnostic: would have been 1 without raw<0.5 gate

    def test_bankers_rounding_canary(self) -> None:
        result = compute_contracts("DOUBLE", "PLUS", 0)
        self.assertEqual(result["raw"], 2.5)
        self.assertEqual(result["contracts"], 2)


class TestAdditionalCases(unittest.TestCase):
    def test_half_normal_at_threshold(self) -> None:
        result = compute_contracts("HALF", "NORMAL", 0)
        self.assertEqual(result["raw"], 0.5)
        self.assertEqual(result["contracts"], 1)

    def test_double_half_calendar0(self) -> None:
        result = compute_contracts("DOUBLE", "HALF", 0)
        self.assertEqual(result["raw"], 1.0)
        self.assertEqual(result["contracts"], 1)

    def test_plus_plus_calendar0(self) -> None:
        result = compute_contracts("PLUS", "PLUS", 0)
        self.assertEqual(result["raw"], 1.875)
        self.assertEqual(result["contracts"], 2)

    def test_normal_plus_calendar_plus2(self) -> None:
        result = compute_contracts("NORMAL", "PLUS", 2)
        self.assertEqual(result["raw"], 1.875)
        self.assertEqual(result["contracts"], 2)

    def test_double_normal_calendar_minus1(self) -> None:
        result = compute_contracts("DOUBLE", "NORMAL", -1)
        self.assertEqual(result["raw"], 1.5)
        self.assertEqual(result["contracts"], 2)

    def test_half_double_calendar_plus2(self) -> None:
        result = compute_contracts("HALF", "DOUBLE", 2)
        self.assertEqual(result["raw"], 1.125)
        self.assertEqual(result["contracts"], 1)


class TestValidation(unittest.TestCase):
    def test_flat_tier_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "FLAT"):
            compute_contracts("FLAT", "NORMAL", 0)

        with self.assertRaisesRegex(ValueError, "ORB20_BREAK"):
            compute_contracts("FLAT", "NORMAL", 0)

    def test_unknown_stack_tier_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_contracts("BOGUS", "NORMAL", 0)

    def test_unknown_base_tier_raises(self) -> None:
        with self.assertRaises(ValueError):
            compute_contracts("NORMAL", "BOGUS", 0)


class TestCalendarClamping(unittest.TestCase):
    def test_calendar_score_above_max_clamped(self) -> None:
        self.assertEqual(
            compute_contracts("NORMAL", "NORMAL", 5),
            compute_contracts("NORMAL", "NORMAL", 2),
        )
        self.assertEqual(
            compute_contracts("NORMAL", "NORMAL", -5),
            compute_contracts("NORMAL", "NORMAL", -2),
        )


class TestReturnDictShape(unittest.TestCase):
    def test_return_dict_shape(self) -> None:
        result = compute_contracts("EXITED", "DOUBLE", 2)

        self.assertEqual(
            set(result),
            {"contracts", "stack_mult", "base_mult", "calendar_mult", "raw", "clamped"},
        )

        self.assertIsInstance(result["contracts"], int)
        self.assertIsInstance(result["stack_mult"], float)
        self.assertIsInstance(result["base_mult"], float)
        self.assertIsInstance(result["calendar_mult"], float)
        self.assertIsInstance(result["raw"], float)
        self.assertIsInstance(result["clamped"], int)

        self.assertEqual(result["contracts"], 0)
        self.assertEqual(result["clamped"], 1)


if __name__ == "__main__":
    unittest.main()
