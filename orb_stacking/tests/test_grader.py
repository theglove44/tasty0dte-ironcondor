"""Tests for Slice 7 — grader.py.

Covers every factor boundary per SoT §2.9, the Doc2 worked example,
tier mapping boundaries, and invariants of the factors_breakdown dict.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from orb_stacking.grader import (
    GraderInputs,
    grade_base_setup,
    TIER_HALF,
    TIER_NORMAL,
    TIER_PLUS,
    TIER_DOUBLE,
)
from orb_stacking.orb_levels import OrbLevels


def _make_orb20(
    *,
    range_: float = 8.60,
    close_pct: float | None = 0.85,
    high: float = 6560.0,
    low: float = 6551.40,
    close: float = 6558.71,
) -> OrbLevels:
    """Build an OrbLevels with the given range and close_pct."""
    midpoint = (high + low) / 2.0
    return OrbLevels(
        name="ORB20",
        high=high,
        low=low,
        range=range_,
        midpoint=midpoint,
        close=close,
        close_pct=close_pct,
        locked_at=datetime(2026, 4, 9, 13, 50, tzinfo=timezone.utc),
    )


def _make_inputs(
    *,
    orb20: OrbLevels | None = None,
    direction: str = "bull",
    breakout_timing_immediate: bool = False,
    atr14: float = 65.0,
    day_of_week: int = 1,       # Tuesday (neutral)
    buffer_dollars: float = 2.0,  # neutral [1.0, 4.0)
) -> GraderInputs:
    return GraderInputs(
        orb20=orb20 if orb20 is not None else _make_orb20(),
        direction=direction,
        breakout_timing_immediate=breakout_timing_immediate,
        atr14=atr14,
        day_of_week=day_of_week,
        buffer_dollars=buffer_dollars,
    )


class TestDoc2WorkedExample(unittest.TestCase):
    """Headline regression test: Doc2 canonical fixture."""

    def test_doc2_scores_to_double_tier(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=8.60, close_pct=0.85),
            direction="bull",
            breakout_timing_immediate=True,
            atr14=65.0,
            day_of_week=1,          # Tuesday -> 0
            buffer_dollars=3.40,    # in [1.0, 4.0) -> 0
        )
        result = grade_base_setup(inputs)
        self.assertEqual(result["score"], 4)
        self.assertEqual(result["tier"], TIER_DOUBLE)
        fb = result["factors_breakdown"]
        self.assertAlmostEqual(fb["orb_atr_ratio"], 8.60 / 65.0, places=6)
        self.assertEqual(fb["orb_atr_points"], 2)
        self.assertEqual(fb["immediate_points"], 1)
        self.assertEqual(fb["close_aligned_points"], 1)
        self.assertEqual(fb["dow_points"], 0)
        self.assertEqual(fb["buffer_points"], 0)


class TestOrbAtrRatioFactor(unittest.TestCase):

    def test_ratio_below_0_20_gives_plus_2(self):
        inputs = _make_inputs(orb20=_make_orb20(range_=10.0), atr14=100.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["orb_atr_points"], 2
        )

    def test_ratio_exactly_0_20_gives_plus_1(self):
        inputs = _make_inputs(orb20=_make_orb20(range_=20.0), atr14=100.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["orb_atr_points"], 1
        )

    def test_ratio_exactly_0_30_gives_plus_1(self):
        # 0.30 is the inclusive upper end of the +1 bin
        inputs = _make_inputs(orb20=_make_orb20(range_=30.0), atr14=100.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["orb_atr_points"], 1
        )

    def test_ratio_just_above_0_30_gives_0(self):
        inputs = _make_inputs(orb20=_make_orb20(range_=31.0), atr14=100.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["orb_atr_points"], 0
        )

    def test_ratio_exactly_0_40_gives_0(self):
        # 0.40 is still in the 0-bin (> 0.40 is the -1 threshold)
        inputs = _make_inputs(orb20=_make_orb20(range_=40.0), atr14=100.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["orb_atr_points"], 0
        )

    def test_ratio_just_above_0_40_gives_minus_1(self):
        inputs = _make_inputs(orb20=_make_orb20(range_=41.0), atr14=100.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["orb_atr_points"], -1
        )

    def test_atr14_zero_raises_value_error(self):
        inputs = _make_inputs(atr14=0.0)
        with self.assertRaises(ValueError):
            grade_base_setup(inputs)

    def test_atr14_negative_raises_value_error(self):
        """Negative ATR is physically impossible and must be rejected."""
        inputs = _make_inputs(atr14=-10.0)
        with self.assertRaises(ValueError):
            grade_base_setup(inputs)


class TestImmediateFactor(unittest.TestCase):

    def test_immediate_true_plus_1(self):
        inputs = _make_inputs(breakout_timing_immediate=True)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["immediate_points"], 1
        )

    def test_immediate_false_zero(self):
        inputs = _make_inputs(breakout_timing_immediate=False)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["immediate_points"], 0
        )


class TestCloseAlignmentFactor(unittest.TestCase):

    def test_bull_close_pct_exactly_0_80_plus_1(self):
        inputs = _make_inputs(orb20=_make_orb20(close_pct=0.80), direction="bull")
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["close_aligned_points"], 1
        )

    def test_bull_close_pct_0_79_zero(self):
        inputs = _make_inputs(orb20=_make_orb20(close_pct=0.79), direction="bull")
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["close_aligned_points"], 0
        )

    def test_bear_close_pct_exactly_0_20_plus_1(self):
        inputs = _make_inputs(orb20=_make_orb20(close_pct=0.20), direction="bear")
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["close_aligned_points"], 1
        )

    def test_bear_close_pct_0_21_zero(self):
        inputs = _make_inputs(orb20=_make_orb20(close_pct=0.21), direction="bear")
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["close_aligned_points"], 0
        )

    def test_close_pct_none_zero(self):
        inputs = _make_inputs(orb20=_make_orb20(close_pct=None), direction="bull")
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["close_aligned_points"], 0
        )

    def test_invalid_direction_raises_value_error(self):
        inputs = _make_inputs(direction="sideways")
        with self.assertRaises(ValueError):
            grade_base_setup(inputs)


class TestDayOfWeekFactor(unittest.TestCase):

    def test_thursday_plus_1(self):
        inputs = _make_inputs(day_of_week=3)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["dow_points"], 1
        )

    def test_friday_plus_1(self):
        inputs = _make_inputs(day_of_week=4)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["dow_points"], 1
        )

    def test_monday_minus_1(self):
        inputs = _make_inputs(day_of_week=0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["dow_points"], -1
        )

    def test_tuesday_zero_doc4_killed(self):
        """Tuesday returns 0 — Doc4 killed Tuesday as a DOW factor."""
        inputs = _make_inputs(day_of_week=1)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["dow_points"], 0
        )

    def test_wednesday_zero(self):
        inputs = _make_inputs(day_of_week=2)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["dow_points"], 0
        )


class TestBufferFactor(unittest.TestCase):

    def test_buffer_exactly_4_0_plus_1(self):
        inputs = _make_inputs(buffer_dollars=4.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["buffer_points"], 1
        )

    def test_buffer_0_99_minus_1(self):
        inputs = _make_inputs(buffer_dollars=0.99)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["buffer_points"], -1
        )

    def test_buffer_in_mid_band_zero(self):
        inputs = _make_inputs(buffer_dollars=2.5)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["buffer_points"], 0
        )

    def test_buffer_exactly_1_0_zero(self):
        inputs = _make_inputs(buffer_dollars=1.0)
        self.assertEqual(
            grade_base_setup(inputs)["factors_breakdown"]["buffer_points"], 0
        )


class TestTierMapping(unittest.TestCase):

    def test_score_minus_1_is_half(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=50.0, close_pct=None),
            atr14=100.0,
            breakout_timing_immediate=False,
            day_of_week=1,
            buffer_dollars=2.0,
        )
        r = grade_base_setup(inputs)
        self.assertEqual(r["score"], -1)
        self.assertEqual(r["tier"], TIER_HALF)

    def test_score_0_is_normal(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=35.0, close_pct=None),
            atr14=100.0,
            breakout_timing_immediate=False,
            day_of_week=1,
            buffer_dollars=2.0,
        )
        r = grade_base_setup(inputs)
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["tier"], TIER_NORMAL)

    def test_score_1_is_normal(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=35.0, close_pct=None),
            atr14=100.0,
            breakout_timing_immediate=True,
            day_of_week=1,
            buffer_dollars=2.0,
        )
        r = grade_base_setup(inputs)
        self.assertEqual(r["score"], 1)
        self.assertEqual(r["tier"], TIER_NORMAL)

    def test_score_2_is_plus(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=25.0, close_pct=None),
            atr14=100.0,
            breakout_timing_immediate=True,
            day_of_week=1,
            buffer_dollars=2.0,
        )
        r = grade_base_setup(inputs)
        self.assertEqual(r["score"], 2)
        self.assertEqual(r["tier"], TIER_PLUS)

    def test_score_3_is_plus(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=25.0, close_pct=0.90),
            atr14=100.0,
            direction="bull",
            breakout_timing_immediate=True,
            day_of_week=1,
            buffer_dollars=2.0,
        )
        r = grade_base_setup(inputs)
        self.assertEqual(r["score"], 3)
        self.assertEqual(r["tier"], TIER_PLUS)

    def test_score_4_is_double(self):
        inputs = _make_inputs(
            orb20=_make_orb20(range_=10.0, close_pct=0.90),
            atr14=100.0,
            direction="bull",
            breakout_timing_immediate=True,
            day_of_week=1,
            buffer_dollars=2.0,
        )
        r = grade_base_setup(inputs)
        self.assertEqual(r["score"], 4)
        self.assertEqual(r["tier"], TIER_DOUBLE)


class TestFactorsBreakdownShape(unittest.TestCase):

    def test_breakdown_has_all_required_keys(self):
        inputs = _make_inputs()
        fb = grade_base_setup(inputs)["factors_breakdown"]
        required_keys = {
            "orb_atr_ratio",
            "orb_atr_points",
            "immediate_points",
            "close_aligned_points",
            "dow_points",
            "buffer_points",
        }
        self.assertEqual(set(fb.keys()), required_keys)
        self.assertIsInstance(fb["orb_atr_ratio"], float)
        self.assertIsInstance(fb["orb_atr_points"], int)
        self.assertIsInstance(fb["immediate_points"], int)
        self.assertIsInstance(fb["close_aligned_points"], int)
        self.assertIsInstance(fb["dow_points"], int)
        self.assertIsInstance(fb["buffer_points"], int)


if __name__ == "__main__":
    unittest.main()
