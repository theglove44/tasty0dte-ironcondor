#!/usr/bin/env python3
"""
Tasty0DTE: Simple, Resilient 0DTE Iron Condor/Fly Trader

Design principles:
- One Session at startup, never recreate
- SDK handles token refresh automatically
- Network errors → log and continue (don't crash)
- Positions stored in CSV (persistent across restarts)
"""

import os
import asyncio
import logging
import pytz
from datetime import datetime, time
from pathlib import Path
from dotenv import load_dotenv
from tastytrade import Session

import strategy
import monitor
import logger as trade_logger
from project_paths import TRADE_LOG
from orb_stacking.live_runner import run_orb_stacking

try:
    from local import discord_notify
except Exception:
    discord_notify = None

# === LOGGING ===
Path(TRADE_LOG).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(TRADE_LOG),
        logging.StreamHandler()
    ]
)
logging.getLogger("tastytrade").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger("0dte-trader")

# === ENTRY-RELIABILITY RETRY POLICY (2026-06-05) ===
# At the 15:00 open, REST option marks can be momentarily stale, tripping the
# put-call-parity / max-credit guards in strategy.validate_credit_sanity.
# Every is_valid=False from that guard is a stale-mark artifact (see its
# docstring), so we re-fetch FRESH marks (re-call the finder) + a fresh spot and
# re-validate up to PARITY_RETRY_ATTEMPTS times before giving up.
PARITY_RETRY_ATTEMPTS = 3        # total validation attempts per strategy
PARITY_RETRY_DELAY_S = 6         # seconds between retries (let marks refresh)

# Shared 0DTE chain fetch is a single point of failure for the whole 0DTE loop;
# give it a few attempts before conceding there is nothing to trade.
CHAIN_FETCH_ATTEMPTS = 3
CHAIN_FETCH_DELAY_S = 3

load_dotenv()

# === STRATEGY CONFIGS ===
# Note: IC-20D-1500 removed (2026-02-11) - 88% win rate but negative P/L over 34 trades
STRATEGY_CONFIGS = [
    # Iron Flies (CSV-derived, full history -> 2026-06-03): V1 +$53.60/85 t=4.42,
    # V2 +$40.59/85 t=2.73, V3 +$25.55/79, V4 +$10.76/74. All positive; ~$120 BP each.
    {'name': "Iron Fly V1", 'code': "IF-V1", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
    {'name': "Iron Fly V2", 'code': "IF-V2", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
    {'name': "Iron Fly V3", 'code': "IF-V3", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 30)]},
    {'name': "Iron Fly V4", 'code': "IF-V4", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(15, 30)]},
    # Jade Lizard: short put + bear call spread, 25% PT. +$77.95/36 closed, 100% WR but
    # downside UNSAMPLED (0 losses; undefended ITM risk) — kept but monitor closely.
    {'name': "JadeLizard_5DTE", 'code': "JL5", 'type': 'jade_lizard', 'target_dte': 5, 'profit_target_pct': 0.25, 'allowed_times': [time(15, 0)]},
    {'name': "JadeLizard_7DTE", 'code': "JL7", 'type': 'jade_lizard', 'target_dte': 7, 'profit_target_pct': 0.25, 'allowed_times': [time(15, 0)]},
    {'name': "JadeLizard_10DTE", 'code': "JL10", 'type': 'jade_lizard', 'target_dte': 10, 'profit_target_pct': 0.25, 'allowed_times': [time(15, 0)]},

    # ===== DISABLED 2026-06-05 (performance trim — see analysis/REPORT_2026-06-04.md) =====
    # Dynamic 0DTE: net-NEGATIVE since April (-$21.70 Apr-Jun), payoff 0.29, ~$1,465 BP,
    #   no statistical edge (lifetime +$5.23/57, t=0.16). Also on the contended 15:00 slot.
    #   Re-enable = uncomment this dict.
    # {'name': "Dynamic 0DTE", 'code': "DY-0D", 'type': 'dynamic_0dte',
    #  'allowed_times': [time(15, 0)],
    #  'profit_target_pct': 0.20,
    #  'move_threshold': -0.1,
    #  'condor_delta': 0.20, 'condor_wing_width': 20,
    #  'fly_delta': 0.50, 'fly_wing_width': 10},
    # Premium Popper: retired ~2026-04-09 (replaced by ORB Stacking); 0 trades since.
    # {'name': "Premium Popper", 'code': "PP-ORB", 'type': 'premium_popper',
    #  'allowed_times': [time(13, 30)],
    #  'profit_target_pct': 0.50},
    # (ORB Stacking launches separately in the main loop, not here — disabled there too.)

    # Removed 2026-03-22 after performance review (P/L CSV-corrected 2026-06-04):
    # - 20 Delta IC: -$54.68/146, payoff 0.09 despite 89.7% WR
    # - 30 Delta IC: -$45.88/171
    # - Gap Filter 20D: -$60.56/18, catastrophic tail losses
]


def _is_trigger_time_allowed(allowed_times, trigger_time):
    if not allowed_times or not trigger_time:
        return True
    return any(
        t.hour == trigger_time.hour and t.minute == trigger_time.minute
        for t in allowed_times
    )


def _build_strategy_id(strategy_name, trigger_time):
    t_code = trigger_time.strftime("%H%M") if trigger_time else "0000"
    strategy_code = "UNK"
    for cfg in STRATEGY_CONFIGS:
        if cfg['name'] in strategy_name:
            strategy_code = cfg['code']
            break
    return f"{strategy_code}-{t_code}"


def _notify_skip(strat_name: str, reason: str) -> None:
    """Best-effort Discord alert that a strategy was skipped this cycle.

    FIX 3 (2026-06-05): entry skips were previously silent. Surfaces every skip
    (validation rejection, missing legs, leg-find error, or strategy crash) as a
    guarded Discord message. No-op if discord_notify is None; wrapped in
    try/except so a notification failure NEVER aborts the trade cycle.
    """
    if discord_notify is None:
        return
    try:
        discord_notify.send_discord_webhook(
            f":warning: **{strat_name}** skipped entry — {reason}"
        )
    except Exception as e:
        logger.warning(f"[{strat_name}] Skip notification failed: {type(e).__name__}: {e}")


def _notify_0dte_cycle_skip(trigger_time: time, reason: str) -> None:
    """Alert that the WHOLE 0DTE cycle was skipped (no chain / no expiration).

    FIX 3 (2026-06-05): a failed shared chain fetch or a missing 0DTE expiry skips
    EVERY eligible 0DTE strategy at once (the Thu-2026-06-04 batch-failure mode).
    Surface one skip alert per eligible strategy for this trigger time so the
    batch-level miss isn't silent. Jade Lizard / Premium Popper are excluded —
    they don't depend on the shared 0DTE chain.
    """
    for strat in STRATEGY_CONFIGS:
        if strat.get('type') in ('jade_lizard', 'premium_popper'):
            continue
        if _is_trigger_time_allowed(strat.get('allowed_times'), trigger_time):
            _notify_skip(strat.get('name', 'Unknown strategy'), reason)


async def _fetch_chain_with_retry(session: Session):
    """Fetch the SPX option chain, retrying transient failures (FIX 2).

    Returns the chain on success, or None if every attempt failed (a legitimate
    "nothing to trade" signal — caller logs and returns).
    """
    for attempt in range(1, CHAIN_FETCH_ATTEMPTS + 1):
        try:
            return await strategy.fetch_spx_option_chain(session)
        except Exception as e:
            logger.warning(
                f"Chain fetch attempt {attempt}/{CHAIN_FETCH_ATTEMPTS} failed: "
                f"{type(e).__name__}: {e}"
            )
            if attempt < CHAIN_FETCH_ATTEMPTS:
                await asyncio.sleep(CHAIN_FETCH_DELAY_S)
    logger.error(f"Chain fetch failed after {CHAIN_FETCH_ATTEMPTS} attempts.")
    return None


async def _build_validated_trade(session: Session, strat: dict, exp: list):
    """Build a sanity-validated trade for one strategy, retrying with FRESH marks.

    FIX 1 (2026-06-05): validate_credit_sanity can reject an entry when REST marks
    are momentarily stale at the open. Both failure modes are stale-mark
    artifacts, so we re-call the public leg finder (re-fetches Greeks + fresh REST
    prices and re-selects current ATM) and re-fetch the SPX spot, then recompute
    credit/width and re-validate — up to PARITY_RETRY_ATTEMPTS times.

    Returns one of:
      {"status":"ok","legs":dict,"credit":float,"width":float,"spx_spot":float|None,"notes_extra":str}
      {"status":"no_legs","reason":str}     # finder returned None (not retried)
      {"status":"rejected","reason":str}    # still invalid after N attempts
    """
    strat_name = strat['name']
    strat_type = strat['type']
    target_delta = strat.get('target_delta', 0)

    async def _select_legs():
        notes_extra = ""
        if strat_type == 'iron_condor':
            legs = await strategy.find_iron_condor_legs(session, exp, target_delta=target_delta)
        elif strat_type == 'iron_fly':
            wing_width = strat.get('wing_width', 10)
            legs = await strategy.find_iron_fly_legs(session, exp, target_delta=target_delta, wing_width=wing_width)
        elif strat_type == 'dynamic_0dte':
            move_data = await strategy.get_spx_30min_move(session)
            if not move_data:
                logger.warning(f"[{strat_name}] Could not fetch 30-min move.")
                return None, ""
            change_pct = move_data['change_pct']
            threshold = strat.get('move_threshold', -0.1)
            if change_pct > threshold:
                selected = "IC"
                legs = await strategy.find_iron_condor_legs(session, exp, target_delta=strat['condor_delta'])
            else:
                selected = "IF"
                legs = await strategy.find_iron_fly_legs(session, exp, target_delta=strat['fly_delta'], wing_width=strat['fly_wing_width'])
            notes_extra = f"30min: {change_pct:+.2f}% → {selected}"
            logger.info(f"[{strat_name}] SPX 30-min move: {change_pct:+.2f}% → Selected: {selected}")
        else:
            legs = None
        return legs, notes_extra

    last_reason = "validation failed"
    for attempt in range(1, PARITY_RETRY_ATTEMPTS + 1):
        legs, notes_extra = await _select_legs()
        if not legs:
            return {"status": "no_legs", "reason": "Could not find suitable legs."}
        credit = (legs['short_call']['price'] + legs['short_put']['price']) - \
                 (legs['long_call']['price'] + legs['long_put']['price'])
        call_width = abs(float(legs['short_call']['strike']) - float(legs['long_call']['strike']))
        put_width = abs(float(legs['short_put']['strike']) - float(legs['long_put']['strike']))
        width = max(call_width, put_width)
        spx_spot = await strategy.get_spx_spot(session)
        is_valid, reason = strategy.validate_credit_sanity(legs, credit, width, spx_spot, strat_name)
        if is_valid:
            return {"status": "ok", "legs": legs, "credit": credit, "width": width,
                    "spx_spot": spx_spot, "notes_extra": notes_extra}
        last_reason = reason
        logger.warning(f"[{strat_name}] Sanity check failed (attempt {attempt}/{PARITY_RETRY_ATTEMPTS}): {reason}")
        if attempt < PARITY_RETRY_ATTEMPTS:
            await asyncio.sleep(PARITY_RETRY_DELAY_S)
    return {"status": "rejected", "reason": f"{last_reason} (after {PARITY_RETRY_ATTEMPTS} attempts)"}


async def execute_trade_cycle(session: Session, trigger_time: time = None):
    """Execute one trade cycle for all strategies at the given trigger time.

    Resilience (2026-06-05): FIX 1 per-strategy validation retries with fresh
    marks (_build_validated_trade); FIX 2 each Jade Lizard and 0DTE iteration is
    isolated so one failure can't skip later strategies, and the shared chain
    fetch is retried (_fetch_chain_with_retry); FIX 3 every skip is surfaced via
    _notify_skip.
    """
    logger.info(f"Starting trade cycle for {trigger_time}...")

    from jade_lizard import execute_jade_lizard
    for strat in STRATEGY_CONFIGS:
        # .get so a malformed config entry (missing 'type') is simply skipped here
        # and isolated/alerted by the 0DTE loop below, not crashing the JL loop.
        if strat.get('type') != 'jade_lizard':
            continue
        allowed_times = strat.get('allowed_times')
        if not _is_trigger_time_allowed(allowed_times, trigger_time):
            continue
        try:
            await execute_jade_lizard(
                session=session,
                target_dte=strat['target_dte'],
                strategy_name=strat['name'],
                strategy_id=strat.get('code', 'JL'),
                profit_target_pct=strat.get('profit_target_pct', 0.25),
                discord_notify=discord_notify,
            )
        except Exception as e:
            logger.error(f"[{strat['name']}] Strategy crashed: {type(e).__name__}: {e}", exc_info=True)
            _notify_skip(strat['name'], f"crashed: {type(e).__name__}: {e}")
            continue

    chain = await _fetch_chain_with_retry(session)
    if chain is None:
        logger.warning("No SPX option chain after retries. Skipping 0DTE cycle.")
        _notify_0dte_cycle_skip(trigger_time, "no SPX option chain after retries")
        return
    exp = strategy.filter_for_0dte(chain)
    if not exp:
        logger.warning("No 0DTE expiration found. Skipping 0DTE cycle.")
        _notify_0dte_cycle_skip(trigger_time, "no 0DTE expiration found")
        return

    iv_rank = await strategy.fetch_spx_iv_rank(session)

    spx_spot = await strategy.get_spx_spot(session, timeout_s=5)
    if spx_spot:
        strategy.save_spx_price(spx_spot)

    for strat in STRATEGY_CONFIGS:
        # FIX 2: the try wraps the config reads too — a malformed STRATEGY_CONFIGS
        # entry (missing 'type'/'profit_target_pct') must isolate to this strategy,
        # not abort the whole 0DTE loop.
        strat_name = strat.get('name', 'Unknown strategy')
        try:
            strat_type = strat['type']
            if strat_type == 'premium_popper':
                continue
            if strat_type == 'jade_lizard':
                continue
            profit_target_pct = strat['profit_target_pct']
            allowed_times = strat.get('allowed_times')
            if not _is_trigger_time_allowed(allowed_times, trigger_time):
                continue
            logger.info(f"Executing: {strat_name} (Delta {strat.get('target_delta', 0)})")
            result = await _build_validated_trade(session, strat, exp)
            if result["status"] == "no_legs":
                logger.warning(f"[{strat_name}] {result['reason']}")
                _notify_skip(strat_name, result["reason"])
                continue
            if result["status"] == "rejected":
                logger.warning(f"[{strat_name}] REJECTED trade: {result['reason']}. Skipping.")
                _notify_skip(strat_name, f"rejected: {result['reason']}")
                continue
            legs = result["legs"]
            credit = result["credit"]
            width = result["width"]
            spx_spot = result["spx_spot"]
            notes_extra = result["notes_extra"]
            risk = width - credit
            bp = risk * 100
            profit_target = credit * profit_target_pct
            strategy_id = _build_strategy_id(strat_name, trigger_time)
            short_call_delta = abs(legs['short_call'].get('delta', 0))
            short_put_delta = abs(legs['short_put'].get('delta', 0))
            short_delta = max(short_call_delta, short_put_delta)
            notes = f"0DTE {strat_name} | {notes_extra}" if notes_extra else None
            trade_logger.log_trade_entry(legs, credit, bp, profit_target, iv_rank,
                                         strategy_name=strat_name, strategy_id=strategy_id,
                                         notes=notes, short_delta=short_delta, spx_spot=spx_spot)
            logger.info(f"[{strat_name}] Trade logged. Credit: ${credit:.2f}, IV Rank: {iv_rank}")
            if discord_notify:
                try:
                    credit_pct = (credit / width) * 100 if width > 0 else 0
                    profit_target_debit = credit - profit_target
                    payload = discord_notify.format_trade_open_payload(
                        strategy_name=strat_name,
                        short_call_symbol=legs['short_call']['symbol'],
                        long_call_symbol=legs['long_call']['symbol'],
                        short_put_symbol=legs['short_put']['symbol'],
                        long_put_symbol=legs['long_put']['symbol'],
                        credit=float(credit),
                        profit_target=float(profit_target),
                        profit_target_debit=profit_target_debit,
                        wing_width=width,
                        credit_pct=credit_pct,
                        spx_spot=spx_spot,
                        iv_rank=iv_rank,
                    )
                    discord_notify.send_discord_webhook(payload)
                except Exception as e:
                    logger.warning(f"[{strat_name}] Notification failed: {e}")
        except Exception as e:
            logger.error(f"[{strat_name}] Strategy crashed: {type(e).__name__}: {e}", exc_info=True)
            _notify_skip(strat_name, f"crashed: {type(e).__name__}: {e}")
            continue


async def main():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    account_id = os.getenv("TASTY_ACCOUNT_ID")

    if not refresh_token or not client_secret or not account_id:
        logger.error("Missing credentials in .env file.")
        return

    # === ONE SESSION, NEVER RECREATE ===
    logger.info("Creating session...")
    print("--- 0DTE Trader Started ---")
    
    try:
        session = Session(provider_secret=client_secret, refresh_token=refresh_token)
        logger.info("Session created successfully.")
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        return

    uk_tz = pytz.timezone('Europe/London')
    target_times = [time(15, 0), time(15, 30)]
    
    logger.info(f"Entry times: {[t.strftime('%H:%M') for t in target_times]} UK")
    logger.info("Entering main loop. Will run until stopped.")

    # Track which times we've traded today (reset at midnight)
    traded_today = set()
    popper_started_today = False
    last_date = None

    while True:
        try:
            now_uk = datetime.now(uk_tz)
            today = now_uk.date()
            
            # Reset traded times and overnight gap cache at midnight
            if last_date != today:
                traded_today = set()
                popper_started_today = False
                last_date = today
                monitor.FORCE_CLOSE_REASONS.clear()
                logger.info(f"New trading day: {today}")

            current_time = now_uk.time()
            # DISABLED 2026-06-05 (performance trim): ORB Stacking is net-negative since its
            # April launch (~-$16 / 75 trades) and the heaviest API load at the open. Re-enable
            # by uncommenting. See docs/proposals/2026-06-05-entry-reliability-fix.md §6.
            # if (not popper_started_today and time(14, 30) <= current_time < time(21, 0)):
            #     popper_started_today = True
            #     logger.info("Launching ORB Stacking background task...")
            #     asyncio.create_task(run_orb_stacking(session))

            # Check for entry times
            for target in target_times:
                if (current_time.hour == target.hour and 
                    current_time.minute == target.minute and
                    target not in traded_today):
                    
                    logger.info(f"Entry time triggered: {target}")
                    traded_today.add(target)

                    try:
                        await execute_trade_cycle(session, trigger_time=target)
                    except Exception as e:
                        logger.error(f"Trade cycle failed: {type(e).__name__}: {e}")
                        # Don't crash - just log and continue

                    # Sleep to avoid re-triggering in same minute
                    await asyncio.sleep(60)
                    break

            # Monitor open positions (every 10 seconds)
            try:
                await monitor.check_open_positions(session)
                await monitor.check_eod_expiration(session)
            except Exception as e:
                logger.warning(f"Monitor error (will retry): {type(e).__name__}: {e}")
                # Don't crash - just log and continue

            await asyncio.sleep(10)

        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as e:
            # Catch-all: log and continue, never crash
            logger.error(f"Unexpected error in main loop: {type(e).__name__}: {e}")
            await asyncio.sleep(30)  # Wait a bit before retrying


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
