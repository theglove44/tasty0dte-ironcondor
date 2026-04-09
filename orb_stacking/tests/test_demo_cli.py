import unittest
from datetime import datetime, timezone

from orb_stacking.engine import OrbStackingEngine
from orb_stacking.orb_levels import OrbLevels
from orb_stacking.trade_intent import OrbSkipEvent, OrbTradeIntent

import orb_stacking_demo as demo


def _make_orb20() -> OrbLevels:
    return OrbLevels(
        name="ORB20",
        high=6560.0,
        low=6540.0,
        range=20.0,
        midpoint=6550.0,
        close=6558.0,
        close_pct=0.9,
        locked_at=datetime(2026, 4, 9, 13, 0, tzinfo=timezone.utc),
    )


def _bar(ts: datetime, price: float = 6550.0) -> dict:
    return {
        "start": ts,
        "open": price,
        "high": price + 10,
        "low": price - 10,
        "close": price,
        "volume": 1000,
        "time": int(ts.timestamp() * 1000),
    }


class TestDemoCliPrinters(unittest.TestCase):
    def setUp(self) -> None:
        self.ts = datetime(2026, 4, 9, 13, 5, tzinfo=timezone.utc)

    def test_format_intent_contains_key_fields(self) -> None:
        intent = OrbTradeIntent(
            timestamp=self.ts,
            direction="bull",
            spread_side="put",
            short_strike=6530.0,
            long_strike=6525.0,
            expected_credit=None,
            stack_tier="HALF",
            base_tier="NORMAL",
            contracts=2,
            stack_score=1,
            base_score=1,
            calendar_score=0,
            calendar_labels=[],
            closes_aligned_count=1,
            range_expansion_ratio=1.0,
            is_a_plus_buffer=False,
            is_immediate=False,
            orb20=_make_orb20(),
        )
        skip = OrbSkipEvent(
            timestamp=self.ts,
            reason="orb30_opposes_warning",
            direction="bull",
            stack_tier="HALF",
        )

        intent_line = demo.format_intent(intent)
        skip_line = demo.format_skip(skip)

        for text in ("UK]", "INTENT", "HALF", "bull", "6530", "6525", "2x", "NORMAL"):
            self.assertIn(text, intent_line)
        for text in ("UK]", "SKIP", "orb30_opposes_warning", "bull", "HALF"):
            self.assertIn(text, skip_line)

    def test_format_skip_no_direction_renders_dash(self) -> None:
        skip = OrbSkipEvent(timestamp=self.ts, reason="no_breakout_before_noon")
        line = demo.format_skip(skip)
        self.assertIn("dir=-", line)

    def test_format_intent_with_calendar_labels(self) -> None:
        intent = OrbTradeIntent(
            timestamp=self.ts,
            direction="bear",
            spread_side="call",
            short_strike=6570.0,
            long_strike=6575.0,
            expected_credit=None,
            stack_tier="NORMAL",
            base_tier="PLUS",
            contracts=2,
            stack_score=2,
            base_score=3,
            calendar_score=1,
            calendar_labels=["FOMC"],
            closes_aligned_count=2,
            range_expansion_ratio=1.25,
            is_a_plus_buffer=False,
            is_immediate=False,
            orb20=_make_orb20(),
        )
        line = demo.format_intent(intent)
        self.assertIn("[FOMC]", line)

    def test_terminal_skip_reasons_tokens(self) -> None:
        self.assertIn("no_breakout_before_noon", demo.TERMINAL_SKIP_REASONS)
        self.assertIn("orb60_opposes_hard_exit", demo.TERMINAL_SKIP_REASONS)

    def test_print_events_returns_terminal_on_noon_skip(self) -> None:
        skip = OrbSkipEvent(
            timestamp=self.ts,
            reason="no_breakout_before_noon",
            stack_tier="FLAT",
        )
        terminal = demo.print_events([skip])
        self.assertTrue(terminal)

    def test_print_events_returns_false_on_non_terminal_skip(self) -> None:
        skip = OrbSkipEvent(
            timestamp=self.ts,
            reason="orb30_opposes_warning",
            stack_tier="HALF",
        )
        terminal = demo.print_events([skip])
        self.assertFalse(terminal)

    def test_warmup_engine_primes_atr(self) -> None:
        engine = OrbStackingEngine()
        self.assertIsNone(engine._atr.value)
        import datetime as _dt
        base = _dt.datetime(2026, 4, 8, 9, 30, tzinfo=_dt.timezone.utc)
        bars = [
            _bar(base + _dt.timedelta(minutes=5 * i), 6550.0)
            for i in range(14)
        ]
        demo.warmup_engine(engine, bars)
        self.assertIsNotNone(engine._atr.value)

    def test_warmup_engine_does_not_emit_session_events(self) -> None:
        """warmup_engine must not trigger on_closed_bar — session state stays blank."""
        engine = OrbStackingEngine()
        import datetime as _dt
        base = _dt.datetime(2026, 4, 8, 9, 30, tzinfo=_dt.timezone.utc)
        bars = [
            _bar(base + _dt.timedelta(minutes=5 * i), 6550.0)
            for i in range(14)
        ]
        demo.warmup_engine(engine, bars)
        # session_date should remain None — warmup never called on_closed_bar
        self.assertIsNone(engine._session_date)


if __name__ == "__main__":
    unittest.main()
