"""
Premium Popper ORB20 — 1st Breakout Strategy

Collects a 20-minute Opening Range (4 × 5-min candles from market open),
then watches for the first breakout candle close outside the range.
On breakout, enters a credit spread opposite the breakout direction.

Lifecycle (US DST active, UK still GMT):
  13:30–13:50 UK: Collect ORB (poll SPX spot price, build 5-min candles)
  13:50–16:00 UK: Monitor for breakout (5-min candle closes)
  On breakout:   Execute put credit spread (bullish) or call credit spread (bearish)
  16:00 UK:      Timeout if no breakout (noon ET)
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
import pytz

from tastytrade import Session
from tastytrade.instruments import OptionType

import strategy as strategy_mod
import logger as trade_logger

logger = logging.getLogger("0dte-popper")

UK_TZ = pytz.timezone('Europe/London')

# ORB parameters
ORB_CANDLE_COUNT = 4
ORB_CANDLE_MINUTES = 5
ORB_DURATION_MINUTES = ORB_CANDLE_COUNT * ORB_CANDLE_MINUTES  # 20 min

# Breakout parameters
EXPANSION_THRESHOLD = 0.10  # candle body >= 10% of ORB range
BREAKOUT_TIMEOUT = time(16, 0)  # noon ET = 16:00 UK (US DST active, UK still GMT)

# Trade parameters
TARGET_DELTA = 0.20
SPREAD_WIDTH = 5
MIN_CREDIT = 0.80
MAX_CREDIT = 1.50
PROFIT_TARGET_PCT = 0.50
STOP_LOSS_MULT = 2.0


def _now_uk():
    return datetime.now(UK_TZ)


def _candle_boundary(t: datetime, minutes: int = 5) -> datetime:
    """Round down to the nearest candle boundary."""
    floored_minute = (t.minute // minutes) * minutes
    return t.replace(minute=floored_minute, second=0, microsecond=0)


def _calculate_orb(candles: list[dict]) -> dict | None:
    """Calculate ORB high/low/range/bias from completed candles."""
    if len(candles) < ORB_CANDLE_COUNT:
        logger.warning(f"Only {len(candles)} candles collected, need {ORB_CANDLE_COUNT}")
        return None

    orb_high = max(c['high'] for c in candles)
    orb_low = min(c['low'] for c in candles)
    orb_range = orb_high - orb_low

    if orb_range <= 0:
        logger.warning("ORB range is zero or negative")
        return None

    # Bias from candle 4 close position within ORB
    last_close = candles[-1]['close']
    position = (last_close - orb_low) / orb_range

    if position >= 0.60:
        bias = 'bullish'
    elif position <= 0.40:
        bias = 'bearish'
    else:
        bias = 'neutral'

    orb = {
        'high': orb_high,
        'low': orb_low,
        'range': orb_range,
        'midpoint': (orb_high + orb_low) / 2,
        'bias': bias,
        'candles': candles,
    }
    logger.info(f"ORB calculated: high={orb_high:.2f}, low={orb_low:.2f}, "
                f"range={orb_range:.2f}, bias={bias}")
    return orb


def _check_breakout(candle: dict, orb: dict) -> dict | None:
    """Check if a candle close constitutes a breakout."""
    close = candle['close']
    body = abs(candle['close'] - candle['open'])
    orb_range = orb['range']

    # Expansion filter
    if body < orb_range * EXPANSION_THRESHOLD:
        return None

    # Bullish breakout
    if close > orb['high']:
        return {
            'direction': 'bullish',
            'candle': candle,
            'body': body,
            'expansion_ratio': body / orb_range,
        }

    # Bearish breakout
    if close < orb['low']:
        return {
            'direction': 'bearish',
            'candle': candle,
            'body': body,
            'expansion_ratio': body / orb_range,
        }

    return None


async def _poll_candles(session: Session, start_time: datetime,
                        end_time: datetime, candle_minutes: int = 5,
                        poll_interval: int = 3) -> list[dict]:
    """Poll SPX spot price and build OHLC candles.

    Uses get_spx_spot() which is reliable even when other DXLinkStreamers
    are active (avoids concurrent streamer conflicts).

    Returns list of completed candles between start_time and end_time.
    """
    candles = []
    current_candle = None
    current_boundary = _candle_boundary(start_time, candle_minutes)
    next_boundary = current_boundary + timedelta(minutes=candle_minutes)
    tick_count = 0

    while True:
        now = _now_uk()

        # Past end time — finalize any open candle and stop
        if now >= end_time:
            if current_candle and current_candle.get('open') is not None:
                candles.append(current_candle)
                logger.info(
                    f"Final candle #{len(candles)}: "
                    f"O={current_candle['open']:.2f} H={current_candle['high']:.2f} "
                    f"L={current_candle['low']:.2f} C={current_candle['close']:.2f}")
            break

        # Poll SPX price
        try:
            price = await strategy_mod.get_spx_spot(session, timeout_s=5, retries=1)
        except Exception as e:
            logger.warning(f"Poll failed: {type(e).__name__}: {e}")
            await asyncio.sleep(poll_interval)
            continue

        if price is None:
            logger.debug("SPX spot returned None, retrying...")
            await asyncio.sleep(poll_interval)
            continue

        tick_count += 1
        if tick_count == 1:
            logger.info(f"First SPX poll: {price:.2f}")

        # Rotate candle if we've crossed a boundary
        if now >= next_boundary:
            if current_candle and current_candle.get('open') is not None:
                candles.append(current_candle)
                logger.info(
                    f"Candle #{len(candles)} complete: "
                    f"O={current_candle['open']:.2f} H={current_candle['high']:.2f} "
                    f"L={current_candle['low']:.2f} C={current_candle['close']:.2f}")
            current_boundary = _candle_boundary(now, candle_minutes)
            next_boundary = current_boundary + timedelta(minutes=candle_minutes)
            current_candle = None

        # Initialize or update candle
        if current_candle is None:
            current_candle = {
                'open': price, 'high': price,
                'low': price, 'close': price,
                'start': current_boundary,
            }
        else:
            current_candle['high'] = max(current_candle['high'], price)
            current_candle['low'] = min(current_candle['low'], price)
            current_candle['close'] = price

        await asyncio.sleep(poll_interval)

    logger.info(f"Candle polling done: {len(candles)} candles from {tick_count} polls")
    return candles


async def _collect_opening_range(session: Session) -> dict | None:
    """Build ORB from 4 × 5-min candles starting at market open (13:30 UK)."""
    now = _now_uk()
    orb_start = now.replace(hour=13, minute=30, second=0, microsecond=0)
    orb_end = orb_start + timedelta(minutes=ORB_DURATION_MINUTES)

    # If we're past ORB window already, can't collect
    if now >= orb_end:
        logger.warning("Past ORB collection window. Cannot collect.")
        return None

    # Wait until ORB start if early
    if now < orb_start:
        wait_secs = (orb_start - now).total_seconds()
        logger.info(f"Waiting {wait_secs:.0f}s for ORB start (13:30 UK)")
        await asyncio.sleep(wait_secs)

    logger.info("Starting ORB collection (13:30-13:50 UK)...")
    candles = await _poll_candles(session, orb_start, orb_end,
                                  candle_minutes=ORB_CANDLE_MINUTES)

    logger.info(f"ORB collection complete: {len(candles)} candle(s)")
    return _calculate_orb(candles)


async def _monitor_for_breakout(session: Session, orb: dict) -> dict | None:
    """Watch 5-min candle closes for a breakout after ORB period.

    Uses polling via get_spx_spot() to avoid concurrent DXLinkStreamer conflicts.
    """
    now = _now_uk()
    monitor_start = now.replace(hour=13, minute=50, second=0, microsecond=0)
    timeout = now.replace(hour=BREAKOUT_TIMEOUT.hour, minute=BREAKOUT_TIMEOUT.minute,
                          second=0, microsecond=0)

    if now >= timeout:
        logger.info("Past breakout monitoring window.")
        return None

    # Wait for monitor start if needed
    if now < monitor_start:
        wait_secs = (monitor_start - now).total_seconds()
        await asyncio.sleep(wait_secs)

    logger.info(f"Monitoring for breakout (13:50-16:00 UK). "
                f"ORB: {orb['low']:.2f}-{orb['high']:.2f}, bias={orb['bias']}")

    current_candle = None
    candle_minutes = 5
    poll_interval = 3
    current_boundary = _candle_boundary(_now_uk(), candle_minutes)
    next_boundary = current_boundary + timedelta(minutes=candle_minutes)

    while True:
        now = _now_uk()

        if now >= timeout:
            logger.info("No breakout before 16:00 UK (noon ET). Timeout.")
            return None

        try:
            price = await strategy_mod.get_spx_spot(session, timeout_s=5, retries=1)
        except Exception as e:
            logger.warning(f"Breakout poll failed: {type(e).__name__}: {e}")
            await asyncio.sleep(poll_interval)
            continue

        if price is None:
            await asyncio.sleep(poll_interval)
            continue

        # Candle rotation — check breakout on completed candle
        if now >= next_boundary:
            if current_candle and current_candle.get('open') is not None:
                breakout = _check_breakout(current_candle, orb)
                if breakout:
                    breakout['time'] = now.strftime("%H:%M:%S")
                    logger.info(
                        f"BREAKOUT detected: {breakout['direction']} "
                        f"at {breakout['time']}, body={breakout['body']:.2f}, "
                        f"expansion={breakout['expansion_ratio']:.2f}")
                    return breakout
                else:
                    logger.info(
                        f"Candle closed: O={current_candle['open']:.2f} "
                        f"H={current_candle['high']:.2f} "
                        f"L={current_candle['low']:.2f} "
                        f"C={current_candle['close']:.2f} — no breakout")

            current_boundary = _candle_boundary(now, candle_minutes)
            next_boundary = current_boundary + timedelta(minutes=candle_minutes)
            current_candle = None

        # Update candle
        if current_candle is None:
            current_candle = {
                'open': price, 'high': price,
                'low': price, 'close': price,
                'start': current_boundary,
            }
        else:
            current_candle['high'] = max(current_candle['high'], price)
            current_candle['low'] = min(current_candle['low'], price)
            current_candle['close'] = price

        await asyncio.sleep(poll_interval)

    return None


async def _find_credit_spread_legs(session: Session, options_list: list,
                                    side: str, delta: float, width: float) -> dict | None:
    """Find legs for a credit spread.

    side: 'put' for put credit spread, 'call' for call credit spread
    Returns dict with short/long leg info, or None on failure.
    """
    greeks = await strategy_mod.get_greeks_for_chain(session, options_list)
    if not greeks:
        logger.error("No Greeks data for credit spread leg selection")
        return None

    calls, puts = strategy_mod._separate_calls_puts(options_list, greeks)

    if side == 'put':
        if not puts:
            logger.error("No puts available for put credit spread")
            return None
        # Sell ~delta put, buy put $width lower
        short_leg = min(puts, key=lambda x: abs(x['delta'] + delta))
        long_leg = min(puts, key=lambda p: abs(p['strike'] - (short_leg['strike'] - width)),
                       default=None)
        if not long_leg:
            logger.error("Could not find long put wing")
            return None
        return {'short': short_leg, 'long': long_leg, 'side': 'put'}

    elif side == 'call':
        if not calls:
            logger.error("No calls available for call credit spread")
            return None
        # Sell ~delta call, buy call $width higher
        short_leg = min(calls, key=lambda x: abs(x['delta'] - delta))
        long_leg = min(calls, key=lambda c: abs(c['strike'] - (short_leg['strike'] + width)),
                       default=None)
        if not long_leg:
            logger.error("Could not find long call wing")
            return None
        return {'short': short_leg, 'long': long_leg, 'side': 'call'}

    return None


async def _execute_trade(session: Session, breakout: dict, orb: dict) -> None:
    """Find credit spread legs, validate premium, and log trade."""
    chain = await strategy_mod.fetch_spx_option_chain(session)
    exp = strategy_mod.filter_for_0dte(chain)
    if not exp:
        logger.warning("No 0DTE expiration found. Cannot execute Premium Popper trade.")
        return

    # Bullish breakout → put credit spread (sell puts below market)
    # Bearish breakout → call credit spread (sell calls above market)
    if breakout['direction'] == 'bullish':
        side = 'put'
    else:
        side = 'call'

    spread = await _find_credit_spread_legs(session, exp, side, TARGET_DELTA, SPREAD_WIDTH)
    if not spread:
        logger.warning(f"Could not find {side} credit spread legs. Skipping.")
        return

    # Build 4-leg dict (NONE for unused side)
    none_leg = {'symbol': 'NONE', 'occ_symbol': 'NONE', 'strike': 0, 'delta': 0, 'price': 0}

    if side == 'put':
        legs = {
            'short_call': dict(none_leg),
            'long_call': dict(none_leg),
            'short_put': spread['short'],
            'long_put': spread['long'],
        }
    else:
        legs = {
            'short_call': spread['short'],
            'long_call': spread['long'],
            'short_put': dict(none_leg),
            'long_put': dict(none_leg),
        }

    # Fetch live prices for active legs
    active_legs = {k: v for k, v in legs.items() if v['symbol'] != 'NONE'}
    await strategy_mod._fetch_leg_prices(session, active_legs)
    # Copy prices back
    for k, v in active_legs.items():
        legs[k] = v

    short_price = legs[f'short_{side}']['price']
    long_price = legs[f'long_{side}']['price']

    if short_price <= 0 or long_price <= 0:
        logger.warning(f"Missing price data: short={short_price}, long={long_price}. Skipping.")
        return

    credit = round(short_price - long_price, 2)

    if credit < MIN_CREDIT:
        logger.info(f"Premium too low: ${credit:.2f} < ${MIN_CREDIT}. Skipping.")
        return
    if credit > MAX_CREDIT:
        logger.info(f"Premium too high: ${credit:.2f} > ${MAX_CREDIT}. Skipping.")
        return

    buying_power = (SPREAD_WIDTH - credit) * 100
    profit_target = credit * PROFIT_TARGET_PCT
    stop_loss = credit * STOP_LOSS_MULT

    iv_rank = await strategy_mod.fetch_spx_iv_rank(session)

    now = _now_uk()
    strategy_id = f"PP-ORB-{now.strftime('%H%M')}"

    notes = (f"0DTE Premium Popper | {breakout['direction']} breakout at {breakout['time']} | "
             f"ORB: {orb['low']:.0f}-{orb['high']:.0f} ({orb['bias']})")

    trade_logger.log_trade_entry(
        legs, credit, buying_power, profit_target, iv_rank,
        strategy_name="Premium Popper", strategy_id=strategy_id,
        notes=notes, stop_loss=stop_loss)

    logger.info(f"Premium Popper trade logged: {side} credit spread, "
                f"credit=${credit:.2f}, stop=${stop_loss:.2f}")


async def run_premium_popper(session: Session) -> None:
    """Main entry point — launched as asyncio background task from main.py."""
    logger.info("Premium Popper ORB20 starting...")

    try:
        # Phase A: Collect Opening Range
        orb = await _collect_opening_range(session)
        if not orb:
            logger.info("Premium Popper: ORB collection failed. Done for today.")
            return

        # Phase B: Monitor for Breakout
        breakout = await _monitor_for_breakout(session, orb)
        if not breakout:
            logger.info("Premium Popper: No valid breakout detected. Done for today.")
            return

        # Phase C: Execute Trade
        await _execute_trade(session, breakout, orb)

    except Exception as e:
        logger.error(f"Premium Popper error: {type(e).__name__}: {e}")

    logger.info("Premium Popper ORB20 finished.")
