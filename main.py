import os
import asyncio
import logging
import pytz
from datetime import datetime, time
from dotenv import load_dotenv
from tastytrade import Session, DXLinkStreamer
import strategy
import monitor
import logger as trade_logger

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

async def main():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    account_id = os.getenv("TASTY_ACCOUNT_ID")

    if not refresh_token or not client_secret or not account_id:
        logger.error("Missing refresh token, client_secret (provider_secret) or account_id in .env file.")
        return

    logger.info("Authenticating with Tastytrade (OAuth)...")
    print("--- 0DTE Trader Started ---")
    print("Authenticating...")
    try:
        session = Session(refresh_token=refresh_token, provider_secret=client_secret)
        logger.info("Authentication successful.")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return

    # TZ Setup
    uk_tz = pytz.timezone('Europe/London')
    target_times = [time(14, 45), time(15, 0), time(15, 30)]
    
    logger.info(f"Target Entry Times: {[t.strftime('%H:%M') for t in target_times]} UK Time")

    try:
        while True:
            now_uk = datetime.now(uk_tz)
            
            # Connection Keep-Alive
            if not session.validate():
                 logger.info("Refreshing session...")
                 session = Session(refresh_token=refresh_token, provider_secret=client_secret)

            # Check if it's time to trade
            for target in target_times:
                if now_uk.time().hour == target.hour and now_uk.time().minute == target.minute:
                     logger.info(f"Triggering Trade Entry for {target}...")
                     await execute_trade_cycle(session, trigger_time=target)
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
    
    # Define Strategies
    # Note: Times are in UK time as per main loop logic (14:45, 15:00, 15:30)
    # 3pm GMT is 15:00 UK time (usually, assuming standard winter time or alignment)
    strategies = [
        {'name': "20 Delta", 'type': 'iron_condor', 'target_delta': 0.20, 'profit_target_pct': 0.25},
        {'name': "30 Delta", 'type': 'iron_condor', 'target_delta': 0.30, 'profit_target_pct': 0.25},
        {'name': "Iron Fly V1", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
        {'name': "Iron Fly V2", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(15, 0)]},
        {'name': "Iron Fly V3", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.10, 'wing_width': 10, 'allowed_times': [time(15, 30)]},
        {'name': "Iron Fly V4", 'type': 'iron_fly', 'target_delta': 0.50, 'profit_target_pct': 0.20, 'wing_width': 10, 'allowed_times': [time(15, 30)]}
    ]
    
    for strat in strategies:
        strat_name = strat['name']
        strat_type = strat['type']
        target_delta = strat['target_delta']
        profit_target_pct = strat['profit_target_pct']
        allowed_times = strat.get('allowed_times')
        
        # Check Entry Time
        if allowed_times and trigger_time:
            # simple check: if trigger_time (HH:MM) is in allowed_times
            # time objects comparison should work for hour/minute
            is_allowed = False
            for t in allowed_times:
                if t.hour == trigger_time.hour and t.minute == trigger_time.minute:
                    is_allowed = True
                    break
            
            if not is_allowed:
                # logger.info(f"Skipping {strat_name} at {trigger_time}")
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
        
        # Generate Strategy ID
        t_code = "0000"
        if trigger_time:
             t_code = trigger_time.strftime("%H%M")
        
        s_code = "UNK"
        if "20 Delta" in strat_name: s_code = "IC-20D"
        elif "30 Delta" in strat_name: s_code = "IC-30D"
        elif "Iron Fly V1" in strat_name: s_code = "IF-V1"
        elif "Iron Fly V2" in strat_name: s_code = "IF-V2"
        elif "Iron Fly V3" in strat_name: s_code = "IF-V3"
        elif "Iron Fly V4" in strat_name: s_code = "IF-V4"
        
        strategy_id = f"{s_code}-{t_code}"
        
        trade_logger.log_trade_entry(legs, credit, bp, profit_target, iv_rank, strategy_name=strat_name, strategy_id=strategy_id)
        logger.info(f"[{strat_name}] Trade Logged successfully. IV Rank: {iv_rank}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
