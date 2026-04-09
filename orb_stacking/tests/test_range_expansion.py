import unittest
from datetime import datetime, timezone

from orb_stacking.orb_levels import OrbLevels
from orb_stacking.range_expansion import (
    range_expansion_ratio,
    expansion_bonus,
    EXPANSION_BONUS_THRESHOLD,
)


def _make_orb(name: str, rng: float) -> OrbLevels:
    """Build a minimal OrbLevels with a specific range."""
    midpoint = rng / 2 if rng else 0.0
    return OrbLevels(
        name=name,
        high=rng,
        low=0.0,
        range=rng,
        midpoint=midpoint,
        close=0.0,
        close_pct=0.0 if rng else None,
        locked_at=datetime(2026, 4, 9, 13, 50, tzinfo=timezone.utc),
    )


class TestRangeExpansionRatio(unittest.TestCase):

    def test_ratio_math(self):
        """orb20.range=4.0, orb60.range=10.0 → ratio=2.5."""
        orb20 = _make_orb("ORB20", 4.0)
        orb60 = _make_orb("ORB60", 10.0)
        self.assertAlmostEqual(range_expansion_ratio(orb20, orb60), 2.5, places=6)

    def test_zero_range_raises(self):
        """orb20.range=0 → ValueError (not inf)."""
        orb20 = _make_orb("ORB20", 0.0)
        orb60 = _make_orb("ORB60", 10.0)
        with self.assertRaises(ValueError):
            range_expansion_ratio(orb20, orb60)

    def test_large_expansion(self):
        """ratio 5.0 >> 2.5 → correct ratio and bonus=1."""
        orb20 = _make_orb("ORB20", 2.0)
        orb60 = _make_orb("ORB60", 10.0)
        ratio = range_expansion_ratio(orb20, orb60)
        self.assertAlmostEqual(ratio, 5.0, places=6)
        self.assertEqual(expansion_bonus(ratio), 1)

    def test_small_expansion(self):
        """orb60 same size as orb20 → ratio=1.0."""
        orb20 = _make_orb("ORB20", 8.0)
        orb60 = _make_orb("ORB60", 8.0)
        self.assertAlmostEqual(range_expansion_ratio(orb20, orb60), 1.0, places=6)


class TestExpansionBonus(unittest.TestCase):

    def test_boundary_at_2_5x_inclusive(self):
        """ratio exactly 2.5 → bonus=1 (inclusive)."""
        self.assertEqual(expansion_bonus(2.5), 1)

    def test_below_boundary(self):
        """ratio 2.49 → bonus=0."""
        self.assertEqual(expansion_bonus(2.49), 0)

    def test_bonus_threshold_constant(self):
        """EXPANSION_BONUS_THRESHOLD is 2.5."""
        self.assertEqual(EXPANSION_BONUS_THRESHOLD, 2.5)

    def test_zero_ratio_no_bonus(self):
        """ratio=0.0 → bonus=0."""
        self.assertEqual(expansion_bonus(0.0), 0)


if __name__ == "__main__":
    unittest.main()
