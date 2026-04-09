"""Tests for OrbBuilder / OrbLevels (Slice 2).

All synthetic bars are constructed in UTC on 2025-06-03 (a summer session,
so ET is UTC-4). The helper _bar() takes ET hh:mm and builds a UTC-aware
bar dict matching bar_fetcher.py's schema.
"""
import unittest
from datetime import datetime, timezone, timedelta

import pytz

from orb_stacking.orb_levels import OrbBuilder, OrbLevels, ORB_NAMES


ET = pytz.timezone("America/New_York")
SESSION_DATE = datetime(2025, 6, 3).date()


def _bar(et_hhmm: str, o: float, h: float, l: float, c: float) -> dict:
    """Build a bar whose START is et_hhmm ET on SESSION_DATE."""
    hh, mm = map(int, et_hhmm.split(":"))
    naive = datetime(SESSION_DATE.year, SESSION_DATE.month, SESSION_DATE.day, hh, mm)
    start_et = ET.localize(naive)
    epoch_ms = int(start_et.timestamp() * 1000)
    return {
        "time": epoch_ms,
        "start": start_et,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    }


def _feed(builder: OrbBuilder, bars: list[dict]) -> list[OrbLevels]:
    out = []
    for b in bars:
        out.extend(builder.update(b))
    return out


# ORB20 spans 09:30, 09:35, 09:40, 09:45 ET (lock bar = 09:45)
ORB20_BARS = [
    _bar("09:30", 100, 102, 99, 101),
    _bar("09:35", 101, 103, 100, 102),
    _bar("09:40", 102, 104, 101, 103),
    _bar("09:45", 103, 105, 102, 104),  # lock bar
]

# ORB30 extends ORB20 with 09:50, 09:55 ET
ORB30_EXTRA = [
    _bar("09:50", 104, 106, 103, 105),
    _bar("09:55", 105, 107, 104, 106),  # lock bar
]

# ORB60 extends ORB30 with 10:00..10:25 ET (6 more bars, 12 total)
ORB60_EXTRA = [
    _bar("10:00", 106, 108, 105, 107),
    _bar("10:05", 107, 109, 106, 108),
    _bar("10:10", 108, 110, 107, 109),
    _bar("10:15", 109, 111, 108, 110),
    _bar("10:20", 110, 112, 109, 111),
    _bar("10:25", 111, 113, 110, 112),  # lock bar
]


class TestOrb20Lock(unittest.TestCase):

    def test_orb20_locks_on_fourth_bar(self):
        b = OrbBuilder()
        locks = _feed(b, ORB20_BARS)
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0].name, "ORB20")

    def test_orb20_high_low_across_all_four_bars(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        orb20 = b.locked("ORB20")
        # Highs: 102,103,104,105 -> max 105; Lows: 99,100,101,102 -> min 99
        self.assertEqual(orb20.high, 105.0)
        self.assertEqual(orb20.low, 99.0)
        self.assertEqual(orb20.range, 6.0)
        self.assertEqual(orb20.midpoint, 102.0)
        self.assertEqual(orb20.close, 104.0)  # 09:45 bar's close

    def test_orb20_close_pct(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        orb20 = b.locked("ORB20")
        # (104 - 99) / 6 = 0.8333..
        self.assertAlmostEqual(orb20.close_pct, 5.0 / 6.0)

    def test_orb20_locked_at_is_close_moment(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        orb20 = b.locked("ORB20")
        # lock bar start 09:45 ET + 5min => 09:50 ET == 13:50 UTC in June
        expected = ET.localize(datetime(2025, 6, 3, 9, 50)).astimezone(timezone.utc)
        self.assertEqual(orb20.locked_at, expected)

    def test_orb20_not_locked_before_fourth_bar(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS[:3])
        self.assertIsNone(b.locked("ORB20"))
        self.assertFalse(b.all_locked())

    def test_adding_0950_bar_does_not_modify_orb20(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        snapshot = b.locked("ORB20")
        # 09:50 bar pushes new highs but must NOT mutate ORB20
        b.update(_bar("09:50", 104, 999, 103, 105))
        orb20_after = b.locked("ORB20")
        self.assertEqual(orb20_after.high, snapshot.high)
        self.assertEqual(orb20_after.low, snapshot.low)
        self.assertEqual(orb20_after.close, snapshot.close)


class TestOrb30Lock(unittest.TestCase):

    def test_orb30_requires_six_bars(self):
        b = OrbBuilder()
        locks = _feed(b, ORB20_BARS + ORB30_EXTRA)
        names = [lv.name for lv in locks]
        self.assertIn("ORB20", names)
        self.assertIn("ORB30", names)

    def test_orb30_mid_build_query_returns_none(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS + ORB30_EXTRA[:1])  # up to 09:50 only
        self.assertIsNone(b.locked("ORB30"))

    def test_orb30_high_low_span_six_bars(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS + ORB30_EXTRA)
        orb30 = b.locked("ORB30")
        # Highs peak at 107 (09:55 bar), Lows bottom at 99 (09:30 bar)
        self.assertEqual(orb30.high, 107.0)
        self.assertEqual(orb30.low, 99.0)
        self.assertEqual(orb30.close, 106.0)


class TestOrb60Lock(unittest.TestCase):

    def test_orb60_requires_twelve_bars(self):
        b = OrbBuilder()
        locks = _feed(b, ORB20_BARS + ORB30_EXTRA + ORB60_EXTRA)
        self.assertTrue(b.all_locked())
        self.assertEqual(len(locks), 3)

    def test_orb60_high_low_span_twelve_bars(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS + ORB30_EXTRA + ORB60_EXTRA)
        orb60 = b.locked("ORB60")
        self.assertEqual(orb60.high, 113.0)
        self.assertEqual(orb60.low, 99.0)
        self.assertEqual(orb60.close, 112.0)

    def test_bar_after_1025_does_not_reopen_orb60(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS + ORB30_EXTRA + ORB60_EXTRA)
        snapshot = b.locked("ORB60")
        b.update(_bar("10:30", 112, 9999, 111, 112))
        self.assertEqual(b.locked("ORB60").high, snapshot.high)
        self.assertEqual(b.locked("ORB60").range, snapshot.range)


class TestClosePctEdges(unittest.TestCase):

    def test_close_pct_none_when_range_zero(self):
        b = OrbBuilder()
        flat = [_bar(t, 100, 100, 100, 100) for t in ("09:30", "09:35", "09:40", "09:45")]
        _feed(b, flat)
        orb20 = b.locked("ORB20")
        self.assertEqual(orb20.range, 0.0)
        self.assertIsNone(orb20.close_pct)

    def test_close_at_exact_low(self):
        b = OrbBuilder()
        bars = [
            _bar("09:30", 100, 105, 95, 100),
            _bar("09:35", 100, 104, 96, 100),
            _bar("09:40", 100, 103, 97, 100),
            _bar("09:45", 100, 102, 95, 95),  # lock bar closes at 95 == overall low
        ]
        _feed(b, bars)
        self.assertAlmostEqual(b.locked("ORB20").close_pct, 0.0)

    def test_close_at_exact_high(self):
        b = OrbBuilder()
        bars = [
            _bar("09:30", 100, 102, 99, 100),
            _bar("09:35", 100, 103, 99, 100),
            _bar("09:40", 100, 104, 99, 100),
            _bar("09:45", 100, 105, 99, 105),  # lock bar closes at overall high
        ]
        _feed(b, bars)
        self.assertAlmostEqual(b.locked("ORB20").close_pct, 1.0)


class TestSessionBoundary(unittest.TestCase):

    def test_different_session_raises(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        # Bar on next session
        next_day = datetime(2025, 6, 4, 9, 30)
        start = ET.localize(next_day)
        bar = {
            "time": int(start.timestamp() * 1000),
            "start": start,
            "open": 100, "high": 101, "low": 99, "close": 100,
        }
        with self.assertRaises(ValueError):
            b.update(bar)

    def test_reset_for_new_session_clears_state(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        self.assertIsNotNone(b.locked("ORB20"))
        b.reset_for_new_session()
        self.assertIsNone(b.locked("ORB20"))
        self.assertFalse(b.all_locked())
        # Re-feeding the same session should work again
        _feed(b, ORB20_BARS)
        self.assertIsNotNone(b.locked("ORB20"))


class TestBarGapDuringLock(unittest.TestCase):
    """Contiguity contract from ROADMAP risks table.

    OrbBuilder must NOT lock an ORB off a partial bar set. Any gap in the
    5-min feed (missing bar, late start, feed drop) must skip the lock and
    record a reason for Slice 8's SkipEvent translation.
    """

    def test_late_start_single_bar_does_not_lock_orb20(self):
        b = OrbBuilder()
        # Feed ONLY the 09:45 lock bar — simulates DXLink dropping the open
        b.update(_bar("09:45", 103, 105, 102, 104))
        self.assertIsNone(b.locked("ORB20"))
        self.assertIn("bar_gap_during_lock", b.gap_reason("ORB20"))

    def test_missing_mid_window_bar_skips_orb20(self):
        b = OrbBuilder()
        # Skip the 09:35 bar — 3 bars instead of 4
        _feed(b, [
            _bar("09:30", 100, 102, 99, 101),
            _bar("09:40", 102, 104, 101, 103),
            _bar("09:45", 103, 105, 102, 104),
        ])
        self.assertIsNone(b.locked("ORB20"))
        self.assertIn("missing bars at ET 09:35", b.gap_reason("ORB20"))

    def test_missing_open_bar_skips_orb20(self):
        b = OrbBuilder()
        # Skip the 09:30 bar
        _feed(b, [
            _bar("09:35", 101, 103, 100, 102),
            _bar("09:40", 102, 104, 101, 103),
            _bar("09:45", 103, 105, 102, 104),
        ])
        self.assertIsNone(b.locked("ORB20"))
        self.assertIsNotNone(b.gap_reason("ORB20"))

    def test_orb20_gap_does_not_block_orb30_from_checking_gap(self):
        """Each ORB's gap is tracked independently."""
        b = OrbBuilder()
        # Only 09:35..09:55 -> 5 bars. ORB20 should skip (3 bars at lock),
        # ORB30 should also skip (5 bars instead of 6).
        _feed(b, [
            _bar("09:35", 101, 103, 100, 102),
            _bar("09:40", 102, 104, 101, 103),
            _bar("09:45", 103, 105, 102, 104),
            _bar("09:50", 104, 106, 103, 105),
            _bar("09:55", 105, 107, 104, 106),
        ])
        self.assertIsNone(b.locked("ORB20"))
        self.assertIsNone(b.locked("ORB30"))
        self.assertIsNotNone(b.gap_reason("ORB20"))
        self.assertIsNotNone(b.gap_reason("ORB30"))

    def test_gap_inside_orb60_only_skips_orb60(self):
        """A mid-ORB60 gap (after ORB30 locked cleanly) only affects ORB60."""
        b = OrbBuilder()
        # Clean through ORB30, then skip the 10:10 bar
        clean = ORB20_BARS + ORB30_EXTRA + [
            _bar("10:00", 106, 108, 105, 107),
            _bar("10:05", 107, 109, 106, 108),
            # 10:10 missing
            _bar("10:15", 109, 111, 108, 110),
            _bar("10:20", 110, 112, 109, 111),
            _bar("10:25", 111, 113, 110, 112),
        ]
        _feed(b, clean)
        self.assertIsNotNone(b.locked("ORB20"))
        self.assertIsNotNone(b.locked("ORB30"))
        self.assertIsNone(b.locked("ORB60"))
        self.assertIsNotNone(b.gap_reason("ORB60"))
        # ORB20/30 should have no gap reason
        self.assertIsNone(b.gap_reason("ORB20"))
        self.assertIsNone(b.gap_reason("ORB30"))

    def test_reset_clears_gap_reasons(self):
        b = OrbBuilder()
        b.update(_bar("09:45", 100, 101, 99, 100))  # triggers ORB20 gap
        self.assertIsNotNone(b.gap_reason("ORB20"))
        b.reset_for_new_session()
        self.assertIsNone(b.gap_reason("ORB20"))
        # Fresh clean feed should now lock cleanly
        _feed(b, ORB20_BARS)
        self.assertIsNotNone(b.locked("ORB20"))

    def test_happy_path_has_no_gap_reasons(self):
        b = OrbBuilder()
        _feed(b, ORB20_BARS + ORB30_EXTRA + ORB60_EXTRA)
        for name in ("ORB20", "ORB30", "ORB60"):
            self.assertIsNone(b.gap_reason(name))

    def test_duplicate_bar_delivery_does_not_mask_gap(self):
        """DXLink can redeliver a candle on reconnect or as a late correction.
        A duplicate must NOT double-count toward the contiguity check — if
        09:35 is missing, delivering 09:30 twice plus 09:40 plus 09:45 must
        still skip ORB20 (observed distinct = 3, expected = 4)."""
        b = OrbBuilder()
        _feed(b, [
            _bar("09:30", 100, 102, 99, 101),
            _bar("09:30", 100, 102, 99, 101),  # duplicate
            _bar("09:40", 102, 104, 101, 103),
            _bar("09:45", 103, 105, 102, 104),
        ])
        self.assertIsNone(b.locked("ORB20"))
        self.assertIn("missing bars at ET 09:35", b.gap_reason("ORB20"))

    def test_post_lock_redelivery_does_not_mutate_locked_orb(self):
        """Once an ORB has locked, its levels are frozen. A late candle
        correction for an already-locked timestamp must not mutate the
        locked OrbLevels (the dataclass is immutable after _build_level)."""
        b = OrbBuilder()
        _feed(b, ORB20_BARS)
        orb20 = b.locked("ORB20")
        self.assertIsNotNone(orb20)
        b.update(_bar("09:45", 103, 99999, 102, 104))
        self.assertEqual(b.locked("ORB20").high, orb20.high)

    def test_pre_lock_correction_updates_orb_levels(self):
        """If DXLink redelivers a corrected candle BEFORE the ORB locks,
        the latest version wins. bar_fetcher keeps the newest candle per
        timestamp, and OrbBuilder must match that semantics — otherwise
        stale OHLC from the first delivery poisons the locked ORB.

        Here the 09:30 bar is initially reported with high=102, then
        corrected to high=150 before the 09:45 lock bar arrives. ORB20's
        high must reflect the correction (150), not the stale 102.
        """
        b = OrbBuilder()
        _feed(b, [
            _bar("09:30", 100, 102, 99, 101),   # initial
            _bar("09:30", 100, 150, 99, 101),   # late correction, high pumped
            _bar("09:35", 101, 103, 100, 102),
            _bar("09:40", 102, 104, 101, 103),
            _bar("09:45", 103, 105, 102, 104),  # lock
        ])
        orb20 = b.locked("ORB20")
        self.assertIsNotNone(orb20)
        self.assertEqual(orb20.high, 150.0)  # reflects the correction
        self.assertEqual(orb20.low, 99.0)


class TestArrivalOrder(unittest.TestCase):
    """OrbBuilder accepts bars in any order. Contiguity at lock time is
    the sole correctness gate — a late-arriving bar that fills a gap is
    indistinguishable from an on-time bar."""

    def test_late_arrival_of_missing_bar_is_accepted(self):
        """09:30, 09:40, then 09:35 (network reorder) → all stored, ORB20
        locks cleanly on 09:45 with 4 bars."""
        b = OrbBuilder()
        b.update(ORB20_BARS[0])  # 09:30
        b.update(ORB20_BARS[2])  # 09:40
        b.update(ORB20_BARS[1])  # 09:35 — late arrival
        b.update(ORB20_BARS[3])  # 09:45 lock
        orb20 = b.locked("ORB20")
        self.assertIsNotNone(orb20)
        self.assertEqual(orb20.high, 105.0)  # full range across all 4 bars
        self.assertEqual(orb20.low, 99.0)

    def test_late_correction_for_seen_timestamp_is_allowed(self):
        """A redelivered candle for an already-stored start time must be
        accepted even if it arrives after newer bars — DXLink replays and
        exchange corrections behave this way."""
        b = OrbBuilder()
        _feed(b, [
            _bar("09:30", 100, 102, 99, 101),
            _bar("09:35", 101, 103, 100, 102),
        ])
        # Correct the 09:30 bar AFTER 09:35 has been seen.
        b.update(_bar("09:30", 100, 160, 99, 101))
        _feed(b, [
            _bar("09:40", 102, 104, 101, 103),
            _bar("09:45", 103, 105, 102, 104),
        ])
        orb20 = b.locked("ORB20")
        self.assertIsNotNone(orb20)
        self.assertEqual(orb20.high, 160.0)

    def test_bar_past_lock_start_before_lock_bar_marks_orb_gapped(self):
        """Once the engine sees a bar whose start is AFTER an unlocked
        ORB's lock-bar start, the ORB must be marked as gapped — we can
        no longer tell "reordered and will arrive" from "never will".
        Out-of-order past-the-lock is treated as a feed problem, not as
        a recoverable condition. ORB30 remains independent."""
        b = OrbBuilder()
        b.update(_bar("09:30", 100, 102, 99, 101))
        b.update(_bar("09:35", 101, 103, 100, 102))
        b.update(_bar("09:40", 102, 104, 101, 103))
        # 09:50 arrives before the 09:45 ORB20 lock bar — this crosses
        # ORB20's lock boundary, so ORB20 must be marked gapped.
        b.update(_bar("09:50", 104, 999, 103, 105))
        self.assertIsNone(b.locked("ORB20"))
        self.assertIn("missing bars at ET 09:45", b.gap_reason("ORB20"))
        # Later arrivals for 09:45 and 09:55 should not un-gap ORB20.
        b.update(_bar("09:45", 103, 105, 102, 104))
        b.update(_bar("09:55", 105, 107, 104, 106))
        self.assertIsNone(b.locked("ORB20"))
        # ORB30 locks independently — all 6 of its required bars are in
        # the store by the time 09:55 (its lock bar) arrives.
        orb30 = b.locked("ORB30")
        self.assertIsNotNone(orb30)
        self.assertEqual(orb30.high, 999.0)

    def test_missing_lock_bar_marks_orb_gapped(self):
        """Direct P1 case: the lock bar itself never arrives. Before this
        fix, ORB20 would sit in permanent `None` state with no gap reason
        because the skip branch only fired on the bar_tod == lock_start
        path. Now seeing any bar past 09:45 without 09:45 in the store
        produces a gap reason."""
        b = OrbBuilder()
        b.update(_bar("09:30", 100, 102, 99, 101))
        b.update(_bar("09:35", 101, 103, 100, 102))
        b.update(_bar("09:40", 102, 104, 101, 103))
        # 09:45 is dropped entirely by the feed
        b.update(_bar("09:50", 104, 106, 103, 105))
        self.assertIsNone(b.locked("ORB20"))
        reason = b.gap_reason("ORB20")
        self.assertIsNotNone(reason)
        self.assertIn("09:45", reason)

    def test_early_arriving_bar_does_not_mask_missing_bar(self):
        """If 09:50 arrives early, it must not fool ORB20's count check into
        accepting a window with 09:35 missing. Before the fix, the store
        had 4 bars {09:30, 09:40, 09:45, 09:50} and size==4 would have
        matched ORB20's expected count, hiding the missing 09:35."""
        b = OrbBuilder()
        b.update(_bar("09:30", 100, 102, 99, 101))
        # Skip 09:35
        b.update(_bar("09:40", 102, 104, 101, 103))
        b.update(_bar("09:50", 104, 999, 103, 105))  # early, bumps store to 3
        b.update(_bar("09:45", 103, 105, 102, 104))  # store reaches 4 total
        self.assertIsNone(b.locked("ORB20"))
        self.assertIn("missing bars at ET 09:35", b.gap_reason("ORB20"))

    def test_out_of_window_replay_after_orb60_lock_does_not_raise(self):
        """After ORB60 has locked, a redelivered out-of-window bar (e.g.
        10:30 replayed after 10:35) must be silently ignored — live
        sessions see reconnect replays long after the ORB window closes."""
        b = OrbBuilder()
        _feed(b, ORB20_BARS + ORB30_EXTRA + ORB60_EXTRA)
        self.assertTrue(b.all_locked())
        # Post-window bars + a replay of an earlier post-window bar
        b.update(_bar("10:30", 112, 113, 111, 112))
        b.update(_bar("10:35", 113, 114, 112, 113))
        # Replay of 10:30 after 10:35 — must not raise
        b.update(_bar("10:30", 112, 113, 111, 112))
        # Locked ORBs remain frozen
        self.assertEqual(b.locked("ORB60").high, 113.0)


class TestNoCoupling(unittest.TestCase):

    def test_module_imports_only_stdlib_and_time_utils(self):
        """Slice 2 DoD: orb_levels must depend only on stdlib + time_utils."""
        import ast
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "orb_levels.py"
        )
        with open(path) as f:
            tree = ast.parse(f.read())
        allowed_prefixes = ("orb_stacking.time_utils",)
        allowed_stdlib = {"dataclasses", "datetime", "typing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in allowed_stdlib:
                    continue
                if any(mod.startswith(p) for p in allowed_prefixes):
                    continue
                self.fail(f"Disallowed import: {mod}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in allowed_stdlib:
                        self.fail(f"Disallowed import: {alias.name}")


if __name__ == "__main__":
    unittest.main()
