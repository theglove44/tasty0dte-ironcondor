import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd
import asyncio
import os
from monitor import check_open_positions
from tastytrade.dxfeed import Quote

class TestMonitor(unittest.TestCase):

    def setUp(self):
        # Create a dummy CSV
        self.csv_path = "test_paper_trades.csv"
        data = {
            'Date': ['2023-10-27'],
            'Entry Time': ['10:00:00'],
            'Symbol': ['SPX'],
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
            'Notes': ['']
        }
        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    @patch('monitor.DXLinkStreamer')
    def test_check_open_positions_close_trade(self, MockStreamer):
        # Setup Mock Streamer
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance
        
        # Mock Session
        mock_session = MagicMock()
        
        # Mock Quotes triggering a profit
        # Target Debit = 1.00 - 0.25 = 0.75
        # We need Current Debit <= 0.75
        
        # Let's say:
        # SC Mark = 0.50
        # SP Mark = 0.50
        # (Shorts = 1.00)
        # LC Mark = 0.15
        # LP Mark = 0.15
        # (Longs = 0.30)
        # Debit = 1.00 - 0.30 = 0.70 (Triggers Close)
        
        quotes = [
            Quote(eventSymbol='SC', bidPrice=0.49, askPrice=0.51, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.50
            Quote(eventSymbol='SP', bidPrice=0.49, askPrice=0.51, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.50
            Quote(eventSymbol='LC', bidPrice=0.14, askPrice=0.16, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.15
            Quote(eventSymbol='LP', bidPrice=0.14, askPrice=0.16, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.15
        ]
        
        # Mock listen() to yield these quotes then exit
        async def mock_listen(event_type):
            yield quotes
            
        mock_streamer_instance.listen = MagicMock(side_effect=mock_listen)

        # Run the function
        asyncio.run(check_open_positions(mock_session, self.csv_path))
        
        # Check CSV
        df = pd.read_csv(self.csv_path)
        print(df) # Debug
        
        self.assertEqual(df.iloc[0]['Status'], 'CLOSED')
        # Expected P/L: Credit (1.00) - Debit (0.70) = 0.30
        self.assertAlmostEqual(float(df.iloc[0]['Exit P/L']), 0.30)

    @patch('monitor.DXLinkStreamer')
    def test_check_open_positions_no_close(self, MockStreamer):
        # Setup Mock Streamer
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance
        
        # Mock Session
        mock_session = MagicMock()
        
        # Mock Quotes NOT triggering a profit
        # Target Debit = 0.75
        
        # Let's say:
        # SC Mark = 0.60
        # SP Mark = 0.60
        # (Shorts = 1.20)
        # LC Mark = 0.10
        # LP Mark = 0.10
        # (Longs = 0.20)
        # Debit = 1.20 - 0.20 = 1.00 (No close)
        
        quotes = [
            Quote(eventSymbol='SC', bidPrice=0.59, askPrice=0.61, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.60
            Quote(eventSymbol='SP', bidPrice=0.59, askPrice=0.61, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.60
            Quote(eventSymbol='LC', bidPrice=0.09, askPrice=0.11, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.10
            Quote(eventSymbol='LP', bidPrice=0.09, askPrice=0.11, bidTime=0, bidExchangeCode='X', askTime=0, askExchangeCode='X', eventTime=0, sequence=0, timeNanoPart=0), # Mark 0.10
        ]
        
        async def mock_listen(event_type):
            yield quotes
            
        mock_streamer_instance.listen = MagicMock(side_effect=mock_listen)

        # Run the function
        asyncio.run(check_open_positions(mock_session, self.csv_path))
        
        # Check CSV
        df = pd.read_csv(self.csv_path)
        
        self.assertEqual(df.iloc[0]['Status'], 'OPEN')

if __name__ == '__main__':
    unittest.main()
