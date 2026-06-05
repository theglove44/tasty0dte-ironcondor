"""
Tests for entry-reliability fixes (2026-06-05): FIX 1 (retry with fresh marks),
FIX 2 (chain fetch retry), FIX 3 (skip notifications).
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import time

import main
from main import (
    _notify_skip,
    _fetch_chain_with_retry,
    _build_validated_trade,
    PARITY_RETRY_ATTEMPTS,
    CHAIN_FETCH_ATTEMPTS,
)
import strategy


def _fly_legs(sc_strike=6600, sc_price=10.0, lc_strike=6610, lc_price=6.0,
              sp_strike=6600, sp_price=4.0, lp_strike=6590, lp_price=2.1):
    """Build a reusable iron-fly legs dict with symbol/occ_symbol for embed path."""
    return {
        'short_call': {
            'strike': float(sc_strike),
            'price': sc_price,
            'symbol': f'.SPXW260320C{sc_strike}',
            'occ_symbol': f'SPX 260320C{sc_strike:05d}',
            'delta': 0.30,
        },
        'long_call': {
            'strike': float(lc_strike),
            'price': lc_price,
            'symbol': f'.SPXW260320C{lc_strike}',
            'occ_symbol': f'SPX 260320C{lc_strike:05d}',
            'delta': 0.15,
        },
        'short_put': {
            'strike': float(sp_strike),
            'price': sp_price,
            'symbol': f'.SPXW260320P{sp_strike}',
            'occ_symbol': f'SPX 260320P{sp_strike:05d}',
            'delta': 0.30,
        },
        'long_put': {
            'strike': float(lp_strike),
            'price': lp_price,
            'symbol': f'.SPXW260320P{lp_strike}',
            'occ_symbol': f'SPX 260320P{lp_strike:05d}',
            'delta': 0.15,
        },
    }


class TestBuildValidatedTradeRetry(unittest.IsolatedAsyncioTestCase):
    """FIX 1: _build_validated_trade retries with fresh marks."""

    async def test_retry_succeeds_when_marks_refresh(self):
        """Stale marks fail attempt 1; fresh marks pass attempt 2 — REAL validator.

        Uses the real strategy.validate_credit_sanity (not mocked) so this proves
        the reject -> re-fetch -> accept transition end-to-end, including the guard
        math itself.
        """
        # Stale attempt: credit = (20.25+17.35) - (14.25+13.35) = $10.00 on a $10
        # wing -> real validator rejects via the max-credit/arbitrage guard (a
        # stale-mark artifact, just like a parity drift).
        stale_legs = _fly_legs(sc_price=20.25, lc_price=14.25, sp_price=17.35, lp_price=13.35)
        # Fresh attempt: credit = (22.45+14.95) - (16.65+11.45) = $9.30; parity
        # drift |7.50 - 8.00| = 0.50 < 2.00 -> real validator passes.
        fresh_legs = _fly_legs(sc_price=22.45, lc_price=16.65, sp_price=14.95, lp_price=11.45)

        strat = {
            'name': 'Iron Fly V1',
            'type': 'iron_fly',
            'target_delta': 0.50,
            'wing_width': 10,
        }

        session = MagicMock()

        with patch('main.strategy.find_iron_fly_legs', new_callable=AsyncMock) as mock_find, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.asyncio.sleep', new_callable=AsyncMock):

            # Attempt 1: stale marks fail validation; attempt 2: fresh marks pass.
            mock_find.side_effect = [stale_legs, fresh_legs]
            mock_spot.return_value = 6608.0

            result = await _build_validated_trade(session, strat, [])

            self.assertEqual(result["status"], "ok")
            self.assertAlmostEqual(result["credit"], 9.30, places=2)
            self.assertEqual(mock_find.call_count, 2)

    async def test_retry_exhausted_returns_rejected(self):
        """All retry attempts fail validation."""
        stale_legs = _fly_legs(sc_price=20.25, sp_price=17.35)

        strat = {
            'name': 'Iron Fly V2',
            'type': 'iron_fly',
            'target_delta': 0.50,
            'wing_width': 10,
        }

        session = MagicMock()

        with patch('main.strategy.find_iron_fly_legs', new_callable=AsyncMock) as mock_find, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.validate_credit_sanity') as mock_validate, \
             patch('main.asyncio.sleep', new_callable=AsyncMock):

            mock_find.return_value = stale_legs
            mock_spot.return_value = 6607.19
            mock_validate.return_value = (False, "put-call parity violation")

            result = await _build_validated_trade(session, strat, [])

            self.assertEqual(result["status"], "rejected")
            self.assertIn("after 3 attempts", result["reason"])
            self.assertEqual(mock_find.call_count, PARITY_RETRY_ATTEMPTS)

    async def test_no_legs_returns_immediately_without_retry(self):
        """Finder returns None — no retry."""
        strat = {
            'name': 'Iron Fly V1',
            'type': 'iron_fly',
            'target_delta': 0.50,
            'wing_width': 10,
        }

        session = MagicMock()

        with patch('main.strategy.find_iron_fly_legs', new_callable=AsyncMock) as mock_find, \
             patch('main.strategy.validate_credit_sanity') as mock_validate:

            mock_find.return_value = None

            result = await _build_validated_trade(session, strat, [])

            self.assertEqual(result["status"], "no_legs")
            self.assertEqual(mock_find.call_count, 1)
            # validate_credit_sanity should NOT be called if finder returns None
            mock_validate.assert_not_called()

    async def test_first_attempt_success_no_sleep(self):
        """Legs pass validation on attempt 1 — no retry, no sleep."""
        legs = _fly_legs()

        strat = {
            'name': 'Iron Fly V1',
            'type': 'iron_fly',
            'target_delta': 0.50,
            'wing_width': 10,
        }

        session = MagicMock()

        with patch('main.strategy.find_iron_fly_legs', new_callable=AsyncMock) as mock_find, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.validate_credit_sanity') as mock_validate, \
             patch('main.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            mock_find.return_value = legs
            mock_spot.return_value = 6607.0
            mock_validate.return_value = (True, "")

            result = await _build_validated_trade(session, strat, [])

            self.assertEqual(result["status"], "ok")
            self.assertEqual(mock_find.call_count, 1)
            mock_sleep.assert_not_called()

    async def test_iron_condor_type_uses_condor_finder(self):
        """Iron Condor strategy uses find_iron_condor_legs."""
        legs = _fly_legs(sc_strike=6645, lc_strike=6665, sp_strike=6565, lp_strike=6545)

        strat = {
            'name': 'IC-20D',
            'type': 'iron_condor',
            'target_delta': 0.20,
        }

        session = MagicMock()

        with patch('main.strategy.find_iron_condor_legs', new_callable=AsyncMock) as mock_condor, \
             patch('main.strategy.find_iron_fly_legs', new_callable=AsyncMock) as mock_fly, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.validate_credit_sanity') as mock_validate:

            mock_condor.return_value = legs
            mock_spot.return_value = 6608.0
            mock_validate.return_value = (True, "")

            result = await _build_validated_trade(session, strat, [])

            self.assertEqual(result["status"], "ok")
            mock_condor.assert_called_once()
            mock_fly.assert_not_called()

    async def test_dynamic_no_move_data_is_no_legs(self):
        """Dynamic strategy with no move data returns no_legs."""
        strat = {
            'name': 'Dynamic 0DTE',
            'type': 'dynamic_0dte',
            'move_threshold': -0.1,
            'condor_delta': 0.20,
            'fly_delta': 0.50,
            'fly_wing_width': 10,
        }

        session = MagicMock()

        with patch('main.strategy.get_spx_30min_move', new_callable=AsyncMock) as mock_move, \
             patch('main.strategy.find_iron_condor_legs', new_callable=AsyncMock) as mock_condor:

            mock_move.return_value = None

            result = await _build_validated_trade(session, strat, [])

            self.assertEqual(result["status"], "no_legs")
            mock_condor.assert_not_called()


class TestExecuteTradeCycleIsolation(unittest.IsolatedAsyncioTestCase):
    """FIX 2 + FIX 3: cycle isolation and skip notifications."""

    async def test_one_strategy_crash_does_not_skip_later(self):
        """First strat crashes; second strat still logs a trade."""
        ok_result = {
            "status": "ok",
            "legs": _fly_legs(),
            "credit": 5.90,
            "width": 10.0,
            "spx_spot": 6607.0,
            "notes_extra": "",
        }

        strats = [
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
            {
                'name': 'Iron Fly V2',
                'code': 'IF-V2',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.20,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.trade_logger.log_trade_entry') as mock_log, \
             patch('main.discord_notify', None):

            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.side_effect = [RuntimeError("boom"), ok_result]

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # Second strat should have logged (first crashed)
            self.assertEqual(mock_log.call_count, 1)

    async def test_crash_is_logged_with_exc_info(self):
        """Strategy crash is logged with exc_info=True."""
        strats = [
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.discord_notify', None), \
             self.assertLogs("0dte-trader", level="ERROR") as cm:

            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.side_effect = RuntimeError("boom")

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # Check that an error log contains "Strategy crashed" and exc_info was set
            crash_records = [r for r in cm.records if "Strategy crashed" in r.getMessage()]
            self.assertTrue(len(crash_records) > 0)
            self.assertIsNotNone(crash_records[0].exc_info)

    async def test_crash_triggers_skip_notify(self):
        """Strategy crash triggers skip notification."""
        strats = [
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()
        discord_mock = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.discord_notify', discord_mock):

            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.side_effect = RuntimeError("boom")

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # Check that send_discord_webhook was called with a skip message
            discord_mock.send_discord_webhook.assert_called_once()
            call_arg = discord_mock.send_discord_webhook.call_args[0][0]
            self.assertIn("Iron Fly V1", call_arg)
            self.assertIn("crashed", call_arg)

    async def test_rejected_trade_notifies_and_continues(self):
        """Rejected trade triggers skip notification."""
        strats = [
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()
        discord_mock = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.discord_notify', discord_mock):

            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.return_value = {"status": "rejected", "reason": "parity... (after 3 attempts)"}

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # Check that a rejection notify was sent
            rejection_notifies = [
                call for call in discord_mock.send_discord_webhook.call_args_list
                if "rejected" in call[0][0].lower()
            ]
            self.assertTrue(len(rejection_notifies) > 0)

    async def test_no_legs_notifies_and_continues(self):
        """No legs found triggers skip notification."""
        strats = [
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()
        discord_mock = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.discord_notify', discord_mock):

            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.return_value = {"status": "no_legs", "reason": "Could not find suitable legs."}

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # First no_legs should have triggered a notify
            no_legs_notifies = [
                call for call in discord_mock.send_discord_webhook.call_args_list
                if "Could not find" in call[0][0]
            ]
            self.assertTrue(len(no_legs_notifies) > 0)

    async def test_jade_lizard_crash_isolated(self):
        """JL crash doesn't block 0DTE fly."""
        ok_result = {
            "status": "ok",
            "legs": _fly_legs(),
            "credit": 5.90,
            "width": 10.0,
            "spx_spot": 6607.0,
            "notes_extra": "",
        }

        strats = [
            {
                'name': 'JadeLizard_5DTE',
                'code': 'JL5',
                'type': 'jade_lizard',
                'target_dte': 5,
                'profit_target_pct': 0.25,
                'allowed_times': [time(15, 0)],
            },
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()
        discord_mock = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('jade_lizard.execute_jade_lizard', new_callable=AsyncMock) as mock_jl, \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.trade_logger.log_trade_entry') as mock_log, \
             patch('main.discord_notify', discord_mock):

            mock_jl.side_effect = RuntimeError("jl boom")
            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.return_value = ok_result

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # Fly should still log despite JL crash (JL crash isolated)
            self.assertEqual(mock_log.call_count, 1)
            # JL crash should have triggered a skip notify
            jl_notifies = [
                call for call in discord_mock.send_discord_webhook.call_args_list
                if "JadeLizard_5DTE" in call[0][0] and "crashed" in call[0][0].lower()
            ]
            self.assertTrue(len(jl_notifies) > 0)

    async def test_chain_none_notifies_eligible_strategies(self):
        """FIX 3: a chain-fetch failure surfaces a skip alert per eligible 0DTE
        strategy (and NOT for Jade Lizard, which doesn't use the shared chain)."""
        strats = [
            {'name': 'Iron Fly V1', 'code': 'IF-V1', 'type': 'iron_fly', 'target_delta': 0.50,
             'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
            {'name': 'JadeLizard_5DTE', 'code': 'JL5', 'type': 'jade_lizard', 'target_dte': 5,
             'profit_target_pct': 0.25, 'allowed_times': [time(15, 0)]},
        ]
        session = MagicMock()
        discord_mock = MagicMock()
        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('jade_lizard.execute_jade_lizard', new_callable=AsyncMock), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.discord_notify', discord_mock):
            mock_chain.return_value = None
            await main.execute_trade_cycle(session, trigger_time=time(15, 0))
            msgs = [c[0][0] for c in discord_mock.send_discord_webhook.call_args_list]
            self.assertTrue(any("Iron Fly V1" in m and "no SPX option chain" in m for m in msgs))
            self.assertFalse(any("JadeLizard_5DTE" in m for m in msgs))

    async def test_no_expiration_notifies_eligible_strategies(self):
        """FIX 3: a missing 0DTE expiration surfaces a skip alert per eligible strat."""
        strats = [
            {'name': 'Iron Fly V1', 'code': 'IF-V1', 'type': 'iron_fly', 'target_delta': 0.50,
             'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
        ]
        session = MagicMock()
        discord_mock = MagicMock()
        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.discord_notify', discord_mock):
            mock_chain.return_value = {None: []}
            mock_filter.return_value = []
            await main.execute_trade_cycle(session, trigger_time=time(15, 0))
            msgs = [c[0][0] for c in discord_mock.send_discord_webhook.call_args_list]
            self.assertTrue(any("Iron Fly V1" in m and "no 0DTE expiration" in m for m in msgs))

    async def test_malformed_config_is_isolated(self):
        """FIX 2: a config entry missing a required key isolates to that strategy and
        does NOT abort later strategies (in either the JL or 0DTE loop)."""
        ok_result = {
            "status": "ok", "legs": _fly_legs(), "credit": 5.90,
            "width": 10.0, "spx_spot": 6607.0, "notes_extra": "",
        }
        strats = [
            {'name': 'BadStrat', 'code': 'BAD', 'allowed_times': [time(15, 0)]},  # missing 'type'
            {'name': 'Iron Fly V1', 'code': 'IF-V1', 'type': 'iron_fly', 'target_delta': 0.50,
             'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
        ]
        session = MagicMock()
        discord_mock = MagicMock()
        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.strategy.fetch_spx_iv_rank', new_callable=AsyncMock) as mock_iv, \
             patch('main.strategy.get_spx_spot', new_callable=AsyncMock) as mock_spot, \
             patch('main.strategy.save_spx_price'), \
             patch('main._build_validated_trade', new_callable=AsyncMock) as mock_build, \
             patch('main.trade_logger.log_trade_entry') as mock_log, \
             patch('main.discord_notify', discord_mock):
            mock_chain.return_value = {None: []}
            mock_filter.return_value = [MagicMock()]
            mock_iv.return_value = 50.0
            mock_spot.return_value = 6607.0
            mock_build.return_value = ok_result
            await main.execute_trade_cycle(session, trigger_time=time(15, 0))
            # Good strat still logged despite BadStrat raising KeyError('type').
            self.assertEqual(mock_log.call_count, 1)
            msgs = [c[0][0] for c in discord_mock.send_discord_webhook.call_args_list]
            self.assertTrue(any("BadStrat" in m and "crashed" in m.lower() for m in msgs))


class TestChainFetchRetry(unittest.IsolatedAsyncioTestCase):
    """FIX 2: _fetch_chain_with_retry retries on transient failures."""

    async def test_chain_retry_then_success(self):
        """Fails twice, succeeds on third attempt."""
        chain_dict = {None: [MagicMock()]}

        session = MagicMock()

        with patch('main.strategy.fetch_spx_option_chain', new_callable=AsyncMock) as mock_fetch, \
             patch('main.asyncio.sleep', new_callable=AsyncMock):

            mock_fetch.side_effect = [
                TimeoutError(),
                TimeoutError(),
                chain_dict,
            ]

            result = await _fetch_chain_with_retry(session)

            self.assertEqual(result, chain_dict)
            self.assertEqual(mock_fetch.call_count, 3)

    async def test_chain_retry_exhausted_returns_none(self):
        """All attempts fail — returns None."""
        session = MagicMock()

        with patch('main.strategy.fetch_spx_option_chain', new_callable=AsyncMock) as mock_fetch, \
             patch('main.asyncio.sleep', new_callable=AsyncMock):

            mock_fetch.side_effect = TimeoutError()

            result = await _fetch_chain_with_retry(session)

            self.assertIsNone(result)
            self.assertEqual(mock_fetch.call_count, CHAIN_FETCH_ATTEMPTS)

    async def test_cycle_returns_when_chain_none(self):
        """When _fetch_chain_with_retry returns None, cycle exits early."""
        strats = [
            {
                'name': 'Iron Fly V1',
                'code': 'IF-V1',
                'type': 'iron_fly',
                'target_delta': 0.50,
                'profit_target_pct': 0.10,
                'wing_width': 10,
                'allowed_times': [time(15, 0)],
            },
        ]

        session = MagicMock()

        with patch('main.STRATEGY_CONFIGS', strats), \
             patch('main._is_trigger_time_allowed', return_value=True), \
             patch('main._fetch_chain_with_retry', new_callable=AsyncMock) as mock_chain, \
             patch('main.strategy.filter_for_0dte') as mock_filter, \
             patch('main.trade_logger.log_trade_entry') as mock_log, \
             patch('main.discord_notify', None):

            mock_chain.return_value = None

            await main.execute_trade_cycle(session, trigger_time=time(15, 0))

            # filter_for_0dte should NOT be called when chain is None
            mock_filter.assert_not_called()
            # log_trade_entry should NOT be called
            mock_log.assert_not_called()


class TestNotifySkipGuard(unittest.TestCase):
    """FIX 3: _notify_skip guards against notification failure."""

    def test_notify_skip_noop_when_module_none(self):
        """_notify_skip is no-op when discord_notify is None."""
        with patch('main.discord_notify', None):
            # Should not raise
            _notify_skip("Iron Fly V1", "some reason")

    def test_notify_skip_sends_string(self):
        """_notify_skip sends a string message via discord_notify."""
        discord_mock = MagicMock()

        with patch('main.discord_notify', discord_mock):
            _notify_skip("Iron Fly V1", "parity violation")

            discord_mock.send_discord_webhook.assert_called_once()
            call_arg = discord_mock.send_discord_webhook.call_args[0][0]
            self.assertIn("Iron Fly V1", call_arg)
            self.assertIn("parity violation", call_arg)
            self.assertIsInstance(call_arg, str)

    def test_notify_skip_swallows_webhook_error(self):
        """_notify_skip catches and logs notification failure; does not raise."""
        discord_mock = MagicMock()
        discord_mock.send_discord_webhook.side_effect = RuntimeError("net error")

        with patch('main.discord_notify', discord_mock):
            # Should not raise
            _notify_skip("Iron Fly V1", "some reason")


if __name__ == '__main__':
    unittest.main()
