import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd
import asyncio
import os
from monitor import check_open_positions, check_eod_expiration
from tastytrade.dxfeed import Quote


class TestMonitor(unittest.TestCase):

    def setUp(self):
        self.csv_path = "test_paper_trades.csv"
        data = {
            'Date': ['2023-10-27'],
            'Entry Time': ['10:00:00'],
            'Symbol': ['SPX'],
            'Strategy': ['20 Delta'],
            'StrategyId': ['IC-20D-1000'],
            'Short Call': ['SC'],
            'Long Call': ['LC'],
            'Short Put': ['SP'],
            'Long Put': ['LP'],
            'Credit Collected': [1.00],
            'Buying Power': [1000],
            'Profit Target': [0.25],
            'Status': ['OPEN'],
            'Exit Time': [''],
            'Exit P/L': [''],
            'Notes': [''],
            'IV Rank': [15.0]
        }
        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    @patch('monitor.DXLinkStreamer')
    def test_check_open_positions_close_trade(self, MockStreamer):
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance
        mock_session = MagicMock()

        # SC=0.50, SP=0.50, LC=0.15, LP=0.15 -> Debit=0.70 -> P/L=0.30 (triggers 0.25 target)
        quotes = [
            Quote(eventSymbol='SC', bidPrice=0.49, askPrice=0.51, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='SP', bidPrice=0.49, askPrice=0.51, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='LC', bidPrice=0.14, askPrice=0.16, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='LP', bidPrice=0.14, askPrice=0.16, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
        ]

        async def mock_listen(event_type):
            yield quotes

        mock_streamer_instance.listen = MagicMock(side_effect=mock_listen)
        asyncio.run(check_open_positions(mock_session, self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'CLOSED')
        self.assertAlmostEqual(float(df.iloc[0]['Exit P/L']), 0.30)

    @patch('monitor.DXLinkStreamer')
    def test_check_open_positions_no_close(self, MockStreamer):
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance
        mock_session = MagicMock()

        # SC=0.60, SP=0.60, LC=0.10, LP=0.10 -> Debit=1.00 -> P/L=0.00 (no close)
        quotes = [
            Quote(eventSymbol='SC', bidPrice=0.59, askPrice=0.61, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='SP', bidPrice=0.59, askPrice=0.61, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='LC', bidPrice=0.09, askPrice=0.11, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
            Quote(eventSymbol='LP', bidPrice=0.09, askPrice=0.11, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0),
        ]

        async def mock_listen(event_type):
            yield quotes

        mock_streamer_instance.listen = MagicMock(side_effect=mock_listen)
        asyncio.run(check_open_positions(mock_session, self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'OPEN')


class TestEODExpiration(unittest.TestCase):
    """Tests for check_eod_expiration settlement logic."""

    def setUp(self):
        self.csv_path = "test_eod_trades.csv"

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def _make_csv(self, short_call='SC6100', long_call='LC6120', short_put='SP6000', long_put='LP5980', credit=4.50):
        """Create a test CSV with symbols that have parseable strikes."""
        data = {
            'Date': ['2023-10-27'],
            'Entry Time': ['10:00:00'],
            'Symbol': ['SPX'],
            'Strategy': ['20 Delta'],
            'StrategyId': ['IC-20D-1000'],
            'Short Call': [f'.SPXW231027C{short_call}'],
            'Long Call': [f'.SPXW231027C{long_call}'],
            'Short Put': [f'.SPXW231027P{short_put}'],
            'Long Put': [f'.SPXW231027P{long_put}'],
            'Credit Collected': [credit],
            'Buying Power': [1600],
            'Profit Target': [credit * 0.25],
            'Status': ['OPEN'],
            'Exit Time': [''],
            'Exit P/L': [''],
            'Notes': [''],
            'IV Rank': [15.0]
        }
        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)

    @patch('monitor.is_market_closed', return_value=True)
    @patch('monitor.strategy_mod')
    def test_eod_otm_full_profit(self, mock_strategy, mock_closed):
        """SPX settles between short strikes -> full credit profit."""
        self._make_csv(short_call='6100', long_call='6120', short_put='6000', long_put='5980', credit=4.50)
        mock_strategy.get_spx_spot = AsyncMock(return_value=6050.0)

        mock_session = MagicMock()
        asyncio.run(check_eod_expiration(mock_session, self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'EXPIRED')
        self.assertAlmostEqual(float(df.iloc[0]['Exit P/L']), 4.50)

    @patch('monitor.is_market_closed', return_value=True)
    @patch('monitor.strategy_mod')
    def test_eod_call_breach(self, mock_strategy, mock_closed):
        """SPX settles above short call -> partial loss on call side."""
        self._make_csv(short_call='6100', long_call='6120', short_put='6000', long_put='5980', credit=4.50)
        # SPX at 6110 -> call debit = max(0, 6110-6100) - max(0, 6110-6120) = 10 - 0 = 10
        mock_strategy.get_spx_spot = AsyncMock(return_value=6110.0)

        mock_session = MagicMock()
        asyncio.run(check_eod_expiration(mock_session, self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'EXPIRED')
        # P/L = 4.50 - 10.00 = -5.50
        self.assertAlmostEqual(float(df.iloc[0]['Exit P/L']), -5.50)

    @patch('monitor.is_market_closed', return_value=True)
    @patch('monitor.strategy_mod')
    def test_eod_put_breach(self, mock_strategy, mock_closed):
        """SPX settles below short put -> partial loss on put side."""
        self._make_csv(short_call='6100', long_call='6120', short_put='6000', long_put='5980', credit=4.50)
        # SPX at 5990 -> put debit = max(0, 6000-5990) - max(0, 5980-5990) = 10 - 0 = 10
        mock_strategy.get_spx_spot = AsyncMock(return_value=5990.0)

        mock_session = MagicMock()
        asyncio.run(check_eod_expiration(mock_session, self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'EXPIRED')
        self.assertAlmostEqual(float(df.iloc[0]['Exit P/L']), -5.50)

    @patch('monitor.is_market_closed', return_value=False)
    def test_eod_not_called_before_close(self, mock_closed):
        """EOD function should not process trades before market close."""
        self._make_csv()
        mock_session = MagicMock()
        asyncio.run(check_eod_expiration(mock_session, self.csv_path))

        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'OPEN')


if __name__ == '__main__':
    unittest.main()
