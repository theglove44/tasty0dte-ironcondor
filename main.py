import os
import asyncio
import time as pytime
import logging
import pytz
from datetime import datetime, time
from dotenv import load_dotenv
from tastytrade import Session
from tastytrade.utils import TastytradeError
import strategy
import monitor
import logger as trade_logger
try:
    from local import discord_notify
except Exception:
    discord_notify = None
try:
    from local import x_notify
except Exception:
    x_notify = None
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trade.log")
        # Console output is handled by monitor.py directly for clean UI
        # logging.StreamHandler()
    ]
)

# Suppress chatty libraries
logging.getLogger("tastytrade").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger("0dte-trader")

load_dotenv()

# Session health check interval (SDK v12 auto-refreshes tokens, so this is a lightweight keepalive)
SESSION_VALIDATE_EVERY_S = 120

# Circuit breaker: exit after too many consecutive auth failures (guard will restart cleanly).
SESSION_AUTH_FAIL_CIRCUIT_BREAKER = 8
# If a trade cycle fails due to auth/network, retry once after hard re-auth.
TRADE_CYCLE_RETRY_ON_AUTH_FAIL = 1


STRATEGY_CONFIGS = [
    {'name': "20 Delta", 'code': "IC-20D", 'type': 'iron_condor', 'target_delta': 0.20, 'profit_target_pct': 0.25},
    {'name': "30 Delta", 'code': "IC-30D", 'type': 'iron_condor', 'target_delta': 0.30, 'profit_target_pct': 0.25},
    {'name': "Iron Fly V1", 'code': "IF-V1", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
    {'name': "Iron Fly V2", 'code': "IF-V2", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
    {'name': "Iron Fly V3", 'code': "IF-V3", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 30)]},
    {'name': "Iron Fly V4", 'code': "IF-V4", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(15, 30)]},
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
    for strategy_cfg in STRATEGY_CONFIGS:
        if strategy_cfg['name'] in strategy_name:
            strategy_code = strategy_cfg['code']
            break
    return f"{strategy_code}-{t_code}"


def is_auth_error(e: Exception) -> bool:
    msg = str(e).lower()
    return ("unauthorized" in msg) or ("token" in msg and "invalid" in msg) or ("invalid_grant" in msg)


def is_transient_network_error(e: Exception) -> bool:
    msg = str(e).lower()
    # common intermittent failures observed in logs
    needles = [
        "handshake",
        "timed out",
        "timeout",
        "ssl",
        "connection reset",
        "temporarily unavailable",
        "network",
    ]
    return any(n in msg for n in needles)




async def main():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    account_id = os.getenv("TASTY_ACCOUNT_ID")

    if not refresh_token or not client_secret or not account_id:
        logger.error("Missing refresh token, client_secret (provider_secret) or account_id in .env file.")
        return

    def new_session():
        return Session(provider_secret=client_secret, refresh_token=refresh_token)

    logger.info("Authenticating with Tastytrade (OAuth)...")
    print("--- 0DTE Trader Started ---")
    print("Authenticating...")
    try:
        session = new_session()
        logger.info("Authentication successful.")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return

    # TZ Setup
    uk_tz = pytz.timezone('Europe/London')
    target_times = [time(14, 45), time(15, 0), time(15, 30)]
    
    logger.info(f"Target Entry Times: {[t.strftime('%H:%M') for t in target_times]} UK Time")

    # Session health state
    last_validate_ts = 0.0
    consecutive_auth_failures = 0

    try:
        while True:
            now_uk = datetime.now(uk_tz)

            # Lightweight health check (SDK v12 auto-refreshes tokens)
            if (pytime.time() - last_validate_ts) >= SESSION_VALIDATE_EVERY_S:
                auth_ok = False
                try:
                    auth_ok = bool(await session.validate())
                except Exception as e:
                    logger.warning(f"Session validate failed: {e}")

                if not auth_ok:
                    logger.warning("Session invalid; re-creating...")
                    try:
                        session = new_session()
                        auth_ok = True
                    except Exception as re_err:
                        logger.error(f"Re-auth failed: {re_err}")

                last_validate_ts = pytime.time()
                logger.info(f"HEALTH auth_ok={auth_ok} next_entries={[t.strftime('%H:%M') for t in target_times]}")

                if auth_ok:
                    consecutive_auth_failures = 0
                else:
                    consecutive_auth_failures += 1
                    logger.error(f"Auth unhealthy (consecutive failures={consecutive_auth_failures}); skipping cycle.")
                    if consecutive_auth_failures >= SESSION_AUTH_FAIL_CIRCUIT_BREAKER:
                        logger.error("Circuit breaker tripped: too many consecutive auth failures; exiting for guard restart.")
                        raise SystemExit(2)
                    await asyncio.sleep(5)
                    continue


            # Check if it's time to trade
            for target in target_times:
                if now_uk.time().hour == target.hour and now_uk.time().minute == target.minute:
                     logger.info(f"Triggering Trade Entry for {target}...")
                     # Validate right before trade cycle (fast fail)
                     try:
                         ok = bool(await session.validate())
                     except Exception as ve:
                         logger.warning(f"Pre-trade validate failed: {ve}")
                         ok = False

                     if not ok:
                         logger.warning("Pre-trade session invalid; re-authenticating before trade cycle...")
                         session = new_session()

                     attempt = 0
                     while True:
                         try:
                             await execute_trade_cycle(session, trigger_time=target)
                             break
                         except (TastytradeError, Exception) as e:
                             if is_auth_error(e) or is_transient_network_error(e):
                                 attempt += 1
                                 logger.warning(f"Trade cycle failed due to auth/network ({type(e).__name__}: {e}). attempt={attempt}")
                                 if attempt > TRADE_CYCLE_RETRY_ON_AUTH_FAIL:
                                     consecutive_auth_failures += 1
                                     logger.error(f"Trade cycle giving up (consecutive failures={consecutive_auth_failures}).")
                                     if consecutive_auth_failures >= SESSION_AUTH_FAIL_CIRCUIT_BREAKER:
                                         logger.error("Circuit breaker tripped after trade-cycle failures; exiting for guard restart.")
                                         raise SystemExit(2)
                                     break
                                 # hard reset session and retry once
                                 session = new_session()
                                 continue
                             # Unknown error: re-raise to avoid silent failure
                             raise
                     # Sleep to avoid re-triggering in same minute
                     await asyncio.sleep(60)
                     break
            
            # Check for exits every 10 seconds
            await monitor.check_open_positions(session)
            await monitor.check_eod_expiration(session)
            await asyncio.sleep(10) # check every 10 seconds

    except KeyboardInterrupt:
        logger.info("Stopping...")

async def execute_trade_cycle(session: Session, trigger_time: time = None):
    logger.info(f"Starting Trade Cycle for {trigger_time}...")
    
    # 1. Fetch Chain
    chain = await strategy.fetch_spx_option_chain(session)
    
    # 2. Filter 0DTE
    exp = strategy.filter_for_0dte(chain)
    if not exp:
        logger.error("No 0DTE found. Aborting.")
        return

    # Fetch IV Rank (Common for both)
    iv_rank = await strategy.fetch_spx_iv_rank(session)
    
    # Note: Times are in UK time as per main loop logic (14:45, 15:00, 15:30)
    # 3pm GMT is 15:00 UK time (usually, assuming standard winter time or alignment)
    for strat in STRATEGY_CONFIGS:
        strat_name = strat['name']
        strat_type = strat['type']
        target_delta = strat['target_delta']
        profit_target_pct = strat['profit_target_pct']
        allowed_times = strat.get('allowed_times')
        
        # Check Entry Time
        if not _is_trigger_time_allowed(allowed_times, trigger_time):
            continue

        logger.info(f"Executing Strategy: {strat_name} (Delta {target_delta}, Type {strat_type})")
        
        # 3. Find Legs
        legs = None
        if strat_type == 'iron_condor':
             legs = await strategy.find_iron_condor_legs(session, exp, target_delta=target_delta)
        elif strat_type == 'iron_fly':
             wing_width = strat.get('wing_width', 10)
             legs = await strategy.find_iron_fly_legs(session, exp, target_delta=target_delta, wing_width=wing_width)
        
        if not legs:
            logger.error(f"[{strat_name}] Could not find suitable legs.")
            continue
            
        # 4. Calculate Credit & BP
        short_call_price = legs['short_call']['price']
        long_call_price = legs['long_call']['price']
        short_put_price = legs['short_put']['price']
        long_put_price = legs['long_put']['price']
        
        # Credit = (Shorts Sold) - (Longs Bought)
        credit = (short_call_price + short_put_price) - (long_call_price + long_put_price)
        
        # Buying Power / Risk
        # Width of wings
        # For Iron Fly, width is explicitly defined or calculated
        # For Iron Condor, width is calculated from strikes
        call_width = abs(float(legs['short_call']['strike']) - float(legs['long_call']['strike']))
        put_width = abs(float(legs['short_put']['strike']) - float(legs['long_put']['strike']))
        
        width = max(call_width, put_width)
        
        # Risk = Width - Credit
        risk = width - credit
        
        # BP Effect = Risk * 100 (for 1 contract)
        bp = risk * 100
        
        profit_target = credit * profit_target_pct
        
        # Check if entry time is valid for this strategy?
        # Requirement: "entry is at 3pm GMT"
        # The main loop triggers at 14:45, 15:00, 15:30.
        # "3pm GMT" is 15:00 GMT (which is 15:00 UK time in winter/GMT, but London is usually GMT or BST).
        # Assuming current time usage (pytz London) matches the intent.
        
        description = f"SPX {strat_type} ({strat_name}): {legs['short_call']['strike']}/{legs['long_call']['strike']} Call Spread & {legs['short_put']['strike']}/{legs['long_put']['strike']} Put Spread"
        logger.info(f"Trade Identified: {description}")
        
        # 5. Log Trade
        
        strategy_id = _build_strategy_id(strat_name, trigger_time)
        
        trade_logger.log_trade_entry(legs, credit, bp, profit_target, iv_rank, strategy_name=strat_name, strategy_id=strategy_id)
        logger.info(f"[{strat_name}] Trade Logged successfully. IV Rank: {iv_rank}")

        # 6. Send Discord notification for trade open
        if discord_notify is None:
            logger.info(f"[{strat_name}] Discord notifier not configured (local/discord_notify.py missing); skipping notification.")
            continue

        try:
            spx_spot = await strategy.get_spx_spot(session)

            # Calculate wing width and credit percentage
            wing_width = width
            credit_pct = (credit / wing_width) * 100 if wing_width > 0 else 0
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
                wing_width=wing_width,
                credit_pct=credit_pct,
                spx_spot=spx_spot,
                iv_rank=iv_rank
            )
            discord_notify.send_discord_webhook(payload)
            logger.info(f"[{strat_name}] Discord webhook sent for trade open.")
            
            # Also post to X
            try:
                x_notify and x_notify.post_trade_update(strat_name, float(credit), spx_spot, iv_rank)
                logger.info(f"[{strat_name}] X notification triggered.")
            except Exception as xe:
                logger.warning(f"[{strat_name}] Failed to trigger X notification: {xe}")
        except Exception as e:
            logger.warning(f"[{strat_name}] Failed to send Discord webhook: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
