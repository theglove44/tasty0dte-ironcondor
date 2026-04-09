import unittest
from datetime import date

from orb_stacking.calendar_overlay import calendar_score


class TestCalendarScoreSingleEvents(unittest.TestCase):

    def test_fomc_wednesday_2026(self):
        """2026-01-28 is FOMC → (+1, ['FOMC'])."""
        score, labels = calendar_score(date(2026, 1, 28))
        self.assertEqual(score, 1)
        self.assertEqual(labels, ["FOMC"])

    def test_fomc_wednesday_2025(self):
        """2025-03-19 is FOMC → (+1, ['FOMC'])."""
        score, labels = calendar_score(date(2025, 3, 19))
        self.assertEqual(score, 1)
        self.assertEqual(labels, ["FOMC"])

    def test_quarter_end_march_2026(self):
        """2026-03-31 (Tue) is last weekday of Q1 → (+1, ['quarter_end'])."""
        score, labels = calendar_score(date(2026, 3, 31))
        self.assertEqual(score, 1)
        self.assertIn("quarter_end", labels)

    def test_quarter_end_june_2026(self):
        """2026-06-30 (Tue) is last weekday of Q2 → (+1, ['quarter_end'])."""
        score, labels = calendar_score(date(2026, 6, 30))
        self.assertEqual(score, 1)
        self.assertIn("quarter_end", labels)

    def test_last_friday_non_opex(self):
        """2026-01-30 (Fri) is last Friday of Jan, not OpEx (Jan 16 is OpEx).
        → (+1, ['last_friday'])."""
        score, labels = calendar_score(date(2026, 1, 30))
        self.assertEqual(score, 1)
        self.assertEqual(labels, ["last_friday"])

    def test_triple_witching_2026_march(self):
        """2026-03-20 is triple-witching. Score=-2, no 'opex' double-count."""
        score, labels = calendar_score(date(2026, 3, 20))
        self.assertEqual(score, -2)
        self.assertIn("triple_witching", labels)
        self.assertNotIn("opex", labels)

    def test_triple_witching_2026_june(self):
        """2026-06-19 is triple-witching. Score=-2."""
        score, labels = calendar_score(date(2026, 6, 19))
        self.assertEqual(score, -2)
        self.assertIn("triple_witching", labels)
        self.assertNotIn("opex", labels)

    def test_opex_non_witching_january(self):
        """2026-01-16 (3rd Fri of Jan, not witching month) → (-1, ['opex'])."""
        score, labels = calendar_score(date(2026, 1, 16))
        self.assertEqual(score, -1)
        self.assertEqual(labels, ["opex"])

    def test_opex_non_witching_april(self):
        """2026-04-17 (3rd Fri of Apr, not witching month) → (-1, ['opex'])."""
        score, labels = calendar_score(date(2026, 4, 17))
        self.assertEqual(score, -1)
        self.assertEqual(labels, ["opex"])

    def test_plain_day(self):
        """2026-04-01 (Wed) has no events → (0, [])."""
        score, labels = calendar_score(date(2026, 4, 1))
        self.assertEqual(score, 0)
        self.assertEqual(labels, [])

    def test_plain_monday(self):
        """2026-04-06 (Mon) has no events → (0, [])."""
        score, labels = calendar_score(date(2026, 4, 6))
        self.assertEqual(score, 0)
        self.assertEqual(labels, [])


class TestCalendarScoreStacking(unittest.TestCase):

    def test_quarter_end_plus_last_friday_stacks(self):
        """2027-12-31 (Fri) is last weekday of Q4 AND last Friday of Dec 2027.
        Dec 2027 Fridays: 3,10,17,24,31. 3rd=17 (triple-witching). 31 is last and NOT OpEx.
        Score = +1 (quarter_end) + +1 (last_friday) = +2."""
        score, labels = calendar_score(date(2027, 12, 31))
        self.assertEqual(score, 2)
        self.assertIn("quarter_end", labels)
        self.assertIn("last_friday", labels)
        self.assertNotIn("opex", labels)
        self.assertNotIn("triple_witching", labels)

    def test_clamp_cannot_exceed_plus_two(self):
        """Score is always <= +2."""
        score, _ = calendar_score(date(2027, 12, 31))
        self.assertLessEqual(score, 2)

    def test_clamp_cannot_go_below_minus_two(self):
        """Score is always >= -2."""
        score, _ = calendar_score(date(2026, 3, 20))
        self.assertGreaterEqual(score, -2)


class TestCalendarScoreInvariants(unittest.TestCase):

    def test_last_friday_never_equals_third_friday(self):
        """Invariant: every month has >= 4 Fridays, so the 3rd Friday can
        never be the last Friday. Verify across all 2025-2027 OpEx dates."""
        import calendar as _cal
        from orb_stacking.calendar_overlay import _OPEX_FRIDAYS
        for opex in sorted(_OPEX_FRIDAYS):
            last_day = _cal.monthrange(opex.year, opex.month)[1]
            last_fri_day = last_day
            while date(opex.year, opex.month, last_fri_day).weekday() != 4:
                last_fri_day -= 1
            self.assertNotEqual(
                opex.day, last_fri_day,
                f"3rd Friday {opex} coincides with last Friday — invariant broken",
            )

    def test_triple_witching_never_last_friday_of_month(self):
        """Invariant: 3rd Friday of witching months is never the last Friday."""
        import calendar as _cal
        from orb_stacking.calendar_overlay import _TRIPLE_WITCHING_FRIDAYS
        for tw in sorted(_TRIPLE_WITCHING_FRIDAYS):
            last_day = _cal.monthrange(tw.year, tw.month)[1]
            last_fri_day = last_day
            while date(tw.year, tw.month, last_fri_day).weekday() != 4:
                last_fri_day -= 1
            self.assertNotEqual(tw.day, last_fri_day)


class TestCalendar2027Coverage(unittest.TestCase):

    def test_2027_triple_witching_populated(self):
        """2027-03-19 is triple-witching. Score=-2."""
        score, labels = calendar_score(date(2027, 3, 19))
        self.assertEqual(score, -2)
        self.assertIn("triple_witching", labels)

    def test_2027_opex_populated(self):
        """2027-04-16 (3rd Fri Apr 2027) is OpEx, not witching → (-1, ['opex'])."""
        score, labels = calendar_score(date(2027, 4, 16))
        self.assertEqual(score, -1)
        self.assertEqual(labels, ["opex"])

    def test_2027_fomc_populated(self):
        """2027-01-27 (Wed) is a 2027 FOMC date → (+1, ['FOMC'])."""
        score, labels = calendar_score(date(2027, 1, 27))
        self.assertEqual(score, 1)
        self.assertEqual(labels, ["FOMC"])

    def test_2027_non_fomc_wednesday_plain(self):
        """2027-02-03 (Wed) is not an FOMC date → (0, [])."""
        score, labels = calendar_score(date(2027, 2, 3))
        self.assertEqual(score, 0)
        self.assertEqual(labels, [])


class TestCalendarPackageIsolation(unittest.TestCase):

    def test_no_live_bot_imports(self):
        """Importing calendar_overlay must not pull in live-bot modules."""
        import sys
        mods_before = set(sys.modules.keys())
        from orb_stacking.calendar_overlay import calendar_score as _cs  # noqa: F401
        mods_after = set(sys.modules.keys())
        newly_imported = mods_after - mods_before
        forbidden = ("tastytrade", "dxlink", "broker", "sdk_", "live_")
        for m in newly_imported:
            for bad in forbidden:
                self.assertNotIn(bad, m.lower())


if __name__ == "__main__":
    unittest.main()
