import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
import pytz
import builtins

from orb_stacking.bar_fetcher import (
    candle_to_bar,
    is_garbage_bar,
    clean_and_sort,
    UK_TZ,
    DEFAULT_INTERVAL,
    DEFAULT_LOOKBACK_DAYS,
    WARMUP_MIN_BARS,
    BarFetcher,
    Candle,
)


class MockCandle:
    """Simple mock Candle that looks like a Candle for testing."""
    def __init__(self, time_ms, o, h, l, c):
        self.time = time_ms
        self.open = o
        self.high = h
        self.low = l
        self.close = c


def _mock_candle(time_ms, o, h, l, c):
    """Build a mock Candle event with the given OHLC + timestamp."""
    return MockCandle(time_ms, o, h, l, c)


class TestCandleToBar(unittest.TestCase):
    def test_valid_candle(self):
        ts = 1712499000000  # 2024-04-07 13:30 UTC
        c = _mock_candle(ts, 100.5, 102.0, 99.5, 101.25)
        bar = candle_to_bar(c)
        self.assertIsNotNone(bar)
        self.assertEqual(bar['time'], ts)
        self.assertEqual(bar['open'], 100.5)
        self.assertEqual(bar['high'], 102.0)
        self.assertEqual(bar['low'], 99.5)
        self.assertEqual(bar['close'], 101.25)
        self.assertEqual(bar['start'].tzinfo.zone, UK_TZ.zone)

    def test_none_time_returns_none(self):
        self.assertIsNone(candle_to_bar(_mock_candle(None, 1, 2, 0.5, 1.5)))

    def test_none_open_returns_none(self):
        self.assertIsNone(candle_to_bar(_mock_candle(1, None, 2, 0.5, 1.5)))

    def test_none_high_returns_none(self):
        self.assertIsNone(candle_to_bar(_mock_candle(1, 1, None, 0.5, 1.5)))

    def test_none_low_returns_none(self):
        self.assertIsNone(candle_to_bar(_mock_candle(1, 1, 2, None, 1.5)))

    def test_none_close_returns_none(self):
        self.assertIsNone(candle_to_bar(_mock_candle(1, 1, 2, 0.5, None)))

    def test_floats_coerced(self):
        c = _mock_candle(1000, "100", "102", "99", "101")
        bar = candle_to_bar(c)
        self.assertIsInstance(bar['open'], float)
        self.assertEqual(bar['open'], 100.0)

    def test_start_is_utc_offset_aware(self):
        ts = 1712499000000
        c = _mock_candle(ts, 100, 100, 100, 100)
        bar = candle_to_bar(c)
        self.assertIsNotNone(bar['start'].tzinfo)


class TestIsGarbageBar(unittest.TestCase):
    def test_zero_open_is_garbage(self):
        self.assertTrue(is_garbage_bar(
            {'time': 1, 'open': 0, 'high': 1, 'low': 0, 'close': 1}))

    def test_zero_close_is_garbage(self):
        self.assertTrue(is_garbage_bar(
            {'time': 1, 'open': 1, 'high': 1, 'low': 0, 'close': 0}))

    def test_both_zero_is_garbage(self):
        self.assertTrue(is_garbage_bar(
            {'time': 1, 'open': 0, 'high': 0, 'low': 0, 'close': 0}))

    def test_normal_bar_is_clean(self):
        self.assertFalse(is_garbage_bar(
            {'time': 1, 'open': 100, 'high': 101, 'low': 99, 'close': 100.5}))

    def test_zero_low_is_clean(self):
        # Low can be 0 in theory; only O/C are checked
        self.assertFalse(is_garbage_bar(
            {'time': 1, 'open': 100, 'high': 101, 'low': 0, 'close': 100.5}))


class TestCleanAndSort(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(clean_and_sort({}), [])

    def test_sorted_by_time(self):
        bars = {
            3000: {'time': 3000, 'open': 3, 'high': 3, 'low': 3, 'close': 3},
            1000: {'time': 1000, 'open': 1, 'high': 1, 'low': 1, 'close': 1},
            2000: {'time': 2000, 'open': 2, 'high': 2, 'low': 2, 'close': 2},
        }
        result = clean_and_sort(bars)
        self.assertEqual([b['time'] for b in result], [1000, 2000, 3000])

    def test_dedup_already_handled_by_dict_keys(self):
        # dict can only hold one value per key — last write wins
        bars = {1000: {'time': 1000, 'open': 99, 'high': 99, 'low': 99, 'close': 99}}
        bars[1000] = {'time': 1000, 'open': 100, 'high': 100, 'low': 100, 'close': 100}
        result = clean_and_sort(bars)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['open'], 100)


class TestRealisticDxLinkOutput(unittest.TestCase):
    """Mirror the actual probe output: garbage Mar 28 sentinel + real bars."""

    def test_filters_garbage_keeps_real(self):
        # Simulate what the probe saw
        events = [
            _mock_candle(1711654512000, 0, 0, 0, 0),         # garbage Mar 28
            _mock_candle(1711805400000, 6403.37, 6410, 6370, 6373.9),  # real
            _mock_candle(1711807200000, 6374.03, 6385, 6374, 6382.32),
        ]
        by_time = {}
        for e in events:
            bar = candle_to_bar(e)
            if bar is None or is_garbage_bar(bar):
                continue
            by_time[bar['time']] = bar
        bars = clean_and_sort(by_time)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]['open'], 6403.37)
        self.assertEqual(bars[1]['open'], 6374.03)

    def test_dedup_late_event_for_same_bar(self):
        events = [
            _mock_candle(1711805400000, 6403.37, 6410, 6370, 6373.9),
            _mock_candle(1711805400000, 6403.37, 6411, 6369, 6374.5),  # update
        ]
        by_time = {}
        for e in events:
            bar = candle_to_bar(e)
            if bar is None or is_garbage_bar(bar):
                continue
            by_time[bar['time']] = bar
        self.assertEqual(len(by_time), 1)
        # Latest values won
        self.assertEqual(by_time[1711805400000]['high'], 6411)
        self.assertEqual(by_time[1711805400000]['close'], 6374.5)


class TestDefaultConstants(unittest.TestCase):
    def test_default_interval_is_5m(self):
        self.assertEqual(DEFAULT_INTERVAL, "5m")

    def test_default_lookback_days_is_2(self):
        self.assertEqual(DEFAULT_LOOKBACK_DAYS, 2)

    def test_warmup_min_bars_is_30(self):
        self.assertEqual(WARMUP_MIN_BARS, 30)

# Test compatibility layer for async tests
def test_async(coro):
    """Decorator to run async tests."""
    import asyncio
    def wrapper(self):
        return asyncio.run(coro(self))
    return wrapper


class TestFetchHistoryWithRetryAsync(unittest.TestCase):
    """Async tests for fetch_history_with_retry."""

    @test_async
    async def test_returns_larger_result(self):
        """If first fetch has < WARMUP_MIN_BARS, retry and return the larger result."""
        fetcher = BarFetcher(symbol="SPX", interval="5m", lookback_days=2)

        small_result = [
            {'time': i, 'start': datetime.now(pytz.UTC), 'open': 100, 'high': 101, 'low': 99, 'close': 100}
            for i in range(1, 6)
        ]
        large_result = [
            {'time': i, 'start': datetime.now(pytz.UTC), 'open': 100, 'high': 101, 'low': 99, 'close': 100}
            for i in range(1, 36)
        ]

        call_count = [0]

        async def mock_fetch(session):
            call_count[0] += 1
            if call_count[0] == 1:
                return small_result
            else:
                return large_result

        fetcher.fetch_history = mock_fetch
        session = MagicMock()

        result = await fetcher.fetch_history_with_retry(session)
        self.assertEqual(len(result), 35)
        self.assertEqual(call_count[0], 2)

    @test_async
    async def test_degraded_path_returns_available(self):
        """If both fetches return < WARMUP_MIN_BARS, return what we have + log warning."""
        fetcher = BarFetcher(symbol="SPX", interval="5m", lookback_days=2)

        both_small = [
            {'time': i, 'start': datetime.now(pytz.UTC), 'open': 100, 'high': 101, 'low': 99, 'close': 100}
            for i in range(1, 11)
        ]

        async def mock_fetch(session):
            return both_small

        fetcher.fetch_history = mock_fetch
        session = MagicMock()

        result = await fetcher.fetch_history_with_retry(session)
        self.assertEqual(len(result), 10)


class TestFetchDailyBars(unittest.IsolatedAsyncioTestCase):
    """Tests for fetch_daily_bars top-level async function."""

    def _setup_mock_streamer(self, mock_streamer_cls, candles):
        """Set up mock DXLinkStreamer that yields Candle-like mock objects."""
        mock_streamer = AsyncMock()
        mock_streamer.__aenter__.return_value = mock_streamer
        mock_streamer.__aexit__.return_value = None
        mock_streamer.subscribe_candle = AsyncMock(return_value=None)

        async def _listen(cls):
            for c in candles:
                yield c

        mock_streamer.listen = _listen
        mock_streamer_cls.return_value = mock_streamer

    @patch('orb_stacking.bar_fetcher.candle_to_bar')
    @patch('orb_stacking.bar_fetcher.DXLinkStreamer')
    async def test_excludes_today_still_forming_bar(self, mock_streamer_cls, mock_candle_to_bar):
        """Fetched bars exclude today's still-forming daily bar (ET-date filter)."""
        from orb_stacking.bar_fetcher import fetch_daily_bars
        # Use dates firmly in the past so they pass the today_et filter
        base_date = datetime(2026, 4, 1, 0, 0, 0, tzinfo=pytz.UTC)
        candles = [
            _mock_candle(int((base_date.timestamp() - (15 - i) * 86400) * 1000), 6500, 6550, 6490, 6530)
            for i in range(14)
        ]
        # Today's bar (should be filtered)
        today_ts = int(datetime.now(pytz.UTC).timestamp() * 1000)
        candles.append(_mock_candle(today_ts, 6540, 6560, 6530, 6550))
        self._setup_mock_streamer(mock_streamer_cls, candles)

        # Mock candle_to_bar to convert mock candles to dicts
        def bar_from_candle(c):
            if c.open is None or c.close is None:
                return None
            return {
                'time': c.time,
                'start': datetime.fromtimestamp(c.time / 1000, tz=UK_TZ),
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
            }
        mock_candle_to_bar.side_effect = bar_from_candle

        # Patch isinstance to recognize MockCandle as Candle
        orig_isinstance = builtins.isinstance
        def patched_isinstance(obj, classinfo):
            if classinfo is Candle and isinstance(obj, MockCandle):
                return True
            return orig_isinstance(obj, classinfo)

        with patch('builtins.isinstance', patched_isinstance):
            result = await fetch_daily_bars(MagicMock(), symbol="SPX")
        self.assertEqual(len(result), 14)

    @patch('orb_stacking.bar_fetcher.DXLinkStreamer')
    async def test_returns_empty_on_no_events(self, mock_streamer_cls):
        """If DXLink yields no events, returns []."""
        from orb_stacking.bar_fetcher import fetch_daily_bars
        self._setup_mock_streamer(mock_streamer_cls, [])
        result = await fetch_daily_bars(MagicMock(), symbol="SPX")
        self.assertEqual(result, [])

    @patch('orb_stacking.bar_fetcher.candle_to_bar')
    @patch('orb_stacking.bar_fetcher.DXLinkStreamer')
    async def test_filters_garbage_bars(self, mock_streamer_cls, mock_candle_to_bar):
        """Bars with O=0 or C=0 are filtered out."""
        from orb_stacking.bar_fetcher import fetch_daily_bars
        # Use dates firmly in the past so they pass the today_et filter
        base_date = datetime(2026, 4, 1, 0, 0, 0, tzinfo=pytz.UTC)
        candles = [
            _mock_candle(int((base_date.timestamp() - 5 * 86400) * 1000), 0, 0, 0, 0),  # garbage
            _mock_candle(int((base_date.timestamp() - 4 * 86400) * 1000), 6500, 6550, 6490, 6530),
            _mock_candle(int((base_date.timestamp() - 3 * 86400) * 1000), 6530, 6570, 6510, 6540),
            _mock_candle(int((base_date.timestamp() - 2 * 86400) * 1000), 6540, 6560, 6520, 6550),
        ]
        self._setup_mock_streamer(mock_streamer_cls, candles)

        # Mock candle_to_bar to convert mock candles to dicts
        def bar_from_candle(c):
            if c.open is None or c.close is None:
                return None
            return {
                'time': c.time,
                'start': datetime.fromtimestamp(c.time / 1000, tz=UK_TZ),
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
            }
        mock_candle_to_bar.side_effect = bar_from_candle

        # Patch isinstance to recognize MockCandle as Candle
        orig_isinstance = builtins.isinstance
        def patched_isinstance(obj, classinfo):
            if classinfo is Candle and isinstance(obj, MockCandle):
                return True
            return orig_isinstance(obj, classinfo)

        with patch('builtins.isinstance', patched_isinstance):
            result = await fetch_daily_bars(MagicMock(), symbol="SPX")
        self.assertEqual(len(result), 3)

    @patch('orb_stacking.bar_fetcher.candle_to_bar')
    @patch('orb_stacking.bar_fetcher.DXLinkStreamer')
    async def test_dedupes_by_timestamp(self, mock_streamer_cls, mock_candle_to_bar):
        """Duplicate bars (same time) are deduped — last write wins."""
        from orb_stacking.bar_fetcher import fetch_daily_bars
        # Use a date firmly in the past so it passes the today_et filter
        base_date = datetime(2026, 4, 1, 0, 0, 0, tzinfo=pytz.UTC)
        same_ts = int((base_date.timestamp() - 3 * 86400) * 1000)
        candles = [
            _mock_candle(same_ts, 6500, 6550, 6490, 6530),
            _mock_candle(same_ts, 6500, 6560, 6480, 6540),
        ]
        self._setup_mock_streamer(mock_streamer_cls, candles)

        # Mock candle_to_bar to convert mock candles to dicts
        def bar_from_candle(c):
            if c.open is None or c.close is None:
                return None
            return {
                'time': c.time,
                'start': datetime.fromtimestamp(c.time / 1000, tz=UK_TZ),
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
            }
        mock_candle_to_bar.side_effect = bar_from_candle

        # Patch isinstance to recognize MockCandle as Candle
        orig_isinstance = builtins.isinstance
        def patched_isinstance(obj, classinfo):
            if classinfo is Candle and isinstance(obj, MockCandle):
                return True
            return orig_isinstance(obj, classinfo)

        with patch('builtins.isinstance', patched_isinstance):
            result = await fetch_daily_bars(MagicMock(), symbol="SPX")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['high'], 6560)
        self.assertEqual(result[0]['close'], 6540)

    @patch('orb_stacking.bar_fetcher.DXLinkStreamer')
    async def test_returns_empty_on_setup_exception(self, mock_streamer_cls):
        """If DXLinkStreamer construction or __aenter__ raises, returns [] — no propagation."""
        from orb_stacking.bar_fetcher import fetch_daily_bars
        mock_streamer = AsyncMock()
        mock_streamer.__aenter__.side_effect = Exception("connection refused")
        mock_streamer_cls.return_value = mock_streamer
        result = await fetch_daily_bars(MagicMock(), symbol="SPX")
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
