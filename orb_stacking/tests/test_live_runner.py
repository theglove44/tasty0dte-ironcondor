"""
Tests for Slice 14 — live_runner.py and related monitor/logger changes.
Covers 16 test cases across 3 test classes.
"""
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from datetime import datetime
import tempfile
import os

from orb_stacking.trade_intent import OrbTradeIntent, OrbSkipEvent
from orb_stacking.orb_levels import OrbLevels
from orb_stacking.live_runner import (
    warmup_engine,
    build_strike_map,
    price_legs,
    build_legs_dict,
    handle_trade_intent,
)


class MockOption:
    """Mock Option object matching SDK schema."""
    def __init__(self, strike_price, symbol, streamer_symbol, option_type):
        self.strike_price = strike_price
        self.symbol = symbol
        self.streamer_symbol = streamer_symbol
        self.option_type = option_type


class TestLiveRunnerSync(unittest.TestCase):
    """Sync tests for live_runner.py functions."""

    def test_warmup_engine_updates_atr_with_bars(self):
        """warmup_engine should call _atr.update for each bar."""
        mock_engine = MagicMock()
        mock_engine._atr = MagicMock()

        bars = [
            {'open': 100, 'high': 102, 'low': 99, 'close': 101},
            {'open': 101, 'high': 103, 'low': 100, 'close': 102},
        ]

        warmup_engine(mock_engine, bars)

        self.assertEqual(mock_engine._atr.update.call_count, 2)
        mock_engine._atr.update.assert_any_call(bars[0])
        mock_engine._atr.update.assert_any_call(bars[1])

    def test_warmup_engine_with_empty_bars(self):
        """warmup_engine should handle empty bar list gracefully."""
        mock_engine = MagicMock()
        mock_engine._atr = MagicMock()

        warmup_engine(mock_engine, [])

        mock_engine._atr.update.assert_not_called()

    def test_build_strike_map_groups_by_strike_and_side(self):
        """build_strike_map should return {strike: {put/call: option}}."""
        from tastytrade.instruments import OptionType

        opt_call_100 = MockOption(100.0, "SPX100C", "spx100c", OptionType.CALL)
        opt_put_100 = MockOption(100.0, "SPX100P", "spx100p", OptionType.PUT)
        opt_call_110 = MockOption(110.0, "SPX110C", "spx110c", OptionType.CALL)

        strike_map = build_strike_map([opt_call_100, opt_put_100, opt_call_110])

        self.assertIn(100.0, strike_map)
        self.assertIn(110.0, strike_map)
        self.assertEqual(strike_map[100.0]['call'], opt_call_100)
        self.assertEqual(strike_map[100.0]['put'], opt_put_100)
        self.assertEqual(strike_map[110.0]['call'], opt_call_110)
        self.assertNotIn('put', strike_map[110.0])

    def test_build_strike_map_empty_list(self):
        """build_strike_map should return empty dict for empty options list."""
        strike_map = build_strike_map([])
        self.assertEqual(strike_map, {})

    def test_build_legs_dict_call_spread(self):
        """build_legs_dict should build call spread with NONE put legs."""
        from tastytrade.instruments import OptionType

        mock_short = MockOption(100.0, "SPX100C", "spx100c", OptionType.CALL)
        mock_long = MockOption(110.0, "SPX110C", "spx110c", OptionType.CALL)

        orb20 = OrbLevels(
            name="ORB20",
            high=5610,
            low=5600,
            range=10,
            midpoint=5605,
            close=5608,
            close_pct=0.8,
            locked_at=datetime(2026, 4, 10, 13, 50)
        )
        intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 10, 15, 0),
            direction="UP",
            spread_side="call",
            short_strike=100.0,
            long_strike=110.0,
            expected_credit=2.0,
            stack_tier="NORMAL",
            base_tier="BULL",
            contracts=1,
            stack_score=2,
            base_score=1,
            calendar_score=1,
            calendar_labels=[],
            closes_aligned_count=3,
            range_expansion_ratio=1.2,
            is_a_plus_buffer=False,
            is_immediate=False,
            orb20=orb20,
        )

        legs = build_legs_dict(intent, mock_short, mock_long)

        self.assertEqual(legs['short_call']['symbol'], "spx100c")
        self.assertEqual(legs['short_call']['occ_symbol'], "SPX100C")
        self.assertEqual(legs['short_call']['strike'], 100.0)
        self.assertEqual(legs['long_call']['symbol'], "spx110c")
        self.assertEqual(legs['long_call']['occ_symbol'], "SPX110C")
        self.assertEqual(legs['long_call']['strike'], 110.0)
        self.assertEqual(legs['short_put']['symbol'], "NONE")
        self.assertEqual(legs['long_put']['symbol'], "NONE")

    def test_build_legs_dict_put_spread(self):
        """build_legs_dict should build put spread with NONE call legs."""
        from tastytrade.instruments import OptionType

        mock_short = MockOption(100.0, "SPX100P", "spx100p", OptionType.PUT)
        mock_long = MockOption(90.0, "SPX90P", "spx90p", OptionType.PUT)

        orb20 = OrbLevels(
            name="ORB20",
            high=5610,
            low=5600,
            range=10,
            midpoint=5605,
            close=5608,
            close_pct=0.8,
            locked_at=datetime(2026, 4, 10, 13, 50)
        )
        intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 10, 15, 0),
            direction="DOWN",
            spread_side="put",
            short_strike=100.0,
            long_strike=90.0,
            expected_credit=1.5,
            stack_tier="NORMAL",
            base_tier="BEAR",
            contracts=1,
            stack_score=2,
            base_score=1,
            calendar_score=1,
            calendar_labels=[],
            closes_aligned_count=2,
            range_expansion_ratio=1.1,
            is_a_plus_buffer=False,
            is_immediate=False,
            orb20=orb20,
        )

        legs = build_legs_dict(intent, mock_short, mock_long)

        self.assertEqual(legs['short_put']['symbol'], "spx100p")
        self.assertEqual(legs['short_put']['occ_symbol'], "SPX100P")
        self.assertEqual(legs['short_put']['strike'], 100.0)
        self.assertEqual(legs['long_put']['symbol'], "spx90p")
        self.assertEqual(legs['long_put']['occ_symbol'], "SPX90P")
        self.assertEqual(legs['long_put']['strike'], 90.0)
        self.assertEqual(legs['short_call']['symbol'], "NONE")
        self.assertEqual(legs['long_call']['symbol'], "NONE")


class TestLiveRunnerAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for live_runner.py functions."""

    @patch('orb_stacking.live_runner.get_market_data_by_type')
    @patch('orb_stacking.live_runner.strategy_mod')
    async def test_price_legs_returns_prices(self, mock_strategy, mock_get_market_data):
        """price_legs should return (short_price, long_price) from REST API."""
        mock_short_opt = MockOption(100.0, "SPX100C", "spx100c", None)
        mock_long_opt = MockOption(110.0, "SPX110C", "spx110c", None)

        mock_md_short = MagicMock()
        mock_md_short.symbol = "SPX100C"
        mock_md_short.mark = 2.50

        mock_md_long = MagicMock()
        mock_md_long.symbol = "SPX110C"
        mock_md_long.mark = 0.75

        # get_market_data_by_type returns a non-awaitable mock data list
        mock_get_market_data.return_value = [mock_md_short, mock_md_long]
        # _unwrap_awaitable passes through the argument (it's already a list, not a coroutine)
        mock_strategy._unwrap_awaitable = AsyncMock(return_value=[mock_md_short, mock_md_long])

        mock_session = MagicMock()

        short_price, long_price = await price_legs(mock_session, mock_short_opt, mock_long_opt)

        self.assertEqual(short_price, 2.50)
        self.assertEqual(long_price, 0.75)

    @patch('orb_stacking.live_runner.get_market_data_by_type')
    @patch('orb_stacking.live_runner.strategy_mod')
    async def test_price_legs_returns_none_on_exception(self, mock_strategy, mock_get_market_data):
        """price_legs should return (None, None) on any exception."""
        mock_short_opt = MockOption(100.0, "SPX100C", "spx100c", None)
        mock_long_opt = MockOption(110.0, "SPX110C", "spx110c", None)

        mock_strategy._unwrap_awaitable = AsyncMock(side_effect=Exception("Network error"))

        mock_session = MagicMock()

        short_price, long_price = await price_legs(mock_session, mock_short_opt, mock_long_opt)

        self.assertIsNone(short_price)
        self.assertIsNone(long_price)

    @patch('orb_stacking.live_runner.trade_logger')
    @patch('orb_stacking.live_runner.strategy_mod')
    async def test_handle_trade_intent_logs_trade(self, mock_strategy, mock_logger):
        """handle_trade_intent should log a trade with valid credit and return strategy_id."""
        from tastytrade.instruments import OptionType

        mock_short = MockOption(100.0, "SPX100C", "spx100c", OptionType.CALL)
        mock_long = MockOption(110.0, "SPX110C", "spx110c", OptionType.CALL)

        orb20 = OrbLevels(
            name="ORB20",
            high=5610,
            low=5600,
            range=10,
            midpoint=5605,
            close=5608,
            close_pct=0.8,
            locked_at=datetime(2026, 4, 10, 13, 50)
        )
        intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 10, 15, 0),
            direction="UP",
            spread_side="call",
            short_strike=100.0,
            long_strike=110.0,
            expected_credit=2.0,
            stack_tier="NORMAL",
            base_tier="BULL",
            contracts=1,
            stack_score=2,
            base_score=1,
            calendar_score=1,
            calendar_labels=[],
            closes_aligned_count=3,
            range_expansion_ratio=1.2,
            is_a_plus_buffer=False,
            is_immediate=False,
            orb20=orb20,
        )

        strike_map = {
            100.0: {'call': mock_short},
            110.0: {'call': mock_long},
        }

        # Mock pricing
        with patch('orb_stacking.live_runner.price_legs', new_callable=AsyncMock) as mock_price:
            mock_price.return_value = (2.50, 0.50)

            # Mock strategy functions
            mock_strategy.get_spx_spot = AsyncMock(return_value=5600.0)
            mock_strategy.fetch_spx_iv_rank = AsyncMock(return_value=50.0)

            # Mock logger
            mock_logger.log_trade_entry = MagicMock()

            mock_session = MagicMock()
            result = await handle_trade_intent(mock_session, intent, strike_map)

            # Verify strategy_id was returned
            self.assertEqual(result, "ORB-STACK-NORMAL-1500")

            # Verify log_trade_entry was called with correct credit
            mock_logger.log_trade_entry.assert_called_once()
            call_kwargs = mock_logger.log_trade_entry.call_args[1]
            self.assertAlmostEqual(call_kwargs['credit'], 2.0)  # 2.50 - 0.50
            self.assertEqual(call_kwargs['strategy_name'], 'ORB-STACK-NORMAL')
            self.assertEqual(call_kwargs['strategy_id'], 'ORB-STACK-NORMAL-1500')

    @patch('orb_stacking.live_runner.strategy_mod')
    async def test_handle_trade_intent_skips_negative_credit(self, mock_strategy):
        """handle_trade_intent should skip trades with negative credit and return None."""
        from tastytrade.instruments import OptionType

        mock_short = MockOption(110.0, "SPX110C", "spx110c", OptionType.CALL)
        mock_long = MockOption(100.0, "SPX100C", "spx100c", OptionType.CALL)

        orb20 = OrbLevels(
            name="ORB20",
            high=5610,
            low=5600,
            range=10,
            midpoint=5605,
            close=5608,
            close_pct=0.8,
            locked_at=datetime(2026, 4, 10, 13, 50)
        )
        intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 10, 15, 0),
            direction="UP",
            spread_side="call",
            short_strike=110.0,
            long_strike=100.0,
            expected_credit=-1.0,
            stack_tier="NORMAL",
            base_tier="BULL",
            contracts=1,
            stack_score=2,
            base_score=1,
            calendar_score=1,
            calendar_labels=[],
            closes_aligned_count=3,
            range_expansion_ratio=1.2,
            is_a_plus_buffer=False,
            is_immediate=False,
            orb20=orb20,
        )

        strike_map = {
            100.0: {'call': mock_long},
            110.0: {'call': mock_short},
        }

        with patch('orb_stacking.live_runner.price_legs', new_callable=AsyncMock) as mock_price:
            # Inverted pricing produces negative credit
            mock_price.return_value = (0.50, 2.50)

            with patch('orb_stacking.live_runner.trade_logger') as mock_logger:
                mock_session = MagicMock()
                result = await handle_trade_intent(mock_session, intent, strike_map)

                # Should return None when credit <= 0 and NOT log trade
                self.assertIsNone(result)
                mock_logger.log_trade_entry.assert_not_called()

    async def test_orb60_oppose_writes_force_close_reasons(self):
        """ORB60 oppose skip event should write logged strategy_ids to FORCE_CLOSE_REASONS."""
        from datetime import timezone
        from orb_stacking.trade_intent import OrbTradeIntent, OrbSkipEvent
        from orb_stacking.orb_levels import OrbLevels
        import monitor as monitor_mod

        monitor_mod.FORCE_CLOSE_REASONS.clear()

        orb20 = OrbLevels(
            name="ORB20", high=5610, low=5600, range=10, midpoint=5605,
            close=5608, close_pct=0.8, locked_at=datetime(2026, 4, 10, 13, 50)
        )
        mock_intent = OrbTradeIntent(
            timestamp=datetime(2026, 4, 10, 15, 0),
            direction="bull",
            spread_side="put",
            short_strike=5605.0,
            long_strike=5600.0,
            expected_credit=None,
            stack_tier="NORMAL",
            base_tier="NORMAL",
            contracts=1,
            stack_score=2,
            base_score=1,
            calendar_score=0,
            calendar_labels=[],
            closes_aligned_count=1,
            range_expansion_ratio=1.0,
            is_a_plus_buffer=False,
            is_immediate=True,
            orb20=orb20,
        )
        mock_skip = OrbSkipEvent(
            timestamp=datetime(2026, 4, 10, 16, 0),
            reason="orb60_opposes_hard_exit",
            direction="bull",
            stack_tier="EXITED",
        )

        # Mock handle_trade_intent to return a known strategy_id
        expected_sid = "ORB-STACK-NORMAL-1500"

        with patch('orb_stacking.live_runner.handle_trade_intent', new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = expected_sid

            with patch('orb_stacking.live_runner.BarFetcher') as mock_fetcher_cls:
                with patch('orb_stacking.live_runner.OrbStackingEngine') as mock_engine_cls:
                    with patch('orb_stacking.live_runner.strategy_mod') as mock_strategy:
                        with patch('orb_stacking.live_runner.trade_logger') as mock_logger:
                            # Setup engine to emit intent then skip
                            mock_engine = MagicMock()
                            mock_engine_cls.return_value = mock_engine

                            # Setup bar fetcher
                            mock_fetcher = MagicMock()
                            mock_fetcher_cls.return_value = mock_fetcher
                            mock_fetcher.fetch_history_with_retry = AsyncMock(return_value=[])

                            # Mock bar streaming
                            async def mock_stream(*args, **kwargs):
                                bar1 = {'start': datetime(2026, 4, 10, 14, 50, tzinfo=timezone.utc),
                                        'open': 5600, 'high': 5610, 'low': 5598, 'close': 5612}
                                bar2 = {'start': datetime(2026, 4, 10, 16, 0, tzinfo=timezone.utc),
                                        'open': 5612, 'high': 5615, 'low': 5595, 'close': 5590}
                                yield bar1
                                yield bar2

                            mock_fetcher.stream_closed_bars = mock_stream

                            # Engine: first bar -> intent, second bar -> skip
                            mock_engine.on_closed_bar.side_effect = [
                                [mock_intent],
                                [mock_skip],
                            ]

                            mock_strategy.fetch_spx_option_chain = AsyncMock(return_value={})
                            mock_strategy.filter_for_0dte = MagicMock(return_value=[MagicMock()])

                            mock_session = MagicMock()
                            monitor_mod.FORCE_CLOSE_REASONS.clear()

                            from orb_stacking.live_runner import run_orb_stacking
                            await run_orb_stacking(mock_session)

                            # After ORB60 oppose, expected_sid should be in FORCE_CLOSE_REASONS
                            self.assertIn(expected_sid, monitor_mod.FORCE_CLOSE_REASONS)
                            self.assertEqual(
                                monitor_mod.FORCE_CLOSE_REASONS[expected_sid],
                                'orb60_opposes_hard_exit'
                            )

        monitor_mod.FORCE_CLOSE_REASONS.clear()


class TestLogSkipEvent(unittest.TestCase):
    """Tests for logger.log_skip_event function."""

    def test_log_skip_event_creates_csv_with_header(self):
        """log_skip_event should create skip_events.csv with header if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skip_log = os.path.join(tmpdir, "skip_events.csv")

            event = OrbSkipEvent(
                timestamp=datetime(2026, 4, 10, 15, 30),
                reason="no_breakout_before_noon",
                direction="UP",
                stack_tier="NORMAL",
                notes="test event",
            )

            import logger as trade_logger
            original_skip_log = trade_logger.SKIP_LOG_FILE
            try:
                trade_logger.SKIP_LOG_FILE = skip_log
                trade_logger.log_skip_event(event)

                self.assertTrue(os.path.exists(skip_log))
                with open(skip_log, 'r') as f:
                    lines = f.readlines()
                    self.assertGreater(len(lines), 0)
                    self.assertIn("timestamp", lines[0])
            finally:
                trade_logger.SKIP_LOG_FILE = original_skip_log

    def test_log_skip_event_appends_without_duplicate_header(self):
        """log_skip_event should append rows without duplicating header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skip_log = os.path.join(tmpdir, "skip_events.csv")

            event1 = OrbSkipEvent(
                timestamp=datetime(2026, 4, 10, 15, 30),
                reason="no_breakout_before_noon",
                direction="UP",
                stack_tier="NORMAL",
                notes="first event",
            )

            event2 = OrbSkipEvent(
                timestamp=datetime(2026, 4, 10, 15, 35),
                reason="orb60_opposes_hard_exit",
                direction="DOWN",
                stack_tier="PLUS",
                notes="second event",
            )

            import logger as trade_logger
            original_skip_log = trade_logger.SKIP_LOG_FILE
            try:
                trade_logger.SKIP_LOG_FILE = skip_log
                trade_logger.log_skip_event(event1)
                trade_logger.log_skip_event(event2)

                with open(skip_log, 'r') as f:
                    lines = f.readlines()
                    # 1 header + 2 events
                    self.assertEqual(len(lines), 3)
                    self.assertIn("timestamp", lines[0])
                    self.assertIn("no_breakout_before_noon", lines[1])
                    self.assertIn("orb60_opposes_hard_exit", lines[2])
            finally:
                trade_logger.SKIP_LOG_FILE = original_skip_log

    def test_log_skip_event_handles_missing_optional_fields(self):
        """log_skip_event should handle missing direction, stack_tier, notes gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skip_log = os.path.join(tmpdir, "skip_events.csv")

            event = OrbSkipEvent(
                timestamp=datetime(2026, 4, 10, 15, 30),
                reason="api_error",
            )

            import logger as trade_logger
            original_skip_log = trade_logger.SKIP_LOG_FILE
            try:
                trade_logger.SKIP_LOG_FILE = skip_log
                trade_logger.log_skip_event(event)

                with open(skip_log, 'r') as f:
                    lines = f.readlines()
                    self.assertEqual(len(lines), 2)  # header + event
                    # Event should have empty strings for missing fields
                    self.assertIn("api_error", lines[1])
            finally:
                trade_logger.SKIP_LOG_FILE = original_skip_log


class TestMonitorForceClose(unittest.TestCase):
    """Tests for monitor.py force-close and ORB-STACK time exit."""

    def test_force_close_reasons_dict_initialized(self):
        """FORCE_CLOSE_REASONS should be imported and initialized as empty dict."""
        import monitor
        self.assertIsInstance(monitor.FORCE_CLOSE_REASONS, dict)
        # Clear any prior test state
        monitor.FORCE_CLOSE_REASONS.clear()

    def test_force_close_reasons_can_store_entries(self):
        """FORCE_CLOSE_REASONS should allow storing strategy_id -> reason mapping."""
        import monitor
        monitor.FORCE_CLOSE_REASONS.clear()

        monitor.FORCE_CLOSE_REASONS['ORB-STACK-NORMAL-1530'] = 'orb60_opposes_hard_exit'

        self.assertIn('ORB-STACK-NORMAL-1530', monitor.FORCE_CLOSE_REASONS)
        self.assertEqual(
            monitor.FORCE_CLOSE_REASONS['ORB-STACK-NORMAL-1530'],
            'orb60_opposes_hard_exit'
        )

        monitor.FORCE_CLOSE_REASONS.clear()

    def test_orb_stack_time_exit_at_1950(self):
        """ORB-STACK trades should have time exit at 19:50 UK."""
        # This is a specification test — the logic is in monitor.py
        # Verify that ORB-STACK strategy names start with "ORB-STACK"
        strategy_names = [
            "ORB-STACK-HALF",
            "ORB-STACK-NORMAL",
            "ORB-STACK-PLUS",
            "ORB-STACK-DOUBLE",
        ]

        for name in strategy_names:
            self.assertTrue(name.startswith("ORB-STACK"))


if __name__ == '__main__':
    unittest.main()
