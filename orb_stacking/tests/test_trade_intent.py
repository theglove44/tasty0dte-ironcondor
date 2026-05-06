from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from orb_stacking.orb_levels import GAP_REASON, OrbLevels
from orb_stacking.trade_intent import SKIP_REASONS, OrbSkipEvent, OrbTradeIntent


def _make_orb20():
    return OrbLevels(
        name="ORB20",
        high=6560.0,
        low=6551.40,
        range=8.60,
        midpoint=6555.70,
        close=6558.71,
        close_pct=0.85,
        locked_at=datetime(2026, 4, 9, 13, 50, tzinfo=timezone.utc),
    )


class TradeIntentTests(unittest.TestCase):
    def test_orb_trade_intent_construction(self):
        intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 9, 14, 5, tzinfo=timezone.utc),
            direction="bull",
            spread_side="put",
            short_strike=6530.0,
            long_strike=6525.0,
            expected_credit=1.20,
            stack_tier="DOUBLE",
            base_tier="NORMAL",
            contracts=2,
            stack_score=4,
            base_score=1,
            calendar_score=0,
            calendar_labels=[],
            closes_aligned_count=2,
            range_expansion_ratio=1.80,
            is_a_plus_buffer=True,
            is_immediate=False,
            orb20=_make_orb20(),
        )

        self.assertEqual(intent.timestamp, datetime(2026, 4, 9, 14, 5, tzinfo=timezone.utc))
        self.assertEqual(intent.direction, "bull")
        self.assertEqual(intent.spread_side, "put")
        self.assertEqual(intent.short_strike, 6530.0)
        self.assertEqual(intent.long_strike, 6525.0)
        self.assertEqual(intent.expected_credit, 1.20)
        self.assertEqual(intent.stack_tier, "DOUBLE")
        self.assertEqual(intent.base_tier, "NORMAL")
        self.assertEqual(intent.contracts, 2)
        self.assertEqual(intent.stack_score, 4)
        self.assertEqual(intent.base_score, 1)
        self.assertEqual(intent.calendar_score, 0)
        self.assertEqual(intent.calendar_labels, [])
        self.assertEqual(intent.closes_aligned_count, 2)
        self.assertAlmostEqual(intent.range_expansion_ratio, 1.80)
        self.assertTrue(intent.is_a_plus_buffer)
        self.assertFalse(intent.is_immediate)
        self.assertIsNotNone(intent.orb20)
        self.assertIsNone(intent.orb30)
        self.assertIsNone(intent.orb60)
        self.assertEqual(intent.notes, "")

    def test_orb_skip_event_construction(self):
        ts = datetime(2026, 4, 9, 14, 0, tzinfo=timezone.utc)
        event = OrbSkipEvent(timestamp=ts, reason="base_tier_skip")

        self.assertEqual(event.timestamp, ts)
        self.assertEqual(event.reason, "base_tier_skip")
        self.assertIsNone(event.direction)
        self.assertIsNone(event.orb20)
        self.assertIsNone(event.orb30)
        self.assertIsNone(event.orb60)
        self.assertEqual(event.stack_tier, "FLAT")
        self.assertIsNone(event.base_tier)
        self.assertEqual(event.notes, "")

        override = OrbSkipEvent(
            timestamp=ts,
            reason="credit_too_low",
            direction="bear",
            stack_tier="HALF",
            base_tier="NORMAL",
            notes="test note",
        )

        self.assertEqual(override.reason, "credit_too_low")
        self.assertEqual(override.direction, "bear")
        self.assertEqual(override.stack_tier, "HALF")
        self.assertEqual(override.base_tier, "NORMAL")
        self.assertEqual(override.notes, "test note")

    def test_skip_reasons_is_frozenset(self):
        self.assertIsInstance(SKIP_REASONS, frozenset)
        self.assertTrue(len(SKIP_REASONS) > 0)

    def test_skip_reasons_contains_required_strings(self):
        self.assertEqual(
            SKIP_REASONS,
            {
                "no_breakout_before_noon",
                "orb20_close_middle_bear",
                "orb30_opposes_warning",
                "orb60_opposes_hard_exit",
                "base_tier_skip",
                "credit_too_low",
                "credit_too_high_flagged",
                "api_error",
                "atr_not_ready",
                "calendar_blocked",
                "daily_cap",
                "bar_gap_during_lock",
                "zero_contracts",
            },
        )

    def test_skip_reasons_contains_gap_reason_token(self):
        """bar_gap_during_lock in SKIP_REASONS must match GAP_REASON from orb_levels."""
        self.assertIn(GAP_REASON, SKIP_REASONS)

    def test_dataclasses_are_mutable(self):
        """frozen=False is an explicit contract — mutation must not raise."""
        intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 9, 14, 5, tzinfo=timezone.utc),
            direction="bull",
            spread_side="put",
            short_strike=6530.0,
            long_strike=6525.0,
            expected_credit=1.20,
            stack_tier="DOUBLE",
            base_tier="NORMAL",
            contracts=2,
            stack_score=4,
            base_score=1,
            calendar_score=0,
            calendar_labels=[],
            closes_aligned_count=2,
            range_expansion_ratio=1.80,
            is_a_plus_buffer=True,
            is_immediate=False,
            orb20=_make_orb20(),
        )
        intent.notes = "mutated"
        self.assertEqual(intent.notes, "mutated")

        skip = OrbSkipEvent(
            timestamp=datetime(2026, 4, 9, 14, 0, tzinfo=timezone.utc),
            reason="api_error",
        )
        skip.notes = "retry"
        self.assertEqual(skip.notes, "retry")

    def test_no_old_field_names(self):
        field_names = {f.name for f in dataclasses.fields(OrbTradeIntent)}
        self.assertNotIn("macdv", field_names)
        self.assertNotIn("pulse_bar", field_names)
        self.assertNotIn("v_pattern", field_names)
        self.assertNotIn("bb_at_entry", field_names)


if __name__ == "__main__":
    unittest.main()
