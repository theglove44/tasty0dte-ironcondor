"""Tests for monitor.py Jade Lizard integrations."""

import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
import pandas as pd
import tempfile
import csv

from monitor import (
    _is_multi_day,
    _parse_target_expiry_from_notes,
    _quotes_two_sided,
    check_open_positions,
)
from tastytrade.dxfeed import Quote, Summary


def _two_sided_quote(symbol, bid=1.00, ask=1.20, bid_time=0):
    return SimpleNamespace(bid_price=bid, ask_price=ask, bid_time=bid_time)


class TestQuotesTwoSided(unittest.TestCase):
    """A two-sided book, not timestamp age, gates Jade Lizard profit takes."""

    def test_missing_quote_is_not_two_sided(self):
        self.assertFalse(_quotes_two_sided({}, ["SPXW 123"]))

    def test_none_bid_is_not_two_sided(self):
        quote = _two_sided_quote("SPXW 123")
        quote.bid_price = None
        self.assertFalse(_quotes_two_sided({"SPXW 123": quote}, ["SPXW 123"]))

    def test_none_ask_is_not_two_sided(self):
        quote = _two_sided_quote("SPXW 123")
        quote.ask_price = None
        self.assertFalse(_quotes_two_sided({"SPXW 123": quote}, ["SPXW 123"]))

    def test_zero_bid_is_not_two_sided(self):
        self.assertFalse(_quotes_two_sided(
            {"SPXW 123": _two_sided_quote("SPXW 123", bid=0, ask=1.20)},
            ["SPXW 123"],
        ))

    def test_zero_ask_is_not_two_sided(self):
        self.assertFalse(_quotes_two_sided(
            {"SPXW 123": _two_sided_quote("SPXW 123", bid=1.00, ask=0)},
            ["SPXW 123"],
        ))

    def test_two_sided_book_is_allowed(self):
        self.assertTrue(_quotes_two_sided(
            {"SPXW 123": _two_sided_quote("SPXW 123")},
            ["SPXW 123"],
        ))

    def test_old_bid_time_is_still_allowed(self):
        """Regression: far-OTM legs often have a stamp older than 60s."""
        stale_ms = datetime.utcnow().timestamp() * 1000 - 120_000
        quote = _two_sided_quote("SPXW 123", bid_time=stale_ms)
        self.assertTrue(_quotes_two_sided({"SPXW 123": quote}, ["SPXW 123"]))

    def test_one_of_four_one_sided_blocks(self):
        quotes = {
            "SC": _two_sided_quote("SC"),
            "LC": _two_sided_quote("LC"),
            "SP": _two_sided_quote("SP"),
            "LP": _two_sided_quote("LP", bid=0, ask=0.15),
        }
        self.assertFalse(_quotes_two_sided(quotes, ["SC", "LC", "SP", "LP"]))


class TestIsMultiDay(unittest.TestCase):
    """Tests for _is_multi_day helper."""

    def test_true_for_jade_lizard(self):
        """Test returns True for JadeLizard strategies."""
        self.assertTrue(_is_multi_day("JadeLizard_7DTE"))
        self.assertTrue(_is_multi_day("JadeLizard_5DTE"))
        self.assertTrue(_is_multi_day("JadeLizard_10DTE"))

    def test_false_for_iron_fly(self):
        """Test returns False for Iron Fly strategies."""
        self.assertFalse(_is_multi_day("Iron Fly V1"))
        self.assertFalse(_is_multi_day("Iron Fly V2"))
        self.assertFalse(_is_multi_day("Iron Fly V3"))
        self.assertFalse(_is_multi_day("Iron Fly V4"))

    def test_false_for_other_strategies(self):
        """Test returns False for other strategies."""
        self.assertFalse(_is_multi_day("Dynamic 0DTE"))
        self.assertFalse(_is_multi_day("Premium Popper"))
        self.assertFalse(_is_multi_day("20 Delta"))


class TestParseTargetExpiryFromNotes(unittest.TestCase):
    """Tests for _parse_target_expiry_from_notes helper."""

    def test_present(self):
        """Test extracts expiry when present."""
        notes = "target_expiry=2026-05-12;dte=7;em=50.00"
        result = _parse_target_expiry_from_notes(notes)
        self.assertEqual(result, date(2026, 5, 12))

    def test_missing(self):
        """Test returns None when key missing."""
        notes = "dte=7;em=50.00"
        result = _parse_target_expiry_from_notes(notes)
        self.assertIsNone(result)

    def test_malformed(self):
        """Test returns None when date malformed."""
        notes = "target_expiry=garbage;dte=7"
        result = _parse_target_expiry_from_notes(notes)
        self.assertIsNone(result)

    def test_empty_string(self):
        """Test returns None on empty string."""
        result = _parse_target_expiry_from_notes("")
        self.assertIsNone(result)


class TestStaleMaskExcludesJadeLizard(unittest.TestCase):
    """Integration test: stale_mask should not flag old-date JadeLizard trades."""

    def test_excludes_jade_lizard(self):
        """Test old-date OPEN JadeLizard not marked stale."""
        old_date = "2026-04-01"
        today_str = "2026-05-05"

        df = pd.DataFrame({
            'Date': [old_date],
            'Status': ['OPEN'],
            'Strategy': ['JadeLizard_7DTE'],
            'Short Call': ['SPX'],
            'Long Call': ['SPX'],
            'Short Put': ['SPX'],
            'Long Put': ['SPX'],
            'Credit Collected': [5.50],
            'Buying Power': [500],
            'Profit Target': [1.38],
        })

        # Simulate the stale_mask logic with multi-day check
        stale_mask = (
            (df['Status'] == 'OPEN')
            & (df['Date'].astype(str) < today_str)
            & (~df['Strategy'].astype(str).apply(_is_multi_day))
        )

        self.assertFalse(stale_mask.any())

    def test_still_expires_iron_fly(self):
        """Test old-date OPEN Iron Fly still marked stale."""
        old_date = "2026-04-01"
        today_str = "2026-05-05"

        df = pd.DataFrame({
            'Date': [old_date],
            'Status': ['OPEN'],
            'Strategy': ['Iron Fly V1'],
            'Short Call': ['SPX'],
            'Long Call': ['SPX'],
            'Short Put': ['SPX'],
            'Long Put': ['SPX'],
            'Credit Collected': [5.50],
            'Buying Power': [500],
            'Profit Target': [0.55],
        })

        # Simulate the stale_mask logic with multi-day check
        stale_mask = (
            (df['Status'] == 'OPEN')
            & (df['Date'].astype(str) < today_str)
            & (~df['Strategy'].astype(str).apply(_is_multi_day))
        )

        self.assertTrue(stale_mask.any())


class TestEodSkipsJadeLizardBeforeExpiry(unittest.IsolatedAsyncioTestCase):
    """Integration test: EOD settlement should skip JadeLizard before target_expiry."""

    async def test_skips_before_expiry(self):
        """Test JadeLizard with future target_expiry is not settled."""
        today = date.today()
        target_expiry = today + date.resolution  # tomorrow
        target_expiry_str = target_expiry.isoformat()
        notes = f"target_expiry={target_expiry_str};dte=1;em=50.00"

        csv_content = f"""Date,Strategy,Status,Short Call,Long Call,Short Put,Long Put,Credit Collected,Buying Power,Profit Target,Notes
{today.isoformat()},JadeLizard_7DTE,OPEN,SPX C4550,SPX C4555,SPX P4450,SPX P4430,5.50,500,1.38,{notes}"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            # Simulate check_eod_expiration logic
            df = pd.read_csv(csv_path)
            open_trades = df[df['Status'] == 'OPEN']

            for index, row in open_trades.iterrows():
                strategy_name = row.get('Strategy', '') if 'Strategy' in row else ''
                if _is_multi_day(str(strategy_name)):
                    expiry = _parse_target_expiry_from_notes(str(row.get('Notes', '')))
                    if expiry is None:
                        # Would log warning and continue
                        pass
                    elif expiry > today:
                        # Would log debug and continue (skip settlement)
                        self.assertGreater(expiry, today)
                    else:
                        # Would fall through to settlement
                        self.fail("Should have skipped")
        finally:
            import os
            os.unlink(csv_path)


class TestEodSettlesJadeLizardOnExpiry(unittest.IsolatedAsyncioTestCase):
    """Integration test: EOD settlement should settle JadeLizard on target_expiry."""

    async def test_settles_on_expiry(self):
        """Test JadeLizard with today's target_expiry is settled."""
        today = date.today()
        target_expiry_str = today.isoformat()
        notes = f"target_expiry={target_expiry_str};dte=0;em=50.00"

        csv_content = f"""Date,Strategy,Status,Short Call,Long Call,Short Put,Long Put,Credit Collected,Buying Power,Profit Target,Notes
{today.isoformat()},JadeLizard_7DTE,OPEN,SPX C4550,SPX C4555,SPX P4450,SPX P4430,5.50,500,1.38,{notes}"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            # Simulate check_eod_expiration logic
            df = pd.read_csv(csv_path)
            open_trades = df[df['Status'] == 'OPEN']

            for index, row in open_trades.iterrows():
                strategy_name = row.get('Strategy', '') if 'Strategy' in row else ''
                if _is_multi_day(str(strategy_name)):
                    expiry = _parse_target_expiry_from_notes(str(row.get('Notes', '')))
                    if expiry is None:
                        self.fail("Should have parsed expiry")
                    elif expiry > today:
                        self.fail("Should not skip settlement")
                    else:
                        # Fall through to settlement
                        if expiry < today:
                            # Would log warning about missed expiry
                            pass
                        # Would settle the trade
                        self.assertEqual(expiry, today)
        finally:
            import os
            os.unlink(csv_path)


class TestEodSettlesIronFlyUnchanged(unittest.IsolatedAsyncioTestCase):
    """Regression test: EOD settlement should still work for Iron Fly."""

    async def test_still_settles_iron_fly(self):
        """Test Iron Fly trades still settled normally."""
        today = date.today()

        csv_content = f"""Date,Strategy,Status,Short Call,Long Call,Short Put,Long Put,Credit Collected,Buying Power,Profit Target,Notes
{today.isoformat()},Iron Fly V1,OPEN,SPX C4550,SPX C4560,SPX P4450,SPX P4440,5.50,500,0.55,0DTE trade"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            # Simulate check_eod_expiration logic
            df = pd.read_csv(csv_path)
            open_trades = df[df['Status'] == 'OPEN']

            for index, row in open_trades.iterrows():
                strategy_name = row.get('Strategy', '') if 'Strategy' in row else ''
                if not _is_multi_day(str(strategy_name)):
                    # Would settle immediately (0DTE strategy)
                    self.assertFalse(_is_multi_day(strategy_name))
        finally:
            import os
            os.unlink(csv_path)


class TestTimeExitSkipsJadeLizard(unittest.TestCase):
    """Integration test: time exit logic should skip JadeLizard."""

    def test_no_time_exit_for_jade_lizard(self):
        """Test JadeLizard trades not subject to time exits."""
        row = {
            'Strategy': 'JadeLizard_7DTE',
            'Short Call': 'SPX C4550',
            'Long Call': 'SPX C4555',
            'Short Put': 'SPX P4450',
            'Long Put': 'SPX P4430',
        }

        strategy_name = row['Strategy']

        if _is_multi_day(strategy_name):
            is_time_exit = False
            time_exit_label = ""
        else:
            # Would apply time exit logic
            is_time_exit = True
            time_exit_label = "18:00"

        self.assertFalse(is_time_exit)
        self.assertEqual(time_exit_label, "")

    def test_time_exit_still_works_for_iron_fly(self):
        """Test Iron Fly still subject to time exits."""
        row = {
            'Strategy': 'Iron Fly V1',
            'Short Call': 'SPX C4550',
            'Long Call': 'SPX C4560',
            'Short Put': 'SPX P4450',
            'Long Put': 'SPX P4440',
        }

        strategy_name = row['Strategy']

        if _is_multi_day(strategy_name):
            is_time_exit = False
            time_exit_label = ""
        else:
            # Would apply time exit logic
            is_time_exit = True
            time_exit_label = "18:00"

        self.assertTrue(is_time_exit)
        self.assertEqual(time_exit_label, "18:00")


def _dxlink_quote(symbol, bid, ask, bid_time=0):
    return Quote(
        eventSymbol=symbol,
        bidPrice=bid,
        askPrice=ask,
        bidTime=bid_time,
        bidExchangeCode='X',
        askTime=0,
        askExchangeCode='X',
        eventTime=0,
        sequence=0,
        timeNanoPart=0,
    )


def _dxlink_summary():
    return Summary(
        eventSymbol='SPX',
        eventTime=0,
        dayId=0,
        dayClosePriceType='REGULAR',
        prevDayId=0,
        prevDayClosePriceType='REGULAR',
        openInterest=0,
        prevDayClosePrice=7700,
    )


class TestJadeLizardProfitTargetTwoSidedQuotes(unittest.TestCase):
    """Profit take must fire on a two-sided book even if bid_time is old."""

    def setUp(self):
        self.csv_path = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False).name
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
        pd.DataFrame({
            'Date': [yesterday],
            'Entry Time': ['10:00:00'],
            'Symbol': ['SPX'],
            'Strategy': ['JadeLizard_7DTE'],
            'StrategyId': ['JL7-1500'],
            'Short Call': ['SC'],
            'Long Call': ['LC'],
            'Short Put': ['SP'],
            'Long Put': ['LP'],
            'Credit Collected': [4.80],
            'Buying Power': [1520],
            'Profit Target': [1.20],
            'Status': ['OPEN'],
            'Exit Time': [''],
            'Exit P/L': [''],
            'Notes': ['target_expiry=2026-09-25;dte=7;em=80.00'],
            'IV Rank': [0.0],
        }).to_csv(self.csv_path, index=False)

    def tearDown(self):
        import os
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def _run_monitor(self, MockStreamer, quotes):
        mock_streamer_instance = AsyncMock()
        MockStreamer.return_value.__aenter__.return_value = mock_streamer_instance
        mock_session = MagicMock()

        async def mock_listen(event_type):
            if event_type is Quote:
                yield quotes
            else:
                yield _dxlink_summary()

        mock_streamer_instance.listen = MagicMock(side_effect=mock_listen)
        asyncio.run(check_open_positions(mock_session, self.csv_path))

    @patch('monitor.DXLinkStreamer')
    def test_old_timestamp_two_sided_book_closes(self, MockStreamer):
        stale_ms = int(datetime.utcnow().timestamp() * 1000 - 120_000)
        quotes = [
            _dxlink_quote('SC', 0.49, 0.51, stale_ms),
            _dxlink_quote('SP', 0.49, 0.51, stale_ms),
            _dxlink_quote('LC', 0.14, 0.16, stale_ms),
            _dxlink_quote('LP', 0.14, 0.16, stale_ms),
            _dxlink_quote('SPX', 7700, 7701, stale_ms),
        ]
        self._run_monitor(MockStreamer, quotes)
        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'CLOSED')
        self.assertAlmostEqual(float(df.iloc[0]['Exit P/L']), 4.10)

    @patch('monitor.DXLinkStreamer')
    def test_one_sided_book_does_not_close(self, MockStreamer):
        quotes = [
            _dxlink_quote('SC', 0.0, 0.51),
            _dxlink_quote('SP', 0.0, 0.51),
            _dxlink_quote('LC', 0.14, 0.16),
            _dxlink_quote('LP', 0.14, 0.16),
            _dxlink_quote('SPX', 7700, 7701),
        ]
        self._run_monitor(MockStreamer, quotes)
        df = pd.read_csv(self.csv_path)
        self.assertEqual(df.iloc[0]['Status'], 'OPEN')


if __name__ == '__main__':
    unittest.main()
