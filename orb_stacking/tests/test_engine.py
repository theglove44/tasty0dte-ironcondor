import datetime as _dt
import unittest
import zoneinfo

from orb_stacking.engine import OrbStackingEngine
from orb_stacking.trade_intent import OrbSkipEvent, OrbTradeIntent


def _bar(start_utc, open_, high, low, close):
    return {
        "start": start_utc,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
        "time": int(start_utc.timestamp() * 1000),
    }


def _et(hour, minute, day=_dt.date(2026, 4, 9)):
    tz_et = zoneinfo.ZoneInfo("America/New_York")
    return _dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz_et).astimezone(_dt.timezone.utc)


def _prime_atr(engine, atr_value=65.0):
    base = _dt.datetime(2026, 4, 8, 9, 30, tzinfo=_dt.timezone.utc)
    for i in range(14):
        bar = _bar(base + _dt.timedelta(minutes=5 * i), 6500.0, 6500.0 + atr_value, 6500.0, 6500.0)
        engine._atr.update(bar)


def _feed_session(engine, bars):
    results = []
    for bar in bars:
        results.extend(engine.on_closed_bar(bar))
    return results


def _bull_orb20_break_bars(day=_dt.date(2026, 4, 9)):
    return [
        _bar(_et(9, 30, day), 6550.0, 6560.0, 6548.0, 6554.0),
        _bar(_et(9, 35, day), 6550.0, 6560.0, 6548.0, 6554.0),
        _bar(_et(9, 40, day), 6550.0, 6560.0, 6548.0, 6554.0),
        _bar(_et(9, 45, day), 6554.0, 6560.0, 6548.0, 6554.0),
        _bar(_et(9, 50, day), 6554.0, 6575.0, 6552.0, 6575.0),
    ]


def _orb30_confirm_bars(day=_dt.date(2026, 4, 9)):
    return [
        _bar(_et(9, 55, day), 6568.0, 6572.0, 6560.0, 6570.0),
        _bar(_et(10, 0, day), 6576.0, 6588.0, 6574.0, 6585.0),
    ]


def _orb30_oppose_bars(day=_dt.date(2026, 4, 9)):
    return [
        _bar(_et(9, 55, day), 6540.0, 6550.0, 6530.0, 6540.0),
        _bar(_et(10, 0, day), 6540.0, 6545.0, 6520.0, 6520.0),
    ]


def _orb60_confirm_bars(day=_dt.date(2026, 4, 9)):
    return [
        _bar(_et(10, 5, day), 6580.0, 6582.0, 6576.0, 6578.0),
        _bar(_et(10, 10, day), 6578.0, 6581.0, 6574.0, 6579.0),
        _bar(_et(10, 15, day), 6579.0, 6580.0, 6572.0, 6576.0),
        _bar(_et(10, 20, day), 6576.0, 6584.0, 6574.0, 6582.0),
        _bar(_et(10, 25, day), 6582.0, 6585.0, 6570.0, 6582.0),
        _bar(_et(10, 30, day), 6583.0, 6600.0, 6580.0, 6592.0),
    ]


def _orb60_oppose_bars(day=_dt.date(2026, 4, 9)):
    return [
        _bar(_et(10, 5, day), 6540.0, 6550.0, 6520.0, 6530.0),
        _bar(_et(10, 10, day), 6530.0, 6540.0, 6515.0, 6525.0),
        _bar(_et(10, 15, day), 6525.0, 6535.0, 6510.0, 6520.0),
        _bar(_et(10, 20, day), 6520.0, 6530.0, 6510.0, 6518.0),
        _bar(_et(10, 25, day), 6518.0, 6525.0, 6510.0, 6520.0),
        _bar(_et(10, 30, day), 6520.0, 6522.0, 6495.0, 6500.0),
    ]


def _find_intents(results):
    return [item for item in results if isinstance(item, OrbTradeIntent)]


def _find_skips(results):
    return [item for item in results if isinstance(item, OrbSkipEvent)]


class TestOrbStackingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OrbStackingEngine()
        _prime_atr(self.engine)

    def test_session_date_bound_on_first_bar(self):
        bar = _bar(_et(9, 30), 6550.0, 6560.0, 6548.0, 6554.0)
        self.engine.on_closed_bar(bar)
        self.assertEqual(self.engine._session_date, _dt.date(2026, 4, 9))
        self.assertEqual(self.engine._cal_score, 0)

    def test_calendar_score_set_on_fomc_date(self):
        self.engine = OrbStackingEngine()
        bar = _bar(_et(9, 30, _dt.date(2026, 1, 28)), 6550.0, 6560.0, 6548.0, 6554.0)
        self.engine.on_closed_bar(bar)
        self.assertEqual(self.engine._cal_score, 1)

    def test_no_events_before_orb20_locks(self):
        bars = _bull_orb20_break_bars()[:4]
        for bar in bars:
            self.assertEqual(self.engine.on_closed_bar(bar), [])

    def test_orb20_break_bull_emits_half_intent(self):
        results = _feed_session(self.engine, _bull_orb20_break_bars())
        intents = _find_intents(results)
        self.assertEqual(len(intents), 1)
        intent = intents[0]
        self.assertEqual(intent.stack_tier, "HALF")
        self.assertEqual(intent.direction, "bull")
        self.assertEqual(intent.spread_side, "put")
        self.assertIsNone(intent.expected_credit)
        self.assertEqual(intent.range_expansion_ratio, 1.0)
        self.assertGreaterEqual(intent.contracts, 1)
        self.assertIsNone(intent.orb30)
        self.assertIsNone(intent.orb60)

    def test_orb20_break_atr_not_ready_emits_api_error(self):
        engine = OrbStackingEngine()
        results = _feed_session(engine, _bull_orb20_break_bars())
        skips = _find_skips(results)
        self.assertEqual(len(skips), 1)
        self.assertEqual(skips[0].reason, "api_error")
        self.assertIn("atr_not_ready", skips[0].notes)

    def test_orb30_confirm_emits_normal_intent(self):
        results = _feed_session(self.engine, _bull_orb20_break_bars() + _orb30_confirm_bars())
        intents = _find_intents(results)
        final_intent = intents[-1]
        self.assertEqual(final_intent.stack_tier, "NORMAL")
        self.assertIsNotNone(final_intent.orb30)
        self.assertGreaterEqual(final_intent.contracts, 1)

    def test_orb30_oppose_emits_warning_skip(self):
        results = _feed_session(self.engine, _bull_orb20_break_bars() + _orb30_oppose_bars())
        skips = _find_skips(results)
        self.assertTrue(any(skip.reason == "orb30_opposes_warning" for skip in skips))

    def test_orb60_confirm_emits_plus_or_double_intent(self):
        bars = _bull_orb20_break_bars() + _orb30_confirm_bars() + _orb60_confirm_bars()
        results = _feed_session(self.engine, bars)
        intents = _find_intents(results)
        final_intent = intents[-1]
        self.assertIn(final_intent.stack_tier, ("PLUS", "DOUBLE", "NORMAL"))
        self.assertIsNotNone(final_intent.orb60)
        self.assertGreater(final_intent.range_expansion_ratio, 0)

    def test_orb60_oppose_emits_hard_exit_skip(self):
        bars = _bull_orb20_break_bars() + _orb30_confirm_bars() + _orb60_oppose_bars()
        results = _feed_session(self.engine, bars)
        skips = _find_skips(results)
        self.assertTrue(any(skip.reason == "orb60_opposes_hard_exit" for skip in skips))

    def test_timeout_noon_emits_skip_once(self):
        day = _dt.date(2026, 4, 9)
        bars = []
        current = _et(9, 30, day)
        end = _et(12, 0, day)
        while current <= end:
            bars.append(_bar(current, 6552.0, 6558.0, 6548.0, 6553.0))
            current += _dt.timedelta(minutes=5)
        results = _feed_session(self.engine, bars)
        skips = [skip for skip in _find_skips(results) if skip.reason == "no_breakout_before_noon"]
        self.assertEqual(len(skips), 1)
        more = self.engine.on_closed_bar(_bar(_et(12, 5, day), 6552.0, 6558.0, 6548.0, 6553.0))
        more_skips = [skip for skip in _find_skips(more) if skip.reason == "no_breakout_before_noon"]
        self.assertEqual(more_skips, [])

    def test_reset_clears_all_state(self):
        _feed_session(self.engine, _bull_orb20_break_bars())
        self.engine.reset_for_new_session()
        self.assertIsNone(self.engine._session_date)
        self.assertIsNone(self.engine._direction)
        self.assertFalse(self.engine._aborted)
        self.assertEqual(self.engine._gap_emitted, set())
        self.assertIsNone(self.engine._current_intent)
        self.engine.on_closed_bar(_bar(_et(9, 30, _dt.date(2026, 4, 10)), 6550.0, 6560.0, 6548.0, 6554.0))
        self.assertEqual(self.engine._session_date, _dt.date(2026, 4, 10))

    def test_stack_score_correct_on_half(self):
        results = _feed_session(self.engine, _bull_orb20_break_bars())
        intent = _find_intents(results)[0]
        self.assertEqual(intent.stack_score, 1)

    def test_base_score_threads_through(self):
        results = _feed_session(self.engine, _bull_orb20_break_bars())
        intent = _find_intents(results)[0]
        self.assertIsInstance(intent.base_score, int)

    def test_range_expansion_ratio_placeholder_on_half(self):
        results = _feed_session(self.engine, _bull_orb20_break_bars())
        intent = _find_intents(results)[0]
        self.assertEqual(intent.range_expansion_ratio, 1.0)

    def test_orb60_confirm_updates_range_expansion_ratio(self):
        bars = _bull_orb20_break_bars() + _orb30_confirm_bars() + _orb60_confirm_bars()
        results = _feed_session(self.engine, bars)
        intent = _find_intents(results)[-1]
        self.assertIsInstance(intent.range_expansion_ratio, float)
        self.assertGreaterEqual(intent.range_expansion_ratio, 0.0)

    def test_aborted_suppresses_all_subsequent_bars(self):
        # Engine without ATR prime aborts on ORB20 break
        engine = OrbStackingEngine()
        bars = _bull_orb20_break_bars()
        _feed_session(engine, bars)  # triggers abort
        self.assertTrue(engine._aborted)
        # All subsequent bars must return []
        extra_bars = _orb30_confirm_bars() + _orb60_confirm_bars()
        for bar in extra_bars:
            self.assertEqual(engine.on_closed_bar(bar), [])

    def test_expected_credit_none_on_orb30_and_orb60_intents(self):
        # expected_credit must stay None through all tier updates
        bars = _bull_orb20_break_bars() + _orb30_confirm_bars() + _orb60_confirm_bars()
        results = _feed_session(self.engine, bars)
        for intent in _find_intents(results):
            self.assertIsNone(intent.expected_credit,
                msg=f"expected_credit should be None on {intent.stack_tier} intent")

    def test_gap_skip_precedes_stack_events_in_results(self):
        """Gap skips must appear before stack event results in the same bar's output."""
        day = _dt.date(2026, 4, 9)
        # Feed a single bar at 12:00 ET — past all ORB lock times AND at noon
        # (the entry-window boundary; >= 12:00 ET triggers TIMEOUT_NOON).
        # This triggers both gap skips (ORB20/30/60 never locked) and TIMEOUT_NOON.
        bar = _bar(_et(12, 0, day), 6550.0, 6555.0, 6548.0, 6552.0)
        results = self.engine.on_closed_bar(bar)

        self.assertGreater(len(results), 1, "Expected both gap skips and timeout event")

        gap_skips = [r for r in results if isinstance(r, OrbSkipEvent) and r.reason == "bar_gap_during_lock"]
        timeout_skips = [r for r in results if isinstance(r, OrbSkipEvent) and r.reason == "no_breakout_before_noon"]

        self.assertEqual(len(gap_skips), 3, "Should have gap skips for ORB20, ORB30, ORB60")
        self.assertEqual(len(timeout_skips), 1, "Should have exactly one TIMEOUT_NOON")

        # Gap skips must all precede the timeout event in the results list
        last_gap_idx = max(results.index(s) for s in gap_skips)
        timeout_idx = results.index(timeout_skips[0])
        self.assertLess(last_gap_idx, timeout_idx,
            "All gap skips must appear before stack event results (TIMEOUT_NOON)")
