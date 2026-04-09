from __future__ import annotations
import unittest
from datetime import datetime, timezone

from orb_stacking.exits import (
    REASON_ORB30_OPPOSES_REDUCE,
    REASON_ORB60_OPPOSES,
    HardExitSignal,
    bracket_levels,
    evaluate_exit_signal,
)
from orb_stacking.stacking import StackingEvent


def _make_event(
    kind: str,
    tier_in_snapshot: str = "HALF",
    direction: str = "bull",
    timestamp: datetime | None = None,
) -> StackingEvent:
    return StackingEvent(
        kind=kind,
        direction=direction,
        orb=None,
        bar={},
        timestamp=timestamp or datetime(2026, 4, 9, 14, 50, tzinfo=timezone.utc),
        state_snapshot={
            "stack_tier": tier_in_snapshot,
            "closes_aligned": 1,
            "direction": direction,
        },
    )


class TestBracketLevels(unittest.TestCase):
    def test_bracket_levels_defaults(self):
        result = bracket_levels(1.00)
        self.assertEqual(result["target_debit"], 0.50)
        self.assertEqual(result["stop_debit"], 2.00)

    def test_bracket_levels_custom_target_pct(self):
        result = bracket_levels(2.00, target_pct=0.25)
        self.assertEqual(result["target_debit"], 0.50)
        self.assertEqual(result["stop_debit"], 4.00)

    def test_bracket_levels_custom_stop_mult(self):
        result = bracket_levels(1.50, stop_mult=3.0)
        self.assertEqual(result["target_debit"], 0.75)
        self.assertEqual(result["stop_debit"], 4.50)

    def test_bracket_levels_zero_credit(self):
        result = bracket_levels(0.0)
        self.assertEqual(result["target_debit"], 0.0)
        self.assertEqual(result["stop_debit"], 0.0)

    def test_bracket_levels_negative_credit_raises(self):
        with self.assertRaises(ValueError):
            bracket_levels(-1.0)

    def test_bracket_levels_negative_target_pct_raises(self):
        with self.assertRaises(ValueError):
            bracket_levels(1.0, target_pct=-0.1)

    def test_bracket_levels_negative_stop_mult_raises(self):
        with self.assertRaises(ValueError):
            bracket_levels(1.0, stop_mult=-1.0)

    def test_bracket_levels_return_keys_exact(self):
        self.assertEqual(set(bracket_levels(1.0).keys()), {"target_debit", "stop_debit"})


class TestEvaluateExitSignal(unittest.TestCase):
    def test_orb60_oppose_full_exit(self):
        event = _make_event("ORB60_OPPOSE", tier_in_snapshot="EXITED")
        signal = evaluate_exit_signal(event)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.reason, REASON_ORB60_OPPOSES)
        self.assertEqual(signal.position_tier_after, "EXITED")
        self.assertEqual(signal.position_tier_before, "EXITED")
        self.assertEqual(signal.timestamp, event.timestamp)

    def test_orb30_oppose_reduce_signal(self):
        event = _make_event("ORB30_OPPOSE", tier_in_snapshot="HALF")
        signal = evaluate_exit_signal(event)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.reason, REASON_ORB30_OPPOSES_REDUCE)
        self.assertEqual(signal.position_tier_after, "HALF")
        self.assertEqual(signal.position_tier_before, "HALF")

    def test_orb30_oppose_tier_before_taken_verbatim_from_snapshot(self):
        # tier_before should reflect whatever the snapshot contains, not a hardcoded value
        event = _make_event("ORB30_OPPOSE", tier_in_snapshot="NORMAL")
        signal = evaluate_exit_signal(event)
        self.assertEqual(signal.reason, REASON_ORB30_OPPOSES_REDUCE)
        self.assertEqual(signal.position_tier_before, "NORMAL")  # verbatim from snapshot
        self.assertEqual(signal.position_tier_after, "HALF")     # always HALF for ORB30

    def test_orb20_break_returns_none(self):
        self.assertIsNone(evaluate_exit_signal(_make_event("ORB20_BREAK")))

    def test_orb30_confirm_returns_none(self):
        self.assertIsNone(evaluate_exit_signal(_make_event("ORB30_CONFIRM")))

    def test_orb60_confirm_returns_none(self):
        self.assertIsNone(evaluate_exit_signal(_make_event("ORB60_CONFIRM")))

    def test_orb60_no_breakout_returns_none(self):
        self.assertIsNone(evaluate_exit_signal(_make_event("ORB60_NO_BREAKOUT")))

    def test_timeout_noon_returns_none(self):
        self.assertIsNone(evaluate_exit_signal(_make_event("TIMEOUT_NOON")))

    def test_orb60_oppose_always_exits_regardless_of_tier(self):
        ts = datetime(2026, 4, 9, 15, 20, tzinfo=timezone.utc)
        event = _make_event("ORB60_OPPOSE", tier_in_snapshot="NORMAL", timestamp=ts)
        signal = evaluate_exit_signal(event)
        self.assertEqual(signal.position_tier_after, "EXITED")
        self.assertEqual(signal.timestamp, ts)


if __name__ == "__main__":
    unittest.main()
