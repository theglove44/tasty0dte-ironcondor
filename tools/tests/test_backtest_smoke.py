import unittest
from datetime import date, datetime, timedelta, timezone

import pytz

from orb_stacking.engine import OrbStackingEngine
from tools.backtest_orb_stacking import Bar


class TestTimestampParsing(unittest.TestCase):
    def test_winter_gmt(self):
        from tools.backtest_orb_stacking import _parse_timestamp

        ts = _parse_timestamp("04/01/2010", "14:35")
        self.assertEqual(ts.hour, 14)
        self.assertEqual(ts.minute, 35)
        self.assertEqual(ts.tzinfo, pytz.UTC)

    def test_summer_bst(self):
        from tools.backtest_orb_stacking import _parse_timestamp

        ts = _parse_timestamp("15/07/2015", "14:35")
        self.assertEqual(ts.hour, 13)
        self.assertEqual(ts.minute, 35)


class TestDayFavorable(unittest.TestCase):
    def test_bull_up(self):
        from tools.backtest_orb_stacking import _day_favorable

        self.assertTrue(_day_favorable("bull", 5000.0, 5010.0))

    def test_bull_down(self):
        from tools.backtest_orb_stacking import _day_favorable

        self.assertFalse(_day_favorable("bull", 5000.0, 4990.0))

    def test_bear_down(self):
        from tools.backtest_orb_stacking import _day_favorable

        self.assertTrue(_day_favorable("bear", 5000.0, 4990.0))

    def test_none_direction(self):
        from tools.backtest_orb_stacking import _day_favorable

        self.assertIsNone(_day_favorable(None, 5000.0, 5010.0))


class TestSmokeBacktest(unittest.TestCase):
    def _make_session_bars(self, base_date_et, direction="bull"):
        import zoneinfo

        tz_et = zoneinfo.ZoneInfo("America/New_York")
        base = datetime(
            base_date_et.year, base_date_et.month, base_date_et.day, 9, 30, tzinfo=tz_et
        ).astimezone(timezone.utc)
        bars = []
        price = 5000.0
        for i in range(78):
            t = base + timedelta(minutes=5 * i)
            if direction == "bull":
                o, c = price, price + 2.0
            else:
                o, c = price, price - 2.0
            bars.append(Bar(start=t, open=o, high=c + 1, low=o - 1, close=c))
            price = c
        return bars

    def test_five_sessions_produce_results(self):
        from tools.backtest_orb_stacking import aggregate, run_session

        engine = OrbStackingEngine()
        results = []
        warmup = []
        for i in range(5):
            d = date(2024, 1, 8) + timedelta(days=i)
            bars = self._make_session_bars(d)
            result = run_session(engine, bars, warmup)
            results.append(result)
            warmup = bars
        self.assertEqual(len(results), 5)
        agg = aggregate(results)
        self.assertEqual(agg["total"], 5)
        self.assertIn("by_category", agg)

    def test_aggregate_structure(self):
        from tools.backtest_orb_stacking import SessionResult, aggregate

        result = SessionResult(
            session_date=date(2024, 1, 8),
            bar_count=5,
            session_open=5000.0,
            session_close=5010.0,
            direction=None,
            last_stack_tier="FLAT",
            closes_aligned_count=0,
            reached_orb20_break=False,
            orb30_confirmed=False,
            orb30_opposed=False,
            orb60_confirmed=False,
            orb60_opposed=False,
            no_breakout_before_noon=True,
            aborted=False,
            category="no_break_before_noon",
            day_fav=None,
        )
        agg = aggregate([result])
        self.assertEqual(agg["total"], 1)
        self.assertEqual(agg["plus_count"], 0)
