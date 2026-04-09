"""Tests for Breakout detection (Slice 3).

All synthetic bars are constructed on 2025-06-03 (a summer session,
so ET is UTC-4). The helper _bar() takes ET hh:mm and builds an
ET-aware bar dict (bar["start"] is ET-localized, as bar_fetcher.py emits).
"""
import unittest
from datetime import datetime, timedelta
import pytz

from orb_stacking.orb_levels import OrbBuilder, OrbLevels
from orb_stacking.breakout import Breakout, BreakoutDetector, immediate_breakout


ET = pytz.timezone("America/New_York")
SESSION_DATE = datetime(2025, 6, 3).date()


def _bar(et_hhmm: str, o: float, h: float, l: float, c: float) -> dict:
    hh, mm = map(int, et_hhmm.split(":"))
    naive = datetime(SESSION_DATE.year, SESSION_DATE.month, SESSION_DATE.day, hh, mm)
    start_et = ET.localize(naive)
    epoch_ms = int(start_et.timestamp() * 1000)
    return {"time": epoch_ms, "start": start_et, "open": o, "high": h, "low": l, "close": c}


def _make_orb20() -> OrbLevels:
    b = OrbBuilder()
    bars = [
        _bar("09:30", 100, 102, 99, 101),
        _bar("09:35", 101, 103, 100, 102),
        _bar("09:40", 102, 104, 101, 103),
        _bar("09:45", 103, 105, 102, 104),
    ]
    for bar in bars:
        b.update(bar)
    return b.locked("ORB20")


class TestBreakoutDetector(unittest.TestCase):

    def test_constructor_rejects_none(self):
        with self.assertRaises(ValueError):
            BreakoutDetector(None)

    def test_constructor_accepts_locked_orb(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo)
        self.assertEqual(bo.direction, "bull")

    def test_bull_breakout_on_lock_bar(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo = detector.check(_bar("09:45", 103, 106, 102, 106))
        self.assertIsNotNone(bo)
        self.assertEqual(bo.direction, "bull")
        self.assertEqual(bo.bars_since_lock, 0)
        self.assertEqual(bo.timestamp, orb.locked_at)

    def test_bear_breakout_on_lock_bar(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo = detector.check(_bar("09:45", 103, 98, 98, 98))
        self.assertIsNotNone(bo)
        self.assertEqual(bo.direction, "bear")
        self.assertEqual(bo.bars_since_lock, 0)

    def test_equal_high_is_not_breakout(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:50", 103, 105, 102, 105))
        self.assertIsNone(bo1)
        bo2 = detector.check(_bar("09:55", 103, 106, 102, 106))
        self.assertIsNotNone(bo2)
        self.assertEqual(bo2.direction, "bull")

    def test_equal_low_is_not_breakout(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:50", 103, 104, 99, 99))
        self.assertIsNone(bo1)
        bo2 = detector.check(_bar("09:55", 103, 104, 98, 98))
        self.assertIsNotNone(bo2)
        self.assertEqual(bo2.direction, "bear")

    def test_inside_range_returns_none(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:50", 101, 104, 100, 103))
        self.assertIsNone(bo1)
        bo2 = detector.check(_bar("09:55", 101, 104, 100, 102))
        self.assertIsNone(bo2)
        bo3 = detector.check(_bar("10:00", 101, 104, 100, 101))
        self.assertIsNone(bo3)

    def test_bars_since_lock_counts_one(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        detector.check(_bar("09:45", 103, 104, 102, 103))
        bo = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo)
        self.assertEqual(bo.bars_since_lock, 1)
        self.assertTrue(immediate_breakout(bo))

    def test_bars_since_lock_counts_five(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        detector.check(_bar("09:45", 103, 104, 102, 103))
        detector.check(_bar("09:50", 103, 104, 102, 103))
        detector.check(_bar("09:55", 103, 104, 102, 103))
        detector.check(_bar("10:00", 103, 104, 102, 103))
        detector.check(_bar("10:05", 103, 104, 102, 103))
        bo = detector.check(_bar("10:10", 103, 106, 102, 106))
        self.assertIsNotNone(bo)
        self.assertEqual(bo.bars_since_lock, 5)
        self.assertFalse(immediate_breakout(bo))

    def test_timestamp_equals_close_time(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo = detector.check(_bar("09:50", 103, 106, 102, 106))
        UTC = pytz.UTC
        expected_ts = bo.bar["start"].astimezone(pytz.UTC) + timedelta(minutes=5)
        self.assertEqual(bo.timestamp, expected_ts)
        self.assertEqual(bo.timestamp.tzinfo, pytz.UTC)

    def test_immediate_breakout_boundary_true_at_one(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        detector.check(_bar("09:45", 103, 104, 102, 103))
        bo = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertTrue(immediate_breakout(bo))

    def test_immediate_breakout_boundary_false_at_two(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        detector.check(_bar("09:45", 103, 104, 102, 103))
        detector.check(_bar("09:50", 103, 104, 102, 103))
        bo = detector.check(_bar("09:55", 103, 106, 102, 106))
        self.assertFalse(immediate_breakout(bo))

    def test_immediate_breakout_true_at_zero(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo = detector.check(_bar("09:45", 103, 106, 102, 106))
        self.assertTrue(immediate_breakout(bo))

    def test_one_shot_second_bull_bar_returns_none(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo1)
        bo2 = detector.check(_bar("09:55", 103, 110, 102, 110))
        self.assertIsNone(bo2)

    def test_one_shot_reversal_is_ignored(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo1)
        self.assertEqual(bo1.direction, "bull")
        bo2 = detector.check(_bar("09:55", 103, 104, 90, 90))
        self.assertIsNone(bo2)

    def test_one_shot_many_bars_after_fire(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo1)
        for hh, mm, c in [
            (9, 55, 106), (10, 0, 110), (10, 5, 101), (10, 10, 98),
            (10, 15, 102), (10, 20, 107), (10, 25, 95), (10, 30, 103),
            (10, 35, 108), (10, 40, 100),
        ]:
            bo = detector.check(_bar(f"{hh:02d}:{mm:02d}", 103, 110, 98, c))
            self.assertIsNone(bo)

    def test_pre_lock_bar_silently_ignored(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        bo1 = detector.check(_bar("09:30", 100, 999, 1, 999))
        self.assertIsNone(bo1)
        bo2 = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo2)
        self.assertEqual(bo2.direction, "bull")

    def test_cross_session_bar_silently_ignored(self):
        orb = _make_orb20()
        detector = BreakoutDetector(orb)
        # Bar from the next day — well past lock, would be a breakout by price
        from datetime import date
        from datetime import timedelta as td
        next_day = SESSION_DATE + td(days=1)
        naive = datetime(next_day.year, next_day.month, next_day.day, 9, 50)
        next_day_bar = {
            "time": 0,
            "start": ET.localize(naive),
            "open": 103, "high": 110, "low": 102, "close": 110,
        }
        bo = detector.check(next_day_bar)
        self.assertIsNone(bo)
        # Detector must still be primed — same-session bar still fires
        bo2 = detector.check(_bar("09:50", 103, 106, 102, 106))
        self.assertIsNotNone(bo2)

    def test_imports_are_minimal(self):
        import orb_stacking.breakout as breakout_module
        with open(breakout_module.__file__, 'r') as f:
            source = f.read()
        forbidden = [
            "from orb_stacking.indicators",
            "from orb_stacking.stacking",
            "from orb_stacking.grader",
            "from orb_stacking.bar_fetcher",
        ]
        for substr in forbidden:
            self.assertNotIn(substr, source)


if __name__ == "__main__":
    unittest.main()
