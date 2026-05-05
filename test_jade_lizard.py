"""Tests for jade_lizard.py strategy module."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta
import tempfile
import csv
import math

from jade_lizard import (
    round_to_nearest_5,
    select_target_expiry,
    filter_for_target_expiry,
    fetch_expected_move,
    find_jade_lizard_legs,
    count_open_jade_lizards,
    execute_jade_lizard,
    CREDIT_FLOOR,
    CALL_WING_WIDTH,
    PUT_WING_WIDTH,
    PROFIT_TARGET_PCT,
)


class TestRoundToNearest5(unittest.TestCase):
    """Tests for round_to_nearest_5."""

    def test_exact_value(self):
        """Test exact multiple of 5."""
        self.assertEqual(round_to_nearest_5(4500.0), 4500)

    def test_round_up(self):
        """Test rounding up."""
        self.assertEqual(round_to_nearest_5(4502.6), 4505)

    def test_round_down(self):
        """Test rounding down."""
        self.assertEqual(round_to_nearest_5(4502.4), 4500)


class TestSelectTargetExpiry(unittest.TestCase):
    """Tests for select_target_expiry."""

    def test_picks_smallest_ge_target(self):
        """Test selects smallest expiry >= target date."""
        today = date.today()
        chain = {
            today + timedelta(days=3): [],
            today + timedelta(days=5): [],
            today + timedelta(days=8): [],
        }
        result = select_target_expiry(chain, today, 4)
        self.assertEqual(result, today + timedelta(days=5))

    def test_exact_match(self):
        """Test exact target_dte match."""
        today = date.today()
        chain = {today + timedelta(days=7): []}
        result = select_target_expiry(chain, today, 7)
        self.assertEqual(result, today + timedelta(days=7))

    def test_returns_none_when_all_before(self):
        """Test returns None when all expirations before target."""
        today = date.today()
        chain = {
            today + timedelta(days=1): [],
            today + timedelta(days=2): [],
        }
        result = select_target_expiry(chain, today, 7)
        self.assertIsNone(result)

    def test_empty_chain(self):
        """Test empty chain returns None."""
        today = date.today()
        result = select_target_expiry({}, today, 7)
        self.assertIsNone(result)


class TestFilterForTargetExpiry(unittest.TestCase):
    """Tests for filter_for_target_expiry."""

    def test_present(self):
        """Test returns list when date present."""
        today = date.today()
        opts = ["opt1", "opt2"]
        chain = {today + timedelta(days=7): opts}
        result = filter_for_target_expiry(chain, today + timedelta(days=7))
        self.assertEqual(result, opts)

    def test_missing(self):
        """Test returns None when date missing."""
        today = date.today()
        chain = {}
        result = filter_for_target_expiry(chain, today + timedelta(days=7))
        self.assertIsNone(result)

    def test_empty_list(self):
        """Test returns None when list empty."""
        today = date.today()
        chain = {today + timedelta(days=7): []}
        result = filter_for_target_expiry(chain, today + timedelta(days=7))
        self.assertIsNone(result)


class TestFetchExpectedMove(unittest.IsolatedAsyncioTestCase):
    """Tests for fetch_expected_move."""

    async def test_happy_path(self):
        """Test successful fetch with IV and DTE."""
        today = date.today()
        target_expiry = today + timedelta(days=7)
        spx_spot = 4500.0
        iv = 0.15
        dte = 7

        # OptionExpirationImpliedVolatility entry
        iv_entry = MagicMock()
        iv_entry.expiration_date = target_expiry
        iv_entry.implied_volatility = iv

        # MarketMetricInfo entry for SPX
        spx_metric = MagicMock()
        spx_metric.option_expiration_implied_volatilities = [iv_entry]

        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = [spx_metric]
            result = await fetch_expected_move(session, spx_spot, target_expiry, today)
            expected = spx_spot * iv * math.sqrt(dte / 365.0)
            self.assertAlmostEqual(result, expected, places=2)

    async def test_no_metrics(self):
        """Test returns None when metrics empty."""
        today = date.today()
        target_expiry = today + timedelta(days=7)
        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = []
            result = await fetch_expected_move(session, 4500.0, target_expiry, today)
            self.assertIsNone(result)

    async def test_no_iv_list(self):
        """Test returns None when IV list None."""
        today = date.today()
        target_expiry = today + timedelta(days=7)

        spx_metric = MagicMock()
        spx_metric.option_expiration_implied_volatilities = None

        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = [spx_metric]
            result = await fetch_expected_move(session, 4500.0, target_expiry, today)
            self.assertIsNone(result)

    async def test_no_matching_expiry(self):
        """Test returns None when expiry not found."""
        today = date.today()
        target_expiry = today + timedelta(days=7)
        other_expiry = today + timedelta(days=8)

        iv_entry = MagicMock()
        iv_entry.expiration_date = other_expiry
        iv_entry.implied_volatility = 0.15

        spx_metric = MagicMock()
        spx_metric.option_expiration_implied_volatilities = [iv_entry]

        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = [spx_metric]
            result = await fetch_expected_move(session, 4500.0, target_expiry, today)
            self.assertIsNone(result)

    async def test_iv_none(self):
        """Test returns None when IV is None."""
        today = date.today()
        target_expiry = today + timedelta(days=7)

        iv_entry = MagicMock()
        iv_entry.expiration_date = target_expiry
        iv_entry.implied_volatility = None

        spx_metric = MagicMock()
        spx_metric.option_expiration_implied_volatilities = [iv_entry]

        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = [spx_metric]
            result = await fetch_expected_move(session, 4500.0, target_expiry, today)
            self.assertIsNone(result)

    async def test_iv_zero(self):
        """Test returns None when IV is 0."""
        today = date.today()
        target_expiry = today + timedelta(days=7)

        iv_entry = MagicMock()
        iv_entry.expiration_date = target_expiry
        iv_entry.implied_volatility = 0

        spx_metric = MagicMock()
        spx_metric.option_expiration_implied_volatilities = [iv_entry]

        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = [spx_metric]
            result = await fetch_expected_move(session, 4500.0, target_expiry, today)
            self.assertIsNone(result)

    async def test_negative_dte(self):
        """Test returns None when DTE negative."""
        today = date.today()
        target_expiry = today - timedelta(days=1)

        iv_entry = MagicMock()
        iv_entry.expiration_date = target_expiry
        iv_entry.implied_volatility = 0.15

        spx_metric = MagicMock()
        spx_metric.option_expiration_implied_volatilities = [iv_entry]

        session = MagicMock()

        with patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_unwrap.return_value = [spx_metric]
            result = await fetch_expected_move(session, 4500.0, target_expiry, today)
            self.assertIsNone(result)


class TestFindJadeLizardLegs(unittest.TestCase):
    """Tests for find_jade_lizard_legs."""

    def test_happy_path(self):
        """Test successful leg finding."""
        from tastytrade.instruments import OptionType

        spx_spot = 4500.0
        expected_move = 50.0

        # Expected strikes
        sp = 4450  # round_to_nearest_5(4500 - 50)
        lp = 4430  # 4450 - 20
        sc = 4550  # round_to_nearest_5(4500 + 50)
        lc = 4555  # 4550 + 5

        # Build options
        opts = []
        for strike, opt_type in [
            (sp, OptionType.PUT),
            (lp, OptionType.PUT),
            (sc, OptionType.CALL),
            (lc, OptionType.CALL),
        ]:
            opt = MagicMock()
            opt.strike_price = float(strike)
            opt.option_type = opt_type
            opt.streamer_symbol = f"SPX{opt_type.value}{strike}"
            opt.symbol = f"SPX {date.today()} {opt_type.value} {strike}"
            opts.append(opt)

        result = find_jade_lizard_legs(opts, spx_spot, expected_move)

        self.assertIsNotNone(result)
        self.assertEqual(int(result['short_put']['strike']), sp)
        self.assertEqual(int(result['long_put']['strike']), lp)
        self.assertEqual(int(result['short_call']['strike']), sc)
        self.assertEqual(int(result['long_call']['strike']), lc)

    def test_strike_missing(self):
        """Test returns None when strike missing."""
        from tastytrade.instruments import OptionType

        spx_spot = 4500.0
        expected_move = 50.0

        # Only put side
        opts = []
        for strike in [4450, 4430]:
            opt = MagicMock()
            opt.strike_price = float(strike)
            opt.option_type = OptionType.PUT
            opt.streamer_symbol = f"SPX{strike}"
            opts.append(opt)

        result = find_jade_lizard_legs(opts, spx_spot, expected_move)

        self.assertIsNone(result)

    def test_inverted_short_strikes(self):
        """Test returns None when sc <= sp."""
        from tastytrade.instruments import OptionType

        spx_spot = 4500.0
        expected_move = 0.0  # This makes sc == sp

        opts = []
        strikes = [4500, 4480, 4500, 4505]
        types = [OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL]

        for strike, opt_type in zip(strikes, types):
            opt = MagicMock()
            opt.strike_price = float(strike)
            opt.option_type = opt_type
            opt.streamer_symbol = f"SPX{strike}"
            opts.append(opt)

        result = find_jade_lizard_legs(opts, spx_spot, expected_move)

        self.assertIsNone(result)


class TestCountOpenJadeLizards(unittest.TestCase):
    """Tests for count_open_jade_lizards."""

    def test_no_file(self):
        """Test returns 0 when file missing."""
        result = count_open_jade_lizards("/nonexistent/path.csv")
        self.assertEqual(result, 0)

    def test_zero_open(self):
        """Test returns 0 when no open JadeLizard trades."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['Date', 'Strategy', 'Status', 'Short Call', 'Long Call', 'Short Put', 'Long Put', 'Credit Collected', 'Buying Power', 'Profit Target']
            )
            writer.writeheader()
            writer.writerow({
                'Date': '2026-05-05',
                'Strategy': 'Iron Fly V1',
                'Status': 'OPEN',
                'Short Call': 'SPX',
                'Long Call': 'SPX',
                'Short Put': 'SPX',
                'Long Put': 'SPX',
                'Credit Collected': '5.50',
                'Buying Power': '500',
                'Profit Target': '0.55',
            })
            csv_path = f.name

        try:
            result = count_open_jade_lizards(csv_path)
            self.assertEqual(result, 0)
        finally:
            import os
            os.unlink(csv_path)

    def test_one_open(self):
        """Test counts one open JadeLizard_7DTE."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['Date', 'Strategy', 'Status', 'Short Call', 'Long Call', 'Short Put', 'Long Put', 'Credit Collected', 'Buying Power', 'Profit Target']
            )
            writer.writeheader()
            writer.writerow({
                'Date': '2026-05-05',
                'Strategy': 'JadeLizard_7DTE',
                'Status': 'OPEN',
                'Short Call': 'SPX',
                'Long Call': 'SPX',
                'Short Put': 'SPX',
                'Long Put': 'SPX',
                'Credit Collected': '5.50',
                'Buying Power': '500',
                'Profit Target': '1.38',
            })
            writer.writerow({
                'Date': '2026-04-28',
                'Strategy': 'JadeLizard_7DTE',
                'Status': 'CLOSED',
                'Short Call': 'SPX',
                'Long Call': 'SPX',
                'Short Put': 'SPX',
                'Long Put': 'SPX',
                'Credit Collected': '5.50',
                'Buying Power': '500',
                'Profit Target': '1.38',
            })
            csv_path = f.name

        try:
            result = count_open_jade_lizards(csv_path)
            self.assertEqual(result, 1)
        finally:
            import os
            os.unlink(csv_path)

    def test_mixed_variants(self):
        """Test counts multiple JadeLizard variants."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['Date', 'Strategy', 'Status', 'Short Call', 'Long Call', 'Short Put', 'Long Put', 'Credit Collected', 'Buying Power', 'Profit Target']
            )
            writer.writeheader()
            writer.writerow({
                'Date': '2026-05-05',
                'Strategy': 'JadeLizard_5DTE',
                'Status': 'OPEN',
                'Short Call': 'SPX',
                'Long Call': 'SPX',
                'Short Put': 'SPX',
                'Long Put': 'SPX',
                'Credit Collected': '5.50',
                'Buying Power': '500',
                'Profit Target': '1.38',
            })
            writer.writerow({
                'Date': '2026-05-05',
                'Strategy': 'JadeLizard_10DTE',
                'Status': 'OPEN',
                'Short Call': 'SPX',
                'Long Call': 'SPX',
                'Short Put': 'SPX',
                'Long Put': 'SPX',
                'Credit Collected': '5.50',
                'Buying Power': '500',
                'Profit Target': '1.38',
            })
            csv_path = f.name

        try:
            result = count_open_jade_lizards(csv_path)
            self.assertEqual(result, 2)
        finally:
            import os
            os.unlink(csv_path)


class TestExecuteJadeLizard(unittest.IsolatedAsyncioTestCase):
    """Tests for execute_jade_lizard."""

    async def test_skips_when_active(self):
        """Test skips if JadeLizard already open."""
        session = MagicMock()

        with patch('jade_lizard.count_open_jade_lizards') as mock_count:
            mock_count.return_value = 1

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_skips_on_no_spot(self):
        """Test skips when get_spx_spot returns None."""
        session = MagicMock()

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot:
            mock_count.return_value = 0
            mock_spot.return_value = None

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_skips_on_no_expiry(self):
        """Test skips when no suitable expiry found."""
        session = MagicMock()

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap:
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_unwrap.return_value = {}
            mock_chain.return_value = {}

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_skips_on_no_em(self):
        """Test skips when fetch_expected_move returns None."""
        session = MagicMock()
        today = date.today()

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.fetch_expected_move') as mock_em:
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_em.return_value = None

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_skips_on_no_legs(self):
        """Test skips when find_jade_lizard_legs returns None."""
        session = MagicMock()
        today = date.today()

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.filter_for_target_expiry') as mock_filter, \
             patch('jade_lizard.fetch_expected_move') as mock_em, \
             patch('jade_lizard.find_jade_lizard_legs') as mock_legs:
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_filter.return_value = []
            mock_em.return_value = 50.0
            mock_legs.return_value = None

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_skips_on_missing_price(self):
        """Test skips when leg price is 0 or None."""
        session = MagicMock()
        today = date.today()

        legs = {
            'short_put': {'strike': 4450.0, 'symbol': 'SP', 'occ_symbol': 'SPX', 'price': 0.0},
            'long_put': {'strike': 4430.0, 'symbol': 'LP', 'occ_symbol': 'SPX', 'price': 0.25},
            'short_call': {'strike': 4550.0, 'symbol': 'SC', 'occ_symbol': 'SPX', 'price': 0.15},
            'long_call': {'strike': 4555.0, 'symbol': 'LC', 'occ_symbol': 'SPX', 'price': 0.10},
        }

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.filter_for_target_expiry') as mock_filter, \
             patch('jade_lizard.fetch_expected_move') as mock_em, \
             patch('jade_lizard.find_jade_lizard_legs') as mock_legs, \
             patch('jade_lizard.strategy_mod._fetch_leg_prices'):
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_filter.return_value = []
            mock_em.return_value = 50.0
            mock_legs.return_value = legs

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_skips_on_credit_floor(self):
        """Test skips when credit below floor."""
        session = MagicMock()
        today = date.today()

        legs = {
            'short_put': {'strike': 4450.0, 'symbol': 'SP', 'occ_symbol': 'SPX', 'price': 1.00},
            'long_put': {'strike': 4430.0, 'symbol': 'LP', 'occ_symbol': 'SPX', 'price': 0.25},
            'short_call': {'strike': 4550.0, 'symbol': 'SC', 'occ_symbol': 'SPX', 'price': 1.00},
            'long_call': {'strike': 4555.0, 'symbol': 'LC', 'occ_symbol': 'SPX', 'price': 0.25},
        }
        # credit = (1.00 + 1.00) - (0.25 + 0.25) = 1.50 < 4.50

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.filter_for_target_expiry') as mock_filter, \
             patch('jade_lizard.fetch_expected_move') as mock_em, \
             patch('jade_lizard.find_jade_lizard_legs') as mock_legs, \
             patch('jade_lizard.strategy_mod._fetch_leg_prices'):
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_filter.return_value = []
            mock_em.return_value = 50.0
            mock_legs.return_value = legs

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)

    async def test_logs_trade_on_success(self):
        """Test logs trade when all conditions met."""
        session = MagicMock()
        today = date.today()

        legs = {
            'short_put': {'strike': 4450.0, 'symbol': 'SP', 'occ_symbol': 'SPX 260512P04450', 'price': 2.50},
            'long_put': {'strike': 4430.0, 'symbol': 'LP', 'occ_symbol': 'SPX 260512P04430', 'price': 0.50},
            'short_call': {'strike': 4550.0, 'symbol': 'SC', 'occ_symbol': 'SPX 260512C04550', 'price': 2.50},
            'long_call': {'strike': 4555.0, 'symbol': 'LC', 'occ_symbol': 'SPX 260512C04555', 'price': 1.00},
        }
        # credit = (2.50 + 2.50) - (0.50 + 1.00) = 3.50... wait that's still below floor
        # Let me recalculate: (2.50 + 2.50) - (0.50 + 1.00) = 5.00 - 1.50 = 3.50. Still below.
        # Need higher prices: short_put=3.00, short_call=3.00, long_put=0.50, long_call=0.50
        legs['short_put']['price'] = 3.00
        legs['short_call']['price'] = 3.00
        # credit = (3.00 + 3.00) - (0.50 + 0.50) = 6.00 - 1.00 = 5.00 >= 4.50 ✓

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.filter_for_target_expiry') as mock_filter, \
             patch('jade_lizard.fetch_expected_move') as mock_em, \
             patch('jade_lizard.find_jade_lizard_legs') as mock_legs, \
             patch('jade_lizard.strategy_mod._fetch_leg_prices'), \
             patch('jade_lizard.validate_credit_sanity') as mock_validate, \
             patch('jade_lizard.trade_logger.log_trade_entry') as mock_log:
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_filter.return_value = []
            mock_em.return_value = 50.0
            mock_legs.return_value = legs
            mock_validate.return_value = (True, "")

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertTrue(result)
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            self.assertIn('strategy_name', call_args.kwargs)
            self.assertEqual(call_args.kwargs['strategy_name'], "JadeLizard_7DTE")
            self.assertIn('notes', call_args.kwargs)
            self.assertIn('target_expiry=', call_args.kwargs['notes'])

    async def test_buying_power_uses_put_wing(self):
        """Test buying_power calculation uses PUT_WING_WIDTH."""
        session = MagicMock()
        today = date.today()

        legs = {
            'short_put': {'strike': 4450.0, 'symbol': 'SP', 'occ_symbol': 'SPX', 'price': 3.00},
            'long_put': {'strike': 4430.0, 'symbol': 'LP', 'occ_symbol': 'SPX', 'price': 0.50},
            'short_call': {'strike': 4550.0, 'symbol': 'SC', 'occ_symbol': 'SPX', 'price': 3.00},
            'long_call': {'strike': 4555.0, 'symbol': 'LC', 'occ_symbol': 'SPX', 'price': 0.50},
        }
        # credit = 5.00

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.filter_for_target_expiry') as mock_filter, \
             patch('jade_lizard.fetch_expected_move') as mock_em, \
             patch('jade_lizard.find_jade_lizard_legs') as mock_legs, \
             patch('jade_lizard.strategy_mod._fetch_leg_prices'), \
             patch('jade_lizard.validate_credit_sanity') as mock_validate, \
             patch('jade_lizard.trade_logger.log_trade_entry') as mock_log:
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_filter.return_value = []
            mock_em.return_value = 50.0
            mock_legs.return_value = legs
            mock_validate.return_value = (True, "")

            await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            call_args = mock_log.call_args
            expected_bp = PUT_WING_WIDTH * 100 - 5.00 * 100
            self.assertEqual(call_args[0][2], expected_bp)  # buying_power is 3rd positional arg

    async def test_profit_target_is_credit_times_pct(self):
        """Test profit_target equals credit * profit_target_pct."""
        session = MagicMock()
        today = date.today()

        legs = {
            'short_put': {'strike': 4450.0, 'symbol': 'SP', 'occ_symbol': 'SPX', 'price': 3.00},
            'long_put': {'strike': 4430.0, 'symbol': 'LP', 'occ_symbol': 'SPX', 'price': 0.50},
            'short_call': {'strike': 4550.0, 'symbol': 'SC', 'occ_symbol': 'SPX', 'price': 3.00},
            'long_call': {'strike': 4555.0, 'symbol': 'LC', 'occ_symbol': 'SPX', 'price': 0.50},
        }
        # credit = 5.00, profit_target = 5.00 * 0.25 = 1.25

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot, \
             patch('jade_lizard.fetch_spx_option_chain') as mock_chain, \
             patch('jade_lizard._unwrap_awaitable') as mock_unwrap, \
             patch('jade_lizard.select_target_expiry') as mock_expiry, \
             patch('jade_lizard.filter_for_target_expiry') as mock_filter, \
             patch('jade_lizard.fetch_expected_move') as mock_em, \
             patch('jade_lizard.find_jade_lizard_legs') as mock_legs, \
             patch('jade_lizard.strategy_mod._fetch_leg_prices'), \
             patch('jade_lizard.validate_credit_sanity') as mock_validate, \
             patch('jade_lizard.trade_logger.log_trade_entry') as mock_log:
            mock_count.return_value = 0
            mock_spot.return_value = 4500.0
            mock_chain.return_value = {today + timedelta(days=7): []}
            mock_unwrap.return_value = {today + timedelta(days=7): []}
            mock_expiry.return_value = today + timedelta(days=7)
            mock_filter.return_value = []
            mock_em.return_value = 50.0
            mock_legs.return_value = legs
            mock_validate.return_value = (True, "")

            await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            call_args = mock_log.call_args
            expected_pt = 5.00 * 0.25
            self.assertAlmostEqual(call_args[0][3], expected_pt, places=2)  # profit_target is 4th positional arg

    async def test_swallows_exception(self):
        """Test catches and logs exceptions."""
        session = MagicMock()

        with patch('jade_lizard.count_open_jade_lizards') as mock_count, \
             patch('jade_lizard.get_spx_spot') as mock_spot:
            mock_count.return_value = 0
            mock_spot.side_effect = RuntimeError("Test error")

            result = await execute_jade_lizard(
                session,
                target_dte=7,
                strategy_name="JadeLizard_7DTE",
                strategy_id="JL7",
            )

            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
