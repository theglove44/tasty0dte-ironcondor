import unittest
from datetime import datetime, timezone

from orb_stacking.orb_levels import OrbLevels
from orb_stacking.strike_selector import (
    SpreadSelection, CreditValidation,
    select_short_strike, buffer_to_nearest_5, compute_a_plus_buffer,
    is_a_plus_setup, select_spread, validate_credit,
    A_PLUS_BUFFER_THRESHOLD, MIN_VALID_CREDIT, CAUTION_CREDIT_THRESHOLD,
)


def _make_orb20(high: float, low: float) -> OrbLevels:
    """Create an ORB20 with given high/low."""
    midpoint = (high + low) / 2
    return OrbLevels(
        name="ORB20", high=high, low=low,
        range=high - low, midpoint=midpoint,
        close=low, close_pct=0.0,
        locked_at=datetime(2026, 4, 9, 13, 50, tzinfo=timezone.utc),
    )


class TestSelectShortStrike(unittest.TestCase):
    """Test select_short_strike rounding logic."""

    def test_midpoint_rounds_to_nearest_5(self):
        """midpoint=5923.40 → 5925"""
        result = select_short_strike(5923.40)
        self.assertEqual(result, 5925)

    def test_midpoint_rounds_up_to_nearest_5(self):
        """midpoint=5927.60 → 5930"""
        result = select_short_strike(5927.60)
        self.assertEqual(result, 5930)

    def test_midpoint_exactly_on_boundary(self):
        """midpoint=5925.00 → 5925"""
        result = select_short_strike(5925.00)
        self.assertEqual(result, 5925)

    def test_return_type_is_int(self):
        """Result is int type."""
        result = select_short_strike(5923.40)
        self.assertIsInstance(result, int)

    def test_grid_zero_raises_value_error(self):
        """grid=0 raises ValueError."""
        with self.assertRaises(ValueError):
            select_short_strike(5925.0, grid=0)

    def test_grid_negative_raises_value_error(self):
        """grid=-5 raises ValueError."""
        with self.assertRaises(ValueError):
            select_short_strike(5925.0, grid=-5)

    def test_non_integer_grid_not_truncated(self):
        """grid=1.0 (non-default) must not be int-truncated; rounds midpoint to nearest 1."""
        result = select_short_strike(5923.7, grid=1.0)
        self.assertEqual(result, 5924)
        self.assertIsInstance(result, int)

    def test_bankers_rounding_documented(self):
        """Python round() uses banker's rounding at exact .5 ties on the grid.
        5922.5 / 5 = 1184.5 → rounds to 1184 (even) → 5920.
        This is deterministic and acceptable for SPX (such ties are vanishingly rare)."""
        result = select_short_strike(5922.5)
        self.assertEqual(result, 5920)  # banker's rounding: 1184.5 → 1184 → 5920


class TestBufferToNearest5(unittest.TestCase):
    """Test buffer_to_nearest_5 distance calculation."""

    def test_on_boundary_returns_zero(self):
        """Level exactly on $5 boundary returns 0.0."""
        result = buffer_to_nearest_5(5925.00)
        self.assertEqual(result, 0.0)

    def test_max_distance_at_halfway(self):
        """Level exactly halfway between boundaries returns 2.5."""
        result = buffer_to_nearest_5(5927.50)
        self.assertEqual(result, 2.5)

    def test_just_below_boundary(self):
        """Level 0.2 below boundary returns 0.2."""
        result = buffer_to_nearest_5(5924.80)
        self.assertAlmostEqual(result, 0.20, places=6)

    def test_just_above_boundary(self):
        """Level 0.3 above boundary returns 0.3."""
        result = buffer_to_nearest_5(5925.30)
        self.assertAlmostEqual(result, 0.30, places=6)

    def test_always_in_range_0_to_2_5(self):
        """All levels in [5920, 5930] stay within [0, 2.5]."""
        for level in [5920.0 + i * 0.1 for i in range(101)]:
            result = buffer_to_nearest_5(level)
            self.assertGreaterEqual(result, 0.0)
            self.assertLessEqual(result, 2.5)


class TestComputeAPlusBuffer(unittest.TestCase):
    """Test compute_a_plus_buffer for bull and bear spreads."""

    def test_bull_buffer_a_plus_worked_example(self):
        """Bull: high=5929.00, short=5925 → buffer=4.00."""
        orb20 = _make_orb20(high=5929.00, low=5919.80)
        result = compute_a_plus_buffer(orb20, 5925, "bull")
        self.assertAlmostEqual(result, 4.00, places=6)

    def test_bull_buffer_below_threshold_worked_example(self):
        """Bull: high=5928.40, short=5925 → buffer≈3.40."""
        orb20 = _make_orb20(high=5928.40, low=5919.80)
        result = compute_a_plus_buffer(orb20, 5925, "bull")
        self.assertAlmostEqual(result, 3.40, places=6)

    def test_bear_buffer_positive(self):
        """Bear: low=5921.00, short=5925 → buffer=4.00."""
        orb20 = _make_orb20(high=5930.20, low=5921.00)
        result = compute_a_plus_buffer(orb20, 5925, "bear")
        self.assertAlmostEqual(result, 4.00, places=6)

    def test_bear_buffer_below_threshold(self):
        """Bear: low=5921.60, short=5925 → buffer≈3.40."""
        orb20 = _make_orb20(high=5930.20, low=5921.60)
        result = compute_a_plus_buffer(orb20, 5925, "bear")
        self.assertAlmostEqual(result, 3.40, places=6)

    def test_negative_buffer_when_short_inside_range(self):
        """Short inside ORB range: high=5923, low=5918, bull, short=5925 → buffer=-2.0."""
        orb20 = _make_orb20(high=5923.00, low=5918.00)
        result = compute_a_plus_buffer(orb20, 5925, "bull")
        self.assertAlmostEqual(result, -2.00, places=6)

    def test_invalid_direction_raises(self):
        """Invalid direction raises ValueError."""
        orb20 = _make_orb20(high=5930.20, low=5921.00)
        with self.assertRaises(ValueError):
            compute_a_plus_buffer(orb20, 5925, "flat")


class TestIsAPlusSetup(unittest.TestCase):
    """Test is_a_plus_setup threshold check."""

    def test_a_plus_exact_boundary(self):
        """buffer=4.0 is A+ (exact boundary)."""
        self.assertTrue(is_a_plus_setup(4.0))

    def test_not_a_plus_just_below(self):
        """buffer=3.99 is not A+."""
        self.assertFalse(is_a_plus_setup(3.99))

    def test_negative_buffer_not_a_plus(self):
        """buffer=-1.0 is not A+."""
        self.assertFalse(is_a_plus_setup(-1.0))


class TestSelectSpread(unittest.TestCase):
    """Test select_spread structure and A+ classification."""

    def test_bull_spread_structure(self):
        """Bull: high=5929, low=5919.8 → short=5925, long=5920, put, buffer=4.0, A+."""
        orb20 = _make_orb20(high=5929.00, low=5919.80)
        result = select_spread(orb20, "bull")
        self.assertEqual(result.direction, "bull")
        self.assertEqual(result.short_strike, 5925)
        self.assertEqual(result.long_strike, 5920)
        self.assertEqual(result.spread_type, "put")
        self.assertAlmostEqual(result.buffer, 4.00, places=6)
        self.assertTrue(result.is_a_plus)

    def test_bear_spread_structure(self):
        """Bear: high=5930.2, low=5921 → short=5925, long=5930, call, buffer=4.0, A+."""
        orb20 = _make_orb20(high=5930.20, low=5921.00)
        result = select_spread(orb20, "bear")
        self.assertEqual(result.direction, "bear")
        self.assertEqual(result.short_strike, 5925)
        self.assertEqual(result.long_strike, 5930)
        self.assertEqual(result.spread_type, "call")
        self.assertAlmostEqual(result.buffer, 4.00, places=6)
        self.assertTrue(result.is_a_plus)

    def test_bull_non_a_plus_worked_example(self):
        """Bull: high=5928.4, low=5919.8 → short=5925, buffer≈3.4, not A+, long=5920."""
        orb20 = _make_orb20(high=5928.40, low=5919.80)
        result = select_spread(orb20, "bull")
        self.assertEqual(result.short_strike, 5925)
        self.assertAlmostEqual(result.buffer, 3.40, places=6)
        self.assertFalse(result.is_a_plus)
        self.assertEqual(result.long_strike, 5920)

    def test_select_spread_invalid_direction_raises(self):
        """Invalid direction raises ValueError."""
        orb20 = _make_orb20(high=5930.20, low=5921.00)
        with self.assertRaises(ValueError):
            select_spread(orb20, "sideways")

    def test_select_spread_returns_frozen_dataclass(self):
        """Result is frozen; assignment raises AttributeError."""
        orb20 = _make_orb20(high=5930.20, low=5921.00)
        result = select_spread(orb20, "bull")
        with self.assertRaises(AttributeError):
            result.short_strike = 9999


class TestValidateCredit(unittest.TestCase):
    """Test validate_credit band checks."""

    def test_credit_below_min_invalid(self):
        """credit=0.79 is invalid: skip: credit < 0.80."""
        result = validate_credit(0.79)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "skip: credit < 0.80")

    def test_credit_exactly_min_valid(self):
        """credit=0.80 is valid: ok."""
        result = validate_credit(0.80)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.reason, "ok")

    def test_credit_mid_band_valid(self):
        """credit=1.05 is valid: ok."""
        result = validate_credit(1.05)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.reason, "ok")

    def test_credit_exactly_max_ok_valid(self):
        """credit=1.50 is valid: ok."""
        result = validate_credit(1.50)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.reason, "ok")

    def test_credit_above_caution_threshold(self):
        """credit=1.51 is valid but caution: credit > 1.50."""
        result = validate_credit(1.51)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.reason, "caution: credit > 1.50")

    def test_credit_zero_invalid(self):
        """credit=0.0 is invalid: skip: credit < 0.80."""
        result = validate_credit(0.0)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "skip: credit < 0.80")

    def test_credit_negative_invalid(self):
        """credit=-0.50 is invalid: skip: credit < 0.80."""
        result = validate_credit(-0.50)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "skip: credit < 0.80")

    def test_nan_raises_value_error(self):
        """NaN credit must raise ValueError, not silently pass as valid."""
        import math
        with self.assertRaises(ValueError):
            validate_credit(float("nan"))

    def test_inf_raises_value_error(self):
        """Infinite credit must raise ValueError."""
        with self.assertRaises(ValueError):
            validate_credit(float("inf"))


if __name__ == "__main__":
    unittest.main()
