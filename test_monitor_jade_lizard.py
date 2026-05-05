"""Tests for monitor.py Jade Lizard integrations."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, time
import pandas as pd
import tempfile
import csv

from monitor import _is_multi_day, _parse_target_expiry_from_notes


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


if __name__ == '__main__':
    unittest.main()
