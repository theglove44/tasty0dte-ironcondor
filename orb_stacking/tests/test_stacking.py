import inspect
import logging
import unittest
from datetime import date, datetime

import pytz

from orb_stacking.stacking import LOCK_TOLERANCE_MS, StackingEngine


ET = pytz.timezone("America/New_York")
UTC = pytz.UTC
SESSION_DATE = date(2025, 6, 3)


def _bar(et_hhmm, o, h, l, c):
    hh, mm = map(int, et_hhmm.split(":"))
    start_et = ET.localize(datetime(SESSION_DATE.year, SESSION_DATE.month, SESSION_DATE.day, hh, mm))
    return {
        "time": int(start_et.timestamp() * 1000),
        "start": start_et,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    }


def _bar_for(day, et_hhmm, o, h, l, c):
    hh, mm = map(int, et_hhmm.split(":"))
    start_et = ET.localize(datetime(day.year, day.month, day.day, hh, mm))
    return {
        "time": int(start_et.timestamp() * 1000),
        "start": start_et,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    }


def _standard_window():
    times = (
        "09:30",
        "09:35",
        "09:40",
        "09:45",
        "09:50",
        "09:55",
        "10:00",
        "10:05",
        "10:10",
        "10:15",
        "10:20",
        "10:25",
    )
    return [_bar(t, 103, 105, 100, 103) for t in times]


def _all_aligned_bull_window():
    bars = []
    for t in ("09:30", "09:35", "09:40"):
        bars.append(_bar(t, 103, 105, 100, 103))
    bars.append(_bar("09:45", 104.5, 105, 100, 104.5))
    bars.append(_bar("09:50", 103, 105, 100, 103))
    bars.append(_bar("09:55", 104.5, 105, 100, 104.5))
    for t in ("10:00", "10:05", "10:10", "10:15", "10:20"):
        bars.append(_bar(t, 103, 105, 100, 103))
    bars.append(_bar("10:25", 104.5, 105, 100, 104.5))
    return bars


def _partial_aligned_bull_window():
    bars = []
    for t in ("09:30", "09:35", "09:40"):
        bars.append(_bar(t, 103, 105, 100, 103))
    bars.append(_bar("09:45", 104.5, 105, 100, 104.5))
    bars.append(_bar("09:50", 103, 105, 100, 103))
    bars.append(_bar("09:55", 104.5, 105, 100, 104.5))
    for t in ("10:00", "10:05", "10:10", "10:15", "10:20", "10:25"):
        bars.append(_bar(t, 103, 105, 100, 103))
    return bars


def _all_aligned_bear_window():
    bars = []
    for t in ("09:30", "09:35", "09:40"):
        bars.append(_bar(t, 103, 105, 100, 103))
    bars.append(_bar("09:45", 100.5, 105, 100, 100.5))
    bars.append(_bar("09:50", 103, 105, 100, 103))
    bars.append(_bar("09:55", 100.5, 105, 100, 100.5))
    for t in ("10:00", "10:05", "10:10", "10:15", "10:20"):
        bars.append(_bar(t, 103, 105, 100, 103))
    bars.append(_bar("10:25", 100.5, 105, 100, 100.5))
    return bars


def _feed(engine, bars):
    last_events = []
    for bar in bars:
        last_events = engine.on_closed_bar(bar)
    return last_events


class TestStackingEngine(unittest.TestCase):
    def test_orb20_only_no_stacking(self):
        engine = StackingEngine()
        # Feed bars 09:30–09:45 to lock ORB20
        _feed(engine, [_bar(t, 103, 105, 100, 103) for t in ("09:30", "09:35", "09:40", "09:45")])

        # Feed 09:50 bull breakout
        events = engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        self.assertEqual([e.kind for e in events], ["ORB20_BREAK"])
        self.assertEqual(engine.current_tier, "HALF")

        # Feed 09:55 bar (ORB30 locks, in-range close → no confirm yet)
        engine.on_closed_bar(_bar("09:55", 103, 105, 100, 103))

        # Feed 10:00–10:20 bars
        _feed(engine, [_bar(t, 103, 105, 100, 103) for t in ("10:00", "10:05", "10:10", "10:15", "10:20")])

        # Feed 10:25 bar (ORB60 locks, in-range close)
        events = engine.on_closed_bar(_bar("10:25", 103, 105, 100, 103))
        self.assertIn("ORB60_NO_BREAKOUT", [e.kind for e in events])
        self.assertEqual(engine.current_tier, "HALF")

    def test_same_same_plus_no_align(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        self.assertEqual(engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))[0].kind, "ORB20_BREAK")
        self.assertEqual(engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))[0].kind, "ORB30_CONFIRM")
        self.assertEqual(engine.on_closed_bar(_bar("10:30", 106, 106, 102, 106))[0].kind, "ORB60_CONFIRM")
        self.assertEqual(engine.current_tier, "PLUS")
        self.assertEqual(engine._closes_aligned, 0)

    def test_same_same_all_3_aligned(self):
        engine = StackingEngine()
        _feed(engine, _all_aligned_bull_window())

        self.assertEqual(engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))[0].kind, "ORB20_BREAK")
        self.assertEqual(engine._closes_aligned, 1)
        self.assertEqual(engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))[0].kind, "ORB30_CONFIRM")
        self.assertEqual(engine._closes_aligned, 2)
        self.assertEqual(engine.on_closed_bar(_bar("10:30", 106, 106, 102, 106))[0].kind, "ORB60_CONFIRM")
        self.assertEqual(engine._closes_aligned, 3)
        self.assertEqual(engine.current_tier, "DOUBLE")

    def test_same_opp_orb60_exits(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))
        events = engine.on_closed_bar(_bar("10:30", 98, 104, 98, 98))
        self.assertEqual([e.kind for e in events], ["ORB60_OPPOSE"])
        self.assertEqual(engine.current_tier, "EXITED")

    def test_orb20_only_timeout_noon(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        events = engine.on_closed_bar(_bar("12:00", 103, 105, 100, 103))
        self.assertEqual([e.kind for e in events], ["TIMEOUT_NOON"])
        self.assertIsNone(events[0].direction)
        self.assertIsNone(events[0].orb)

    def test_same_orb30_oppose_warning(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        events = engine.on_closed_bar(_bar("10:00", 98, 104, 98, 98))
        self.assertEqual([e.kind for e in events], ["ORB30_OPPOSE"])
        self.assertEqual(engine.current_tier, "HALF")

        events = engine.on_closed_bar(_bar("10:30", 106, 106, 102, 106))
        self.assertEqual([e.kind for e in events], ["ORB60_CONFIRM"])
        self.assertEqual(engine.current_tier, "PLUS")

    def test_same_same_partial_align(self):
        engine = StackingEngine()
        _feed(engine, _partial_aligned_bull_window())

        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))
        events = engine.on_closed_bar(_bar("10:30", 106, 106, 102, 106))
        self.assertEqual([e.kind for e in events], ["ORB60_CONFIRM"])
        self.assertEqual(engine._closes_aligned, 2)
        self.assertEqual(engine.current_tier, "PLUS")

    def test_double_from_plus_requires_three_aligned(self):
        engine = StackingEngine()
        _feed(engine, _partial_aligned_bull_window())

        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:30", 106, 106, 102, 106))
        self.assertEqual(engine.current_tier, "PLUS")
        self.assertLess(engine._closes_aligned, 3)

    def test_tier_cannot_regress(self):
        engine = StackingEngine()
        engine._set_tier("HALF")
        engine._set_tier("FLAT")
        self.assertEqual(engine.current_tier, "HALF")
        engine._set_tier("NORMAL")
        engine._set_tier("HALF")
        self.assertEqual(engine.current_tier, "NORMAL")

    def test_stale_lock_bar_logged(self):
        engine = StackingEngine()
        _feed(engine, _standard_window()[:3])

        stale = _bar("09:45", 103, 105, 100, 103)
        stale["time"] += LOCK_TOLERANCE_MS + 2000
        with self.assertLogs("orb_stacking.stacking", level=logging.WARNING) as captured:
            engine.on_closed_bar(stale)
        self.assertTrue(any("STALE_LOCK_BAR" in msg for msg in captured.output))

    def test_orb30_oppose_does_not_exit(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        events = engine.on_closed_bar(_bar("10:00", 98, 104, 98, 98))
        self.assertEqual([e.kind for e in events], ["ORB30_OPPOSE"])
        self.assertNotEqual(engine.current_tier, "EXITED")
        self.assertEqual(engine.current_tier, "HALF")

    def test_orb60_no_breakout_fires_when_flat(self):
        engine = StackingEngine()
        events = _feed(engine, _standard_window())
        self.assertEqual([e.kind for e in events], ["ORB60_NO_BREAKOUT"])
        self.assertEqual(engine.current_tier, "FLAT")

    def test_session_reset_no_state_leak(self):
        engine = StackingEngine()
        _feed(engine, _all_aligned_bull_window())
        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:30", 106, 106, 102, 106))
        self.assertEqual(engine.current_tier, "DOUBLE")

        engine.reset_for_new_session()
        self.assertEqual(engine.current_tier, "FLAT")
        self.assertIsNone(engine.direction)
        self.assertEqual(engine._closes_aligned, 0)

        next_day = date(2025, 6, 4)

        def _bar2(et_hhmm, o, h, l, c):
            return _bar_for(next_day, et_hhmm, o, h, l, c)

        bars = [_bar2(t, 103, 105, 100, 103) for t in ("09:30", "09:35", "09:40", "09:45")]
        _feed(engine, bars)
        self.assertEqual(engine.current_tier, "FLAT")

    def test_close_alignment_boundary_bull(self):
        engine = StackingEngine()
        bars = [
            _bar("09:30", 103.995, 105, 100, 103.995),
            _bar("09:35", 103.995, 105, 100, 103.995),
            _bar("09:40", 103.995, 105, 100, 103.995),
            _bar("09:45", 103.995, 105, 100, 103.995),
        ]
        _feed(engine, bars)
        orb = engine._orb_builder.locked("ORB20")
        self.assertFalse(engine._is_close_aligned(orb, "bull"))

        engine.reset_for_new_session()
        bars = [
            _bar("09:30", 104.0, 105, 100, 104.0),
            _bar("09:35", 104.0, 105, 100, 104.0),
            _bar("09:40", 104.0, 105, 100, 104.0),
            _bar("09:45", 104.0, 105, 100, 104.0),
        ]
        _feed(engine, bars)
        orb = engine._orb_builder.locked("ORB20")
        self.assertTrue(engine._is_close_aligned(orb, "bull"))

    def test_close_alignment_boundary_bear(self):
        engine = StackingEngine()
        bars = [
            _bar("09:30", 101.005, 105, 100, 101.005),
            _bar("09:35", 101.005, 105, 100, 101.005),
            _bar("09:40", 101.005, 105, 100, 101.005),
            _bar("09:45", 101.005, 105, 100, 101.005),
        ]
        _feed(engine, bars)
        orb = engine._orb_builder.locked("ORB20")
        self.assertFalse(engine._is_close_aligned(orb, "bear"))

        engine.reset_for_new_session()
        bars = [
            _bar("09:30", 101.0, 105, 100, 101.0),
            _bar("09:35", 101.0, 105, 100, 101.0),
            _bar("09:40", 101.0, 105, 100, 101.0),
            _bar("09:45", 101.0, 105, 100, 101.0),
        ]
        _feed(engine, bars)
        orb = engine._orb_builder.locked("ORB20")
        self.assertTrue(engine._is_close_aligned(orb, "bear"))

    def test_zero_range_orb_close_pct_none_not_aligned(self):
        """When ORB20 range is zero (all bars same high/low), close_pct is None.
        _is_close_aligned must return False rather than raising."""
        engine = StackingEngine()
        # All 4 bars identical H=L=100: range=0 → close_pct=None
        bars = [_bar(t, 100, 100, 100, 100) for t in ("09:30", "09:35", "09:40", "09:45")]
        _feed(engine, bars)
        orb = engine._orb_builder.locked("ORB20")
        self.assertIsNone(orb.close_pct)
        self.assertFalse(engine._is_close_aligned(orb, "bull"))
        self.assertFalse(engine._is_close_aligned(orb, "bear"))

    def test_event_timestamp_is_utc(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())
        events = engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        self.assertEqual(events[0].timestamp.tzinfo, UTC)

    def test_state_snapshot_keys(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())
        events = engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        self.assertEqual(set(events[0].state_snapshot), {"stack_tier", "closes_aligned", "direction"})

    def test_current_tier_property(self):
        engine = StackingEngine()
        self.assertEqual(engine.current_tier, "FLAT")
        _feed(engine, _standard_window())
        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        self.assertEqual(engine.current_tier, "HALF")

    def test_direction_property(self):
        engine = StackingEngine()
        self.assertIsNone(engine.direction)
        _feed(engine, _standard_window())
        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        self.assertEqual(engine.direction, "bull")

    def test_bear_breakout_direction(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())
        events = engine.on_closed_bar(_bar("09:50", 98, 104, 98, 98))
        self.assertEqual([e.kind for e in events], ["ORB20_BREAK"])
        self.assertEqual(events[0].direction, "bear")
        self.assertEqual(engine.direction, "bear")

    def test_orb60_no_breakout_fires_when_orb20_broke_but_orb60_didnt(self):
        engine = StackingEngine()
        # Feed bars 09:30–09:45 to lock ORB20
        _feed(engine, [_bar(t, 103, 105, 100, 103) for t in ("09:30", "09:35", "09:40", "09:45")])

        # Feed 09:50 bull breakout
        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))

        # Feed 09:55 bar (ORB30 locks, in-range close → no confirm yet)
        engine.on_closed_bar(_bar("09:55", 103, 105, 100, 103))

        # Feed 10:00 bull bar (ORB30_CONFIRM)
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))

        # Feed 10:05–10:20 bars
        _feed(engine, [_bar(t, 103, 105, 100, 103) for t in ("10:05", "10:10", "10:15", "10:20")])

        # Feed 10:25 bar (ORB60 locks, in-range close)
        events = engine.on_closed_bar(_bar("10:25", 103, 105, 100, 103))
        self.assertIn("ORB60_NO_BREAKOUT", [e.kind for e in events])

    def test_no_double_fire_of_timeout(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        self.assertEqual([e.kind for e in engine.on_closed_bar(_bar("12:00", 103, 105, 100, 103))], ["TIMEOUT_NOON"])
        self.assertEqual(engine.on_closed_bar(_bar("12:05", 103, 105, 100, 103)), [])

    def test_exited_is_terminal(self):
        engine = StackingEngine()
        _feed(engine, _standard_window())

        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))
        engine.on_closed_bar(_bar("10:30", 98, 104, 98, 98))
        self.assertEqual(engine.current_tier, "EXITED")
        self.assertEqual(engine.on_closed_bar(_bar("10:35", 106, 106, 102, 106)), [])

    def test_bear_session_all_3_same(self):
        engine = StackingEngine()
        _feed(engine, _all_aligned_bear_window())

        self.assertEqual(engine.on_closed_bar(_bar("09:50", 98, 104, 98, 98))[0].kind, "ORB20_BREAK")
        self.assertEqual(engine.on_closed_bar(_bar("10:00", 98, 104, 98, 98))[0].kind, "ORB30_CONFIRM")
        self.assertEqual(engine.on_closed_bar(_bar("10:30", 98, 104, 98, 98))[0].kind, "ORB60_CONFIRM")
        self.assertEqual(engine.current_tier, "DOUBLE")
        self.assertEqual(engine.direction, "bear")

    def test_orb60_breakout_on_lock_bar_no_spurious_no_breakout(self):
        """When ORB60 locks and then breaks out on the same call, only ORB60_CONFIRM fires (not ORB60_NO_BREAKOUT).

        Regression test for Issue: on_closed_bar called _check_orb60_no_breakout BEFORE the detector loop,
        allowing both ORB60_NO_BREAKOUT and ORB60_CONFIRM to fire on the same bar.
        """
        engine = StackingEngine()
        # Feed bars 09:30–09:45 to lock ORB20
        _feed(engine, [_bar(t, 103, 105, 100, 103) for t in ("09:30", "09:35", "09:40", "09:45")])
        # ORB20 breaks at 09:50
        engine.on_closed_bar(_bar("09:50", 106, 106, 102, 106))
        # ORB30 locks at 09:55 (in-range close 103)
        engine.on_closed_bar(_bar("09:55", 103, 105, 100, 103))
        # ORB30 confirms at 10:00
        engine.on_closed_bar(_bar("10:00", 106, 106, 102, 106))
        # Feed 10:05-10:20 in-range
        _feed(engine, [_bar(t, 103, 105, 100, 103) for t in ("10:05", "10:10", "10:15", "10:20")])
        # ORB60 lock bar (10:25) has close in range (103)
        events = engine.on_closed_bar(_bar("10:25", 103, 105, 100, 103))
        kinds = [e.kind for e in events]
        # ORB60 locks but doesn't break out on lock bar, so ORB60_NO_BREAKOUT fires
        self.assertIn("ORB60_NO_BREAKOUT", kinds)
        self.assertNotIn("ORB60_CONFIRM", kinds)

        # Now feed a breakout bar after ORB60 is locked
        events = engine.on_closed_bar(_bar("10:30", 107, 107, 102, 107))
        kinds = [e.kind for e in events]
        # Only ORB60_CONFIRM should fire now (not ORB60_NO_BREAKOUT again)
        self.assertIn("ORB60_CONFIRM", kinds)
        self.assertNotIn("ORB60_NO_BREAKOUT", kinds)
        self.assertEqual(engine.current_tier, "PLUS")

    def test_imports_are_minimal(self):
        import orb_stacking.stacking as stacking_module

        source = inspect.getsource(stacking_module)
        expected_imports = [
            "import logging",
            "from dataclasses import dataclass",
            "from datetime import datetime, timedelta",
            "from typing import Optional",
            "from orb_stacking.orb_levels import OrbBuilder, OrbLevels, ORB_NAMES",
            "from orb_stacking.breakout import Breakout, BreakoutDetector",
            "from orb_stacking.time_utils import to_utc, entry_window_closed",
        ]
        for line in expected_imports:
            self.assertIn(line, source)

        forbidden = ["pytz", "unittest", "pytest", "orb_stacking.indicators", "bar_fetcher"]
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
