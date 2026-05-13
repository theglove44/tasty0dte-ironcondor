import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd
import asyncio
import os
from datetime import datetime
from tastytrade.dxfeed import Quote

from project_paths import PAPER_TRADES_CSV
from premium_popper import _calculate_orb, _check_breakout, ORB_CANDLE_COUNT


class TestORBCalculation(unittest.TestCase):
    """Test ORB high/low/range/bias from candle data."""

    def _make_candles(self, data):
        """data: list of (open, high, low, close) tuples."""
        return [{'open': o, 'high': h, 'low': l, 'close': c}
                for o, h, l, c in data]

    def test_bullish_bias(self):
        # Candle 4 closes at 80% of range → bullish
        candles = self._make_candles([
            (100, 105, 98, 103),
            (103, 107, 101, 105),
            (105, 108, 100, 102),
            (102, 110, 98, 108),   # close at 108, range 98-110 → position (108-98)/12 = 0.83
        ])
        orb = _calculate_orb(candles)
        self.assertIsNotNone(orb)
        self.assertEqual(orb['high'], 110)
        self.assertEqual(orb['low'], 98)
        self.assertAlmostEqual(orb['range'], 12)
        self.assertEqual(orb['bias'], 'bullish')

    def test_bearish_bias(self):
        # Candle 4 closes at 20% of range → bearish
        candles = self._make_candles([
            (100, 105, 98, 103),
            (103, 107, 101, 105),
            (105, 108, 100, 102),
            (102, 106, 98, 99),  # close at 99, range 98-108 → position (99-98)/10 = 0.10
        ])
        orb = _calculate_orb(candles)
        self.assertIsNotNone(orb)
        self.assertEqual(orb['bias'], 'bearish')

    def test_neutral_bias(self):
        # Candle 4 closes at 50% of range → neutral
        candles = self._make_candles([
            (100, 105, 95, 103),
            (103, 107, 95, 105),
            (105, 108, 95, 102),
            (102, 106, 95, 101.5),  # close at 101.5, range 95-108 → (101.5-95)/13 ≈ 0.50
        ])
        orb = _calculate_orb(candles)
        self.assertIsNotNone(orb)
        self.assertEqual(orb['bias'], 'neutral')

    def test_insufficient_candles(self):
        candles = self._make_candles([
            (100, 105, 98, 103),
            (103, 107, 101, 105),
        ])
        orb = _calculate_orb(candles)
        self.assertIsNone(orb)

    def test_zero_range(self):
        candles = self._make_candles([
            (100, 100, 100, 100),
            (100, 100, 100, 100),
            (100, 100, 100, 100),
            (100, 100, 100, 100),
        ])
        orb = _calculate_orb(candles)
        self.assertIsNone(orb)


class TestBreakoutDetection(unittest.TestCase):
    """Test breakout detection against ORB."""

    def setUp(self):
        self.orb = {
            'high': 5800,
            'low': 5790,
            'range': 10,
            'midpoint': 5795,
            'bias': 'neutral',
        }

    def test_bullish_breakout(self):
        candle = {'open': 5798, 'high': 5803, 'low': 5797, 'close': 5802}
        # body = |5802 - 5798| = 4, 4 >= 10*0.10 = 1 ✓, close > 5800 ✓
        result = _check_breakout(candle, self.orb)
        self.assertIsNotNone(result)
        self.assertEqual(result['direction'], 'bullish')

    def test_bearish_breakout(self):
        candle = {'open': 5792, 'high': 5793, 'low': 5787, 'close': 5788}
        # body = |5788 - 5792| = 4, 4 >= 1 ✓, close < 5790 ✓
        result = _check_breakout(candle, self.orb)
        self.assertIsNotNone(result)
        self.assertEqual(result['direction'], 'bearish')

    def test_no_breakout_inside_range(self):
        candle = {'open': 5793, 'high': 5798, 'low': 5792, 'close': 5796}
        result = _check_breakout(candle, self.orb)
        self.assertIsNone(result)

    def test_weak_expansion_rejected(self):
        # Close outside range but body too small
        candle = {'open': 5800.5, 'high': 5801, 'low': 5800, 'close': 5800.8}
        # body = 0.3, threshold = 1.0 → rejected
        result = _check_breakout(candle, self.orb)
        self.assertIsNone(result)

    def test_bullish_blocked_by_bearish_bias(self):
        self.orb['bias'] = 'bearish'
        candle = {'open': 5798, 'high': 5803, 'low': 5797, 'close': 5802}
        result = _check_breakout(candle, self.orb)
        self.assertIsNone(result)

    def test_bearish_blocked_by_bullish_bias(self):
        self.orb['bias'] = 'bullish'
        candle = {'open': 5792, 'high': 5793, 'low': 5787, 'close': 5788}
        result = _check_breakout(candle, self.orb)
        self.assertIsNone(result)


class TestMonitor2LegSpread(unittest.TestCase):
    """Test monitor.py handling of 2-leg (NONE) spreads."""

    def setUp(self):
        self.csv_path = "test_pp_trades.csv"

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def _write_pp_trade(self, stop_loss=""):
        data = {
            'Date': [datetime.now().strftime('%Y-%m-%d')],
            'Entry Time': ['15:00:00'],
            'Symbol': ['SPX'],
            'Strategy': ['Premium Popper'],
            'StrategyId': ['PP-ORB-1500'],
            'Short Call': ['NONE'],
            'Long Call': ['NONE'],
            'Short Put': ['.SPXW260310P5790'],
            'Long Put': ['.SPXW260310P5785'],
            'Credit Collected': [1.00],
            'Buying Power': [400.00],
            'Profit Target': [0.50],
            'Stop Loss': [stop_loss],
            'Status': ['OPEN'],
            'Exit Time': [''],
            'Exit P/L': [''],
            'Notes': [''],
            'IV Rank': [15.0],
        }
        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)
        return df

    @patch('monitor.DXLinkStreamer')
    def test_2leg_debit_calculation(self, MockStreamer):
        """Debit should only use put side when call side is NONE."""
        self._write_pp_trade()
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance

        mock_session = MagicMock()

        # Put credit spread: short put mark=0.40, long put mark=0.10 → debit=0.30
        quotes = [
            Quote(eventSymbol='.SPXW260310P5790', bidPrice=0.39, askPrice=0.41,
                  bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X',
                  eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='.SPXW260310P5785', bidPrice=0.09, askPrice=0.11,
                  bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X',
                  eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='SPX', bidPrice=5795.0, askPrice=5796.0,
                  bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X',
                  eventTime=0, sequence=0, timeNanoPart=0),
        ]

        async def mock_listen(event_type):
            for q in quotes:
                yield q

        mock_streamer_instance.listen = mock_listen
        mock_streamer_instance.subscribe = AsyncMock()

        from monitor import check_open_positions
        asyncio.run(check_open_positions(mock_session, csv_path=self.csv_path, read_only=True))

        # Verify trade wasn't closed (profit target not met: debit=0.30, target_debit=1.0-0.5=0.5)
        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.at[0, 'Status'], 'OPEN')

    @patch('monitor.DXLinkStreamer')
    def test_stop_loss_triggers(self, MockStreamer):
        """Trade should close when debit >= stop loss."""
        self._write_pp_trade(stop_loss="2.00")
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance

        mock_session = MagicMock()

        # Put credit spread: short put mark=2.50, long put mark=0.10 → debit=2.40 > stop=2.00
        quotes = [
            Quote(eventSymbol='.SPXW260310P5790', bidPrice=2.49, askPrice=2.51,
                  bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X',
                  eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='.SPXW260310P5785', bidPrice=0.09, askPrice=0.11,
                  bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X',
                  eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='SPX', bidPrice=5795.0, askPrice=5796.0,
                  bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X',
                  eventTime=0, sequence=0, timeNanoPart=0),
        ]

        async def mock_listen(event_type):
            for q in quotes:
                yield q

        mock_streamer_instance.listen = mock_listen
        mock_streamer_instance.subscribe = AsyncMock()

        from monitor import check_open_positions
        asyncio.run(check_open_positions(mock_session, csv_path=self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.at[0, 'Status'], 'CLOSED')
        self.assertIn('Stop Loss', df.at[0, 'Notes'])

    @patch('monitor.is_market_closed', return_value=True)
    @patch('monitor.strategy_mod')
    def test_eod_2leg_settlement(self, mock_strategy, mock_closed):
        """EOD settlement should handle NONE call side correctly."""
        self._write_pp_trade()
        mock_strategy.get_spx_close = AsyncMock(return_value=5788.0)

        from monitor import check_eod_expiration

        asyncio.run(check_eod_expiration(MagicMock(), csv_path=self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.at[0, 'Status'], 'EXPIRED')
        # SPX=5788, short put 5790 ITM by 2, long put 5785 ITM by 3
        # put_debit = max(0, 5790-5788) - max(0, 5785-5788) = 2 - 0 = 2
        # call_debit = 0 (NONE side)
        # P/L = 1.00 - 2.00 = -1.00
        self.assertAlmostEqual(df.at[0, 'Exit P/L'], -1.00, places=2)

    @patch('monitor.is_market_closed', return_value=True)
    @patch('monitor.strategy_mod')
    def test_eod_2leg_otm_settlement(self, mock_strategy, mock_closed):
        """EOD settlement: put spread expires OTM → full profit."""
        self._write_pp_trade()
        mock_strategy.get_spx_close = AsyncMock(return_value=5800.0)

        from monitor import check_eod_expiration

        asyncio.run(check_eod_expiration(MagicMock(), csv_path=self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.at[0, 'Status'], 'EXPIRED')
        # SPX=5800, both puts OTM → debit=0, P/L = 1.00
        self.assertAlmostEqual(df.at[0, 'Exit P/L'], 1.00, places=2)


class TestLoggerStopLoss(unittest.TestCase):
    """Test logger.py writes Stop Loss column correctly."""

    def setUp(self):
        self.csv_path = "test_logger_sl.csv"
        import logger as trade_logger
        trade_logger.LOG_FILE = self.csv_path

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)
        import logger as trade_logger
        trade_logger.LOG_FILE = str(PAPER_TRADES_CSV)

    def test_stop_loss_written(self):
        import logger as trade_logger
        legs = {
            'short_call': {'symbol': 'NONE', 'strike': 0, 'delta': 0, 'price': 0},
            'long_call': {'symbol': 'NONE', 'strike': 0, 'delta': 0, 'price': 0},
            'short_put': {'symbol': '.SPXW260310P5790', 'strike': 5790, 'delta': -0.20, 'price': 1.20},
            'long_put': {'symbol': '.SPXW260310P5785', 'strike': 5785, 'delta': -0.15, 'price': 0.20},
        }
        trade_logger.log_trade_entry(
            legs, credit=1.00, buying_power=400, profit_target=0.50,
            strategy_name="Premium Popper", strategy_id="PP-ORB-1500",
            stop_loss=2.00)

        df = pd.read_csv(self.csv_path)
        self.assertIn('Stop Loss', df.columns)
        self.assertAlmostEqual(df.at[0, 'Stop Loss'], 2.00, places=2)
        self.assertEqual(df.at[0, 'Status'], 'OPEN')
        self.assertEqual(df.at[0, 'Short Call'], 'NONE')

    def test_no_stop_loss_empty(self):
        import logger as trade_logger
        legs = {
            'short_call': {'symbol': 'SC', 'strike': 5820, 'delta': 0.20, 'price': 0.50},
            'long_call': {'symbol': 'LC', 'strike': 5840, 'delta': 0.10, 'price': 0.15},
            'short_put': {'symbol': 'SP', 'strike': 5780, 'delta': -0.20, 'price': 0.50},
            'long_put': {'symbol': 'LP', 'strike': 5760, 'delta': -0.10, 'price': 0.15},
        }
        trade_logger.log_trade_entry(
            legs, credit=0.70, buying_power=1300, profit_target=0.175,
            strategy_name="20 Delta", strategy_id="IC-20D-1430")

        df = pd.read_csv(self.csv_path)
        self.assertIn('Stop Loss', df.columns)
        # Stop Loss should be NaN/empty for non-PP trades
        self.assertTrue(pd.isna(df.at[0, 'Stop Loss']) or str(df.at[0, 'Stop Loss']).strip() == '')


if __name__ == '__main__':
    unittest.main()
