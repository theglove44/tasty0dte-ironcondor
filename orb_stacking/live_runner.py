"""Slice 14 — Live adapter between OrbStackingEngine and the live bot.

Launched as asyncio.create_task from main.py at 14:30 UK.
Streams 5m SPX bars, feeds to OrbStackingEngine, prices and logs intents/skips.
Never raises — all exceptions caught and logged.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from tastytrade.instruments import OptionType
from tastytrade.market_data import get_market_data_by_type

from orb_stacking.engine import OrbStackingEngine
from orb_stacking.bar_fetcher import BarFetcher, trading_lookback_days
from orb_stacking.trade_intent import OrbTradeIntent, OrbSkipEvent

import strategy as strategy_mod
import monitor as monitor_mod
import logger as trade_logger

logger = logging.getLogger("trade")

TIER_TO_STRATEGY_NAME: dict[str, str] = {
    "HALF": "ORB-STACK-HALF",
    "NORMAL": "ORB-STACK-NORMAL",
    "PLUS": "ORB-STACK-PLUS",
    "DOUBLE": "ORB-STACK-DOUBLE",
}

TERMINAL_SKIP_REASONS = frozenset({"no_breakout_before_noon", "orb60_opposes_hard_exit"})


def warmup_engine(engine: OrbStackingEngine, history_bars: list) -> None:
    """Feed each history bar into engine._atr.update(bar). Do NOT call engine.on_closed_bar."""
    for bar in history_bars:
        engine._atr.update(bar)


def build_strike_map(options_0dte: list) -> dict:
    """
    Return {strike_float: {"put": option, "call": option}}.
    Uses OptionType.PUT / OptionType.CALL to determine side.
    Key is float(opt.strike_price).
    """
    strike_map = {}
    for opt in options_0dte:
        strike = float(opt.strike_price)
        if strike not in strike_map:
            strike_map[strike] = {}
        if opt.option_type == OptionType.CALL:
            strike_map[strike]["call"] = opt
        elif opt.option_type == OptionType.PUT:
            strike_map[strike]["put"] = opt
    return strike_map


async def price_legs(session, short_opt, long_opt) -> tuple:
    """
    Returns (short_price: float | None, long_price: float | None).
    Uses REST API pattern. Catches all exceptions, returns (None, None) on failure.
    """
    try:
        market_data = await strategy_mod._unwrap_awaitable(
            get_market_data_by_type(session, options=[short_opt.symbol, long_opt.symbol])
        )
        md_by_symbol = {md.symbol: md for md in market_data}

        short_md = md_by_symbol.get(short_opt.symbol)
        short_price = float(short_md.mark) if short_md and short_md.mark is not None else None

        long_md = md_by_symbol.get(long_opt.symbol)
        long_price = float(long_md.mark) if long_md and long_md.mark is not None else None

        return (short_price, long_price)
    except Exception as e:
        logger.error(f"price_legs error {type(e).__name__}: {e}")
        return (None, None)


def build_legs_dict(intent: OrbTradeIntent, short_opt, long_opt) -> dict:
    """
    Returns the 4-leg dict with short_call, long_call, short_put, long_put.
    Uses NONE strings for unused side (matching premium_popper.py pattern).
    Keys in each leg: symbol (streamer), occ_symbol (OCC), strike (float), delta (0), price (float).
    """
    none_leg = {'symbol': 'NONE', 'occ_symbol': 'NONE', 'strike': 0, 'delta': 0, 'price': 0}

    if intent.spread_side == "call":
        call_leg_short = {
            'symbol': short_opt.streamer_symbol,
            'occ_symbol': short_opt.symbol,
            'strike': float(short_opt.strike_price),
            'delta': 0,
            'price': 0
        }
        call_leg_long = {
            'symbol': long_opt.streamer_symbol,
            'occ_symbol': long_opt.symbol,
            'strike': float(long_opt.strike_price),
            'delta': 0,
            'price': 0
        }
        return {
            'short_call': call_leg_short,
            'long_call': call_leg_long,
            'short_put': none_leg,
            'long_put': none_leg,
        }
    else:  # intent.spread_side == "put"
        put_leg_short = {
            'symbol': short_opt.streamer_symbol,
            'occ_symbol': short_opt.symbol,
            'strike': float(short_opt.strike_price),
            'delta': 0,
            'price': 0
        }
        put_leg_long = {
            'symbol': long_opt.streamer_symbol,
            'occ_symbol': long_opt.symbol,
            'strike': float(long_opt.strike_price),
            'delta': 0,
            'price': 0
        }
        return {
            'short_call': none_leg,
            'long_call': none_leg,
            'short_put': put_leg_short,
            'long_put': put_leg_long,
        }


async def handle_trade_intent(session, intent: OrbTradeIntent, strike_map: dict) -> str | None:
    """
    Full logic: look up strikes, price via REST, validate credit > 0, log via log_trade_entry.
    Returns strategy_id if trade was successfully logged, None otherwise.
    """
    try:
        # Strategy ID and name — construct early so it can be returned on early exits
        strategy_name = TIER_TO_STRATEGY_NAME.get(intent.stack_tier, "ORB-STACK-UNKNOWN")
        strategy_id = f"{strategy_name}-{intent.timestamp.strftime('%H%M')}"

        # Look up options
        short_side = strike_map.get(intent.short_strike, {}).get(intent.spread_side)
        long_side = strike_map.get(intent.long_strike, {}).get(intent.spread_side)

        if not short_side or not long_side:
            logger.warning(
                f"ORB Stacking: strike {intent.short_strike}/{intent.long_strike} "
                f"{intent.spread_side} not found in chain"
            )
            return None

        # Price legs via REST
        short_price, long_price = await price_legs(session, short_side, long_side)
        if short_price is None or long_price is None:
            logger.warning(f"ORB Stacking: failed to price {intent.spread_side} spread")
            return None

        # Calculate credit (short - long)
        credit = short_price - long_price
        if credit <= 0:
            logger.warning(
                f"ORB Stacking: invalid credit {credit:.2f} "
                f"({intent.short_strike} {intent.spread_side} at {short_price:.2f} "
                f"vs {intent.long_strike} at {long_price:.2f})"
            )
            return None

        # Build legs dict
        legs = build_legs_dict(intent, short_side, long_side)

        # Spread width for buying power
        spread_width = abs(intent.short_strike - intent.long_strike)
        buying_power = round((spread_width - credit) * 100 * intent.contracts, 2)

        # Profit target and stop loss
        profit_target = credit * 0.5
        stop_loss = credit * 2.0

        # Fetch SPX spot and IV rank
        spx_spot = await strategy_mod.get_spx_spot(session)
        iv_rank = await strategy_mod.fetch_spx_iv_rank(session)

        # Build notes
        notes = (
            f"tier={intent.stack_tier} base={intent.base_tier} "
            f"dir={intent.direction} contracts={intent.contracts}"
        )

        # Log the trade
        trade_logger.log_trade_entry(
            legs=legs,
            credit=credit,
            buying_power=buying_power,
            profit_target=profit_target,
            iv_rank=iv_rank,
            strategy_name=strategy_name,
            strategy_id=strategy_id,
            notes=notes,
            stop_loss=stop_loss,
            short_delta=None,
            spx_spot=spx_spot
        )

        logger.info(
            f"ORB Stacking trade logged: {strategy_name} {intent.spread_side} "
            f"{intent.short_strike}/{intent.long_strike} credit={credit:.2f}"
        )

        return strategy_id

    except Exception as e:
        logger.error(f"handle_trade_intent error {type(e).__name__}: {e}")
        return None


async def run_orb_stacking(session) -> None:
    """
    Full ORB Stacking runner: fetch history, warm engine, subscribe to bars, process events.
    Never raises — all exceptions caught and logged.
    """
    try:
        logger.info("ORB Stacking: initializing engine and fetcher...")
        engine = OrbStackingEngine()
        fetcher = BarFetcher("SPX", "5m", lookback_days=trading_lookback_days())

        # Fetch and warm up history
        history_bars = await fetcher.fetch_history_with_retry(session)
        warmup_engine(engine, history_bars)

        # Fetch 0DTE chain and build strike map
        chain = await strategy_mod.fetch_spx_option_chain(session)
        options_0dte = strategy_mod.filter_for_0dte(chain)

        if not options_0dte:
            logger.error("ORB Stacking: no 0DTE options found, cannot run")
            return

        strike_map = build_strike_map(options_0dte)
        logger.info(f"ORB Stacking: ready with {len(options_0dte)} 0DTE options, {len(strike_map)} strikes")

        # Track logged trades for potential force-close on ORB60 oppose
        logged_strategy_ids: list[str] = []

        # Stream live bars and process events
        terminal = False
        async for bar in fetcher.stream_closed_bars(session):
            if terminal:
                break

            try:
                results = engine.on_closed_bar(bar)
                for result in results:
                    if isinstance(result, OrbTradeIntent):
                        if result.contracts == 0:
                            skip = OrbSkipEvent(
                                timestamp=result.timestamp,
                                reason="zero_contracts",
                                direction=result.direction,
                                stack_tier=result.stack_tier,
                                notes="contracts==0, not traded",
                            )
                            trade_logger.log_skip_event(skip)
                            logger.info("ORB Stacking skip (0 contracts)")
                            continue
                        logged_id = await handle_trade_intent(session, result, strike_map)
                        if logged_id:
                            logged_strategy_ids.append(logged_id)
                    elif isinstance(result, OrbSkipEvent):
                        trade_logger.log_skip_event(result)
                        logger.info(f"ORB Stacking skip: {result.reason}")
                        if result.reason == "orb60_opposes_hard_exit":
                            for sid in logged_strategy_ids:
                                monitor_mod.FORCE_CLOSE_REASONS[sid] = "orb60_opposes_hard_exit"
                            logger.info(f"ORB Stacking: ORB60 oppose, force-closing {logged_strategy_ids}")
                        if result.reason in TERMINAL_SKIP_REASONS:
                            terminal = True
            except Exception as e:
                logger.error(f"ORB Stacking bar error {type(e).__name__}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"ORB Stacking fatal error {type(e).__name__}: {e}", exc_info=True)
        if isinstance(e, BaseExceptionGroup):
            for i, sub in enumerate(e.exceptions):
                logger.error(
                    f"  ORB sub-exception[{i}]: {type(sub).__name__}: {sub}",
                    exc_info=(type(sub), sub, sub.__traceback__),
                )

    logger.info("ORB Stacking finished for session.")
