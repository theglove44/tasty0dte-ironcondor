import unittest
from datetime import datetime, time
import pytz

from orb_stacking.time_utils import (
    to_et, to_uk, to_utc,
    lock_times_et,
    is_lock_bar,
    entry_window_closed,
    UK_TZ, ET_TZ, UTC_TZ,
)


class TestConversions(unittest.TestCase):
    """Test idempotent timezone conversions."""

    def test_to_et_from_utc(self):
        """Convert UTC to ET."""
        # 2026-01-15 14:45 UTC = 09:45 EST (UTC-5 in January)
        utc_dt = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        et_dt = to_et(utc_dt)
        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 45)

    def test_to_et_from_uk(self):
        """Convert UK to ET (winter, both on standard time)."""
        # 2026-01-15 14:45 GMT (UK winter) = 09:45 EST
        uk_dt = UK_TZ.localize(datetime(2026, 1, 15, 14, 45))
        et_dt = to_et(uk_dt)
        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 45)

    def test_to_et_idempotent(self):
        """Calling to_et twice returns same result."""
        utc_dt = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        et1 = to_et(utc_dt)
        et2 = to_et(et1)
        self.assertEqual(et1, et2)

    def test_to_uk_from_utc(self):
        """Convert UTC to UK."""
        # 2026-01-15 14:45 UTC = 14:45 GMT
        utc_dt = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        uk_dt = to_uk(utc_dt)
        self.assertEqual(uk_dt.hour, 14)
        self.assertEqual(uk_dt.minute, 45)

    def test_to_uk_idempotent(self):
        """Calling to_uk twice returns same result."""
        utc_dt = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        uk1 = to_uk(utc_dt)
        uk2 = to_uk(uk1)
        self.assertEqual(uk1, uk2)

    def test_to_utc_from_et(self):
        """Convert ET to UTC."""
        # 2026-01-15 09:45 EST = 14:45 UTC
        et_dt = ET_TZ.localize(datetime(2026, 1, 15, 9, 45))
        utc_dt = to_utc(et_dt)
        self.assertEqual(utc_dt.hour, 14)
        self.assertEqual(utc_dt.minute, 45)

    def test_to_utc_idempotent(self):
        """Calling to_utc twice returns same result."""
        et_dt = datetime(2026, 1, 15, 9, 45, tzinfo=ET_TZ)
        utc1 = to_utc(et_dt)
        utc2 = to_utc(utc1)
        self.assertEqual(utc1, utc2)

    def test_naive_input_treated_as_utc(self):
        """Naive datetime assumed to be UTC."""
        naive_dt = datetime(2026, 1, 15, 14, 45)
        et_dt = to_et(naive_dt)
        self.assertEqual(et_dt.hour, 9)
        self.assertEqual(et_dt.minute, 45)

    def test_round_trip_utc_to_et_back(self):
        """UTC -> ET -> UTC round trip."""
        original = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        intermediate = to_et(original)
        result = to_utc(intermediate)
        self.assertEqual(original, result)


class TestDSTBoundaries(unittest.TestCase):
    """Test DST transitions."""

    def test_us_dst_spring_forward_2026(self):
        """US DST spring forward: 2026-03-08 02:00 EST becomes 03:00 EDT.

        2026-03-08 06:59 UTC = 01:59 EST (before transition)
        2026-03-08 07:00 UTC = 03:00 EDT (after transition, 2:00 EST is skipped)
        """
        # Just before spring forward (2026-03-08 01:59 EST)
        before = datetime(2026, 3, 8, 6, 59, tzinfo=UTC_TZ)
        before_et = to_et(before)
        self.assertEqual(before_et.hour, 1)  # 01:59 EST

        # Just after spring forward (2026-03-08 03:00 EDT - 2:00 EST is skipped)
        after = datetime(2026, 3, 8, 7, 0, tzinfo=UTC_TZ)
        after_et = to_et(after)
        self.assertEqual(after_et.hour, 3)  # 03:00 EDT (spring forward happened)

        # Much after spring forward
        after_clear = datetime(2026, 3, 8, 8, 0, tzinfo=UTC_TZ)
        after_clear_et = to_et(after_clear)
        self.assertEqual(after_clear_et.hour, 4)  # 04:00 EDT

    def test_us_dst_fall_back_2026(self):
        """US DST fall back: 2026-11-01 02:00 EDT becomes 01:00 EST.

        There's a one-hour window where the same local time occurs twice.
        """
        # Before fall back
        before = datetime(2026, 11, 1, 5, 59, tzinfo=UTC_TZ)
        before_et = to_et(before)
        self.assertEqual(before_et.hour, 1)  # 01:59 EDT

        # After fall back
        after = datetime(2026, 11, 1, 6, 1, tzinfo=UTC_TZ)
        after_et = to_et(after)
        self.assertEqual(after_et.hour, 1)  # 01:01 EST (same hour, different offset)

    def test_uk_bst_spring_forward_2026(self):
        """UK BST spring forward: 2026-03-29 01:00 GMT becomes 02:00 BST.

        2026-03-29 00:59 UTC = 00:59 GMT
        2026-03-29 01:00 UTC = 02:00 BST
        """
        before = datetime(2026, 3, 29, 0, 59, tzinfo=UTC_TZ)
        before_uk = to_uk(before)
        self.assertEqual(before_uk.hour, 0)
        self.assertEqual(before_uk.minute, 59)

        after = datetime(2026, 3, 29, 1, 0, tzinfo=UTC_TZ)
        after_uk = to_uk(after)
        self.assertEqual(after_uk.hour, 2)
        self.assertEqual(after_uk.minute, 0)

    def test_uk_bst_fall_back_2026(self):
        """UK BST fall back: 2026-10-25 02:00 BST becomes 01:00 GMT.

        2026-10-25 00:59 UTC = 01:59 BST
        2026-10-25 01:00 UTC = 01:00 GMT
        """
        before = datetime(2026, 10, 25, 0, 59, tzinfo=UTC_TZ)
        before_uk = to_uk(before)
        self.assertEqual(before_uk.hour, 1)
        self.assertEqual(before_uk.minute, 59)

        after = datetime(2026, 10, 25, 1, 0, tzinfo=UTC_TZ)
        after_uk = to_uk(after)
        self.assertEqual(after_uk.hour, 1)
        self.assertEqual(after_uk.minute, 0)


class TestLockTimesET(unittest.TestCase):
    """Test lock_times_et() function."""

    def test_returns_dict_with_three_keys(self):
        """lock_times_et returns exactly three ORB times."""
        times = lock_times_et()
        self.assertEqual(set(times.keys()), {"ORB20", "ORB30", "ORB60"})

    def test_exact_times(self):
        """Each ORB has the correct lock time."""
        times = lock_times_et()
        self.assertEqual(times["ORB20"], time(9, 50))
        self.assertEqual(times["ORB30"], time(10, 0))
        self.assertEqual(times["ORB60"], time(10, 30))


class TestIsLockBar(unittest.TestCase):
    """Test is_lock_bar() function."""

    def test_orb20_lock_bar_winter(self):
        """ORB20 lock bar starts at 09:45 ET (winter, EST)."""
        # 2026-01-15 14:45 UTC = 09:45 EST
        bar_start = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(bar_start, "ORB20"))

    def test_orb20_lock_bar_summer(self):
        """ORB20 lock bar starts at 09:45 EDT (summer, BST active on both sides)."""
        # 2026-06-15 13:45 UTC = 09:45 EDT
        bar_start = datetime(2026, 6, 15, 13, 45, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(bar_start, "ORB20"))

    def test_orb20_not_lock_bar_40(self):
        """09:40 ET is not ORB20 lock bar."""
        bar_start = datetime(2026, 1, 15, 14, 40, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB20"))

    def test_orb20_not_lock_bar_50(self):
        """09:50 ET is not ORB20 lock bar (that's when it closes, not starts)."""
        bar_start = datetime(2026, 1, 15, 14, 50, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB20"))

    def test_orb30_lock_bar(self):
        """ORB30 lock bar starts at 09:55 ET."""
        bar_start = datetime(2026, 1, 15, 14, 55, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(bar_start, "ORB30"))

    def test_orb30_not_lock_bar_50(self):
        """09:50 ET is not ORB30 lock bar."""
        bar_start = datetime(2026, 1, 15, 14, 50, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB30"))

    def test_orb30_not_lock_bar_00(self):
        """10:00 ET is not ORB30 lock bar (that's when it closes)."""
        bar_start = datetime(2026, 1, 15, 15, 0, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB30"))

    def test_orb60_lock_bar(self):
        """ORB60 lock bar starts at 10:25 ET."""
        bar_start = datetime(2026, 1, 15, 15, 25, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(bar_start, "ORB60"))

    def test_orb60_not_lock_bar_20(self):
        """10:20 ET is not ORB60 lock bar."""
        bar_start = datetime(2026, 1, 15, 15, 20, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB60"))

    def test_orb60_not_lock_bar_30(self):
        """10:30 ET is not ORB60 lock bar (that's when it closes)."""
        bar_start = datetime(2026, 1, 15, 15, 30, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB60"))

    def test_invalid_orb_name(self):
        """Invalid ORB name returns False."""
        bar_start = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        self.assertFalse(is_lock_bar(bar_start, "ORB999"))

    def test_is_lock_bar_ignores_seconds(self):
        """is_lock_bar only compares hour/minute, ignores seconds."""
        # 09:45:37 ET
        bar_start = datetime(2026, 1, 15, 14, 45, 37, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(bar_start, "ORB20"))

    def test_is_lock_bar_naive_input(self):
        """is_lock_bar handles naive (UTC) input."""
        bar_start = datetime(2026, 1, 15, 14, 45)  # naive, treated as UTC
        self.assertTrue(is_lock_bar(bar_start, "ORB20"))


class TestEntryWindowClosed(unittest.TestCase):
    """Test entry_window_closed() function."""

    def test_11_59_et_window_open(self):
        """11:59 ET is still within entry window (window closes at 12:00)."""
        # 2026-01-15 16:59 UTC = 11:59 EST
        dt = datetime(2026, 1, 15, 16, 59, tzinfo=UTC_TZ)
        self.assertFalse(entry_window_closed(dt))

    def test_12_00_et_window_closed(self):
        """12:00 ET is the exact cutoff — window is closed."""
        # 2026-01-15 17:00 UTC = 12:00 EST
        dt = datetime(2026, 1, 15, 17, 0, tzinfo=UTC_TZ)
        self.assertTrue(entry_window_closed(dt))

    def test_12_01_et_window_closed(self):
        """12:01 ET is after cutoff — window is closed."""
        # 2026-01-15 17:01 UTC = 12:01 EST
        dt = datetime(2026, 1, 15, 17, 1, tzinfo=UTC_TZ)
        self.assertTrue(entry_window_closed(dt))

    def test_09_30_et_window_open(self):
        """09:30 ET (market open) is within entry window."""
        # 2026-01-15 14:30 UTC = 09:30 EST
        dt = datetime(2026, 1, 15, 14, 30, tzinfo=UTC_TZ)
        self.assertFalse(entry_window_closed(dt))

    def test_summer_dst_boundary(self):
        """entry_window_closed works correctly during DST."""
        # 2026-06-15 16:00 UTC = 12:00 EDT
        dt = datetime(2026, 6, 15, 16, 0, tzinfo=UTC_TZ)
        self.assertTrue(entry_window_closed(dt))

        # 2026-06-15 15:59 UTC = 11:59 EDT
        dt_before = datetime(2026, 6, 15, 15, 59, tzinfo=UTC_TZ)
        self.assertFalse(entry_window_closed(dt_before))

    def test_ignores_seconds(self):
        """entry_window_closed only checks hour/minute."""
        # 12:00:37 ET
        dt = datetime(2026, 1, 15, 17, 0, 37, tzinfo=UTC_TZ)
        self.assertTrue(entry_window_closed(dt))

    def test_naive_input(self):
        """entry_window_closed handles naive (UTC) input."""
        dt = datetime(2026, 1, 15, 17, 0)  # naive, treated as UTC
        self.assertTrue(entry_window_closed(dt))


class TestComposedRoundTrip(unittest.TestCase):
    """Test combining timezone conversions with lock detection."""

    def test_orb20_lock_bar_round_trip(self):
        """Take a UTC datetime for ORB20 lock bar, round-trip through is_lock_bar."""
        # 2026-01-15 14:45 UTC = 09:45 EST (ORB20 lock bar start)
        utc_dt = datetime(2026, 1, 15, 14, 45, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(utc_dt, "ORB20"))

    def test_orb20_lock_bar_bst_day(self):
        """Same test on a BST day (summer)."""
        # 2026-06-15 13:45 UTC = 09:45 EDT (ORB20 lock bar start)
        utc_dt = datetime(2026, 6, 15, 13, 45, tzinfo=UTC_TZ)
        self.assertTrue(is_lock_bar(utc_dt, "ORB20"))


if __name__ == '__main__':
    unittest.main()
