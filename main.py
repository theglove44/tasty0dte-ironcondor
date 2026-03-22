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
from dotenv import load_dotenv
from tastytrade import Session

import strategy
import monitor
import logger as trade_logger
import premium_popper

try:
    from local import discord_notify
except Exception:
    discord_notify = None

try:
    from local import x_notify
except Exception:
    x_notify = None

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trade.log"),
        logging.StreamHandler()
    ]
)
logging.getLogger("tastytrade").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger("0dte-trader")

load_dotenv()

# === STRATEGY CONFIGS ===
# Note: IC-20D-1500 removed (2026-02-11) - 88% win rate but negative P/L over 34 trades
STRATEGY_CONFIGS = [
    # Iron Flies: +$29,422 combined over 510 trades (Dec 2025 - Mar 2026)
    {'name': "Iron Fly V1", 'code': "IF-V1", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(14, 0)]},
    {'name': "Iron Fly V2", 'code': "IF-V2", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(14, 0)]},
    {'name': "Iron Fly V3", 'code': "IF-V3", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(14, 30)]},
    {'name': "Iron Fly V4", 'code': "IF-V4", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(14, 30)]},
    # Dynamic 0DTE: +$7,418 over 13 trades, 92% WR, best per-trade avg
    {'name': "Dynamic 0DTE", 'code': "DY-0D", 'type': 'dynamic_0dte',
     'allowed_times': [time(14, 0)],
     'profit_target_pct': 0.20,
     'move_threshold': -0.1,
     'condor_delta': 0.20, 'condor_wing_width': 20,
     'fly_delta': 0.50, 'fly_wing_width': 10},
    # Premium Popper ORB20: breakout credit spread (runs as background task)
    {'name': "Premium Popper", 'code': "PP-ORB", 'type': 'premium_popper',
     'allowed_times': [time(13, 30)],
     'profit_target_pct': 0.50},
    # Removed 2026-03-22 after performance review (510 trades, Dec 2025 - Mar 2026):
    # - 20 Delta IC: -$2,086, 0.09 win/loss ratio despite 90.6% WR
    # - 30 Delta IC: -$4,351, deteriorating monthly (Jan +$6k -> Mar -$6k)
    # - Gap Filter 20D: -$6,056, catastrophic tail losses (-$3,520 worst)
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


async def execute_trade_cycle(session: Session, trigger_time: time = None):
    """Execute one trade cycle for all strategies at the given trigger time."""
    logger.info(f"Starting trade cycle for {trigger_time}...")
    
    # Fetch chain
    chain = await strategy.fetch_spx_option_chain(session)
    exp = strategy.filter_for_0dte(chain)
    if not exp:
        logger.warning("No 0DTE expiration found. Skipping cycle.")
        return

    iv_rank = await strategy.fetch_spx_iv_rank(session)
    
    # Cache SPX price for fallback (used by Dynamic 0DTE strategy)
    spx_spot = await strategy.get_spx_spot(session, timeout_s=5)
    if spx_spot:
        strategy.save_spx_price(spx_spot)
    
    for strat in STRATEGY_CONFIGS:
        strat_name = strat['name']
        strat_type = strat['type']

        # Premium Popper runs as its own background task, not through trade cycle
        if strat_type == 'premium_popper':
            continue

        target_delta = strat.get('target_delta', 0)
        profit_target_pct = strat['profit_target_pct']
        allowed_times = strat.get('allowed_times')

        if not _is_trigger_time_allowed(allowed_times, trigger_time):
            continue

        logger.info(f"Executing: {strat_name} (Delta {target_delta})")
        
        # Find legs
        legs = None
        notes_extra = ""
        if strat_type == 'iron_condor':
            legs = await strategy.find_iron_condor_legs(session, exp, target_delta=target_delta)
        elif strat_type == 'iron_fly':
            wing_width = strat.get('wing_width', 10)
            legs = await strategy.find_iron_fly_legs(session, exp, target_delta=target_delta, wing_width=wing_width)
        elif strat_type == 'dynamic_0dte':
            move_data = await strategy.get_spx_30min_move(session)
            if not move_data:
                logger.warning(f"[{strat_name}] Could not fetch 30-min move. Skipping.")
                continue

            change_pct = move_data['change_pct']
            threshold = strat.get('move_threshold', -0.1)

            if change_pct > threshold:
                selected = "IC"
                legs = await strategy.find_iron_condor_legs(
                    session, exp, target_delta=strat['condor_delta'])
            else:
                selected = "IF"
                legs = await strategy.find_iron_fly_legs(
                    session, exp, target_delta=strat['fly_delta'],
                    wing_width=strat['fly_wing_width'])

            notes_extra = f"30min: {change_pct:+.2f}% → {selected}"
            logger.info(f"[{strat_name}] SPX 30-min move: {change_pct:+.2f}% → Selected: {selected}")

        if not legs:
            logger.warning(f"[{strat_name}] Could not find suitable legs.")
            continue
            
        # Calculate credit & risk
        credit = (legs['short_call']['price'] + legs['short_put']['price']) - \
                 (legs['long_call']['price'] + legs['long_put']['price'])
        
        call_width = abs(float(legs['short_call']['strike']) - float(legs['long_call']['strike']))
        put_width = abs(float(legs['short_put']['strike']) - float(legs['long_put']['strike']))
        width = max(call_width, put_width)
        
        risk = width - credit
        bp = risk * 100
        profit_target = credit * profit_target_pct
        
        strategy_id = _build_strategy_id(strat_name, trigger_time)
        
        # Log trade
        notes = f"0DTE {strat_name} | {notes_extra}" if notes_extra else None
        trade_logger.log_trade_entry(legs, credit, bp, profit_target, iv_rank,
                                     strategy_name=strat_name, strategy_id=strategy_id,
                                     notes=notes)
        logger.info(f"[{strat_name}] Trade logged. Credit: ${credit:.2f}, IV Rank: {iv_rank}")

        # Discord notification
        if discord_notify:
            try:
                spx_spot = await strategy.get_spx_spot(session)
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
                    iv_rank=iv_rank
                )
                discord_notify.send_discord_webhook(payload)
                
                if x_notify:
                    x_notify.post_trade_update(strat_name, float(credit), spx_spot, iv_rank)
            except Exception as e:
                logger.warning(f"[{strat_name}] Notification failed: {e}")


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
    target_times = [time(14, 0), time(14, 30)]
    
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
                logger.info(f"New trading day: {today}")

            # Launch Premium Popper at 13:30 UK (market open) to collect ORB
            current_time = now_uk.time()
            if (current_time.hour == 13 and current_time.minute == 30 and not popper_started_today):
                popper_started_today = True
                logger.info("Launching Premium Popper ORB20 background task...")
                asyncio.create_task(premium_popper.run_premium_popper(session))

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
