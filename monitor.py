import asyncio
import pandas as pd
import logging
from datetime import datetime, time
from decimal import Decimal
from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Quote, Summary

import sys
logger = logging.getLogger("0dte-monitor")

# Track lines for console refresh
_last_lines_count = 0

def refresh_console(lines: list, reset_cursor: bool = False):
    """
    Prints lines to the console.
    If reset_cursor is True, forces a new block (does not overwrite previous).
    Otherwise, overwrites the previous call's output using ANSI codes.
    """
    global _last_lines_count
    
    if reset_cursor:
        _last_lines_count = 0

    # Move cursor up by the number of lines previously printed
    if _last_lines_count > 0:
        # Move up
        sys.stdout.write(f"\033[{_last_lines_count}A")
        # Clear lines
        sys.stdout.write("\033[J")
    
    # Print new lines
    for line in lines:
        sys.stdout.write(line + "\n")
    
    sys.stdout.flush()
    _last_lines_count = len(lines)

def close_trade(df, index, debit_to_close, current_profit, csv_path):
    """
    Updates the trade status to CLOSED in the dataframe and saves to CSV.
    """
    try:
        df.at[index, 'Status'] = 'CLOSED'
        df.at[index, 'Exit Time'] = datetime.now().strftime("%H:%M:%S")
        df.at[index, 'Exit P/L'] = round(current_profit, 2)
        
        current_notes = df.at[index, 'Notes']
        if pd.isna(current_notes):
            current_notes = ""
        df.at[index, 'Notes'] = f"{current_notes} | Closed at Debit: {debit_to_close:.2f}"
        
        df.to_csv(csv_path, index=False)
        logger.info(f"Trade {index} closed and saved to {csv_path}")
    except Exception as e:
        logger.error(f"Failed to close trade {index}: {e}")

async def check_open_positions(session: Session, csv_path: str = "paper_trades.csv", read_only: bool = False):
    """
    Checks open positions in the CSV, streams current prices,
    calculates P/L, and closes trades if profit target is reached.
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        logger.error(f"{csv_path} not found.")
        return

    # Filter for OPEN trades
    open_trades = df[df['Status'] == 'OPEN']
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_lines = []

    if open_trades.empty:
        status_lines.append(f"[{current_time}] No active trades.")
        status_lines.append(f"Last Updated: {current_time}")
        refresh_console(status_lines, reset_cursor=False)
        return

    # Collect all unique symbols from open trades
    symbols = set()
    for index, row in open_trades.iterrows():
        symbols.add(row['Short Call'])
        symbols.add(row['Long Call'])
        symbols.add(row['Short Put'])
        symbols.add(row['Long Put'])
        
    symbol_list = list(symbols)
    if not symbol_list:
        status_lines.append(f"[{current_time}] Monitoring {len(open_trades)} trades but no symbols found.")
        refresh_console(status_lines, reset_cursor=False)
        return

    # Collect status lines for TUI
    status_lines = []
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    read_only_msg = " [READ-ONLY]" if read_only else ""
    status_lines.append(f"[{current_time}] Monitoring {len(open_trades)} open trades. Streaming quotes for {len(symbol_list)} symbols...{read_only_msg}")

    # Stream Quotes & Summary
    quotes = {}
    summaries = {}
    
    # Ensuring SPX is in the list for market data
    subs_list = list(symbol_list)
    if "SPX" not in subs_list:
        subs_list.append("SPX")

    try:
        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe(Quote, subs_list)
            await streamer.subscribe(Summary, ["SPX"])
            
            # Helper to merge streams since listen() only accepts one type
            queue = asyncio.Queue()
            
            async def pipe(type_cls):
                async for e in streamer.listen(type_cls):
                    await queue.put(e)
            
            tasks = [
                asyncio.create_task(pipe(Quote)),
                asyncio.create_task(pipe(Summary))
            ]

            start_time = datetime.now()
            
            try:
                while (datetime.now() - start_time).seconds < 5:
                    try:
                        # Wait for next event with short timeout to allow loop exit check
                        event = await asyncio.wait_for(queue.get(), timeout=0.5)
                        
                        # Handle list of events or single event
                        events = event if isinstance(event, list) else [event]
                        
                        for e in events:
                            if isinstance(e, Quote):
                                quotes[e.event_symbol] = e
                            elif isinstance(e, Summary):
                                summaries[e.event_symbol] = e
                        
                        # optimization: stop if we have quotes for all symbols AND summary for SPX
                        if len(quotes) >= len(subs_list) and "SPX" in summaries:
                            break
                    except asyncio.TimeoutError:
                        continue
            finally:
                # Cleanup background tasks
                for t in tasks:
                    t.cancel()
    except Exception as e:
        logger.error(f"Error streaming quotes: {e}")
        return

    if not quotes:
        logger.warning("No quotes received.")
        return

    # Process Market Data (SPX)
    if "SPX" in quotes:
        spx_q = quotes["SPX"]
        spx_price = Decimal(0)
        
        # Ensure prices are Decimals (SDK usually returns Decimal, but safety first)
        bid = spx_q.bid_price if spx_q.bid_price is not None else Decimal(0)
        ask = spx_q.ask_price if spx_q.ask_price is not None else Decimal(0)

        if bid > 0 and ask > 0:
            spx_price = (bid + ask) / 2
        elif ask > 0:
            spx_price = ask
            
        spx_change_str = ""
        if "SPX" in summaries:
            summ = summaries["SPX"]
            # Check if prev_day_close_price is valid (it might be NaN or None)
            if summ.prev_day_close_price and not pd.isna(summ.prev_day_close_price):
                # Ensure prev_close is Decimal
                prev_close = Decimal(str(summ.prev_day_close_price))
                change = spx_price - prev_close
                pct_change = (change / prev_close) * 100
                
                sign = "+" if change >= 0 else ""
                spx_change_str = f"({sign}{change:.2f} / {sign}{pct_change:.2f}%)"
        
        status_lines.append(f"MARKET: SPX {spx_price:.2f} {spx_change_str}")
        status_lines.append("-" * 60)

    # Calculate P/L for each trade

    # Calculate P/L for each trade
    trades_closed = 0
    
    for index, row in open_trades.iterrows():
        try:
            # Get Prices (using mid price if available, otherwise mark or last)
            # Quote object usually has bidPrice, askPrice.
            
            def get_mark(symbol):
                if symbol not in quotes:
                    return None
                q = quotes[symbol]
                if q.bid_price and q.ask_price:
                    return (q.bid_price + q.ask_price) / 2
                return q.ask_price if q.ask_price else q.bid_price # fallback
            
            sc_mark = float(get_mark(row['Short Call']))
            lc_mark = float(get_mark(row['Long Call']))
            sp_mark = float(get_mark(row['Short Put']))
            lp_mark = float(get_mark(row['Long Put']))
            
            if sc_mark is None or lc_mark is None or sp_mark is None or lp_mark is None:
                status_lines.append(f"Trade {index}: Waiting for data...")
                # logger.warning(f"Missing quotes for trade {index}. Skipping P/L check.")
                continue
            
            # Calculate Debit to Close (Buying back shorts, Selling longs)
            # Debit = (Shorts Buyback) - (Longs Sell)
            debit_to_close = (sc_mark + sp_mark) - (lc_mark + lp_mark)
            
            initial_credit = row['Credit Collected']
            profit_target = row['Profit Target'] 
            
            target_debit = initial_credit - profit_target
            
            current_profit = initial_credit - debit_to_close
            
            # Helper to parse symbol (e.g., .SPXW251210C6875)
            def parse_strike(sym):
                import re
                match = re.search(r'[CP](\d+)$', sym)
                return match.group(1) if match else "?"

            sc_str = parse_strike(row['Short Call'])
            lc_str = parse_strike(row['Long Call'])
            sp_str = parse_strike(row['Short Put'])
            lp_str = parse_strike(row['Long Put'])
            
            description = f"SPX IC {sc_str}/{lc_str}C / {sp_str}/{lp_str}P"
            
            # Change color based on P/L? For now just text.
            iv_rank_str = ""
            if "IV Rank" in row:
                try:
                    ivr = float(row["IV Rank"])
                    iv_rank_str = f", IVR={ivr:.2f}"
                except:
                    pass
            
            # Check Time Exit for 30 Delta Strategy
            strategy_name = row['Strategy'] if 'Strategy' in row and pd.notna(row['Strategy']) else "20 Delta"
            
            # UK Time Check
            import pytz
            uk_tz = pytz.timezone('Europe/London')
            now_uk = datetime.now(uk_tz)
            
            is_time_exit = False
            if strategy_name == "30 Delta":
                # Exit at 18:00 UK
                if now_uk.time() >= time(18, 0):
                    is_time_exit = True
            
            status_lines.append(f"Trade {index} [{description}]: Credit={initial_credit:.2f}, Current Debit={debit_to_close:.2f}, P/L={current_profit:.2f}, Target={profit_target:.2f}{iv_rank_str}")

            if debit_to_close <= target_debit:
                if read_only:
                    status_lines.append(f"   >>> PROFIT TARGET REACHED (Read-Only)")
                else:
                    logger.info(f"Profit Target Reached for Trade {index}! Closing...")
                    close_trade(df, index, debit_to_close, current_profit, csv_path)
                    trades_closed += 1
            elif is_time_exit:
                if read_only:
                    status_lines.append(f"   >>> TIME EXIT REACHED (Read-Only)")
                else:
                    logger.info(f"Time Exit (18:00 UK) Reached for Trade {index} ({strategy_name})! Closing...")
                    # Update notes to reflect Time Exit
                    current_notes = df.at[index, 'Notes']
                    if pd.isna(current_notes): current_notes = ""
                    df.at[index, 'Notes'] = f"{current_notes} | Time Exit 18:00"
                    
                    close_trade(df, index, debit_to_close, current_profit, csv_path)
                    trades_closed += 1
                
        except Exception as e:
            logger.error(f"Error processing trade {index}: {e}")

    if trades_closed > 0:
        logger.info(f"Closed {trades_closed} trade(s).")
    
    status_lines.append(f"Last Updated: {current_time}")
    
    # If we printed logs (trades_closed > 0), don't overwrite them.
    # Start a new dashboard block below them.
    refresh_console(status_lines, reset_cursor=(trades_closed > 0))

async def check_eod_expiration(session: Session, csv_path: str = "paper_trades.csv"):
    """
    Checks for End-Of-Day expiration.
    If time is past market close (21:00 UK), expire OPEN trades.
    """
    if not is_market_closed():
        return

    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return

    # Filter for OPEN trades that are TODAY (or older)
    # Actually, all OPEN trades should likely be closed if it's 0DTE logic.
    open_trades = df[df['Status'] == 'OPEN']
    
    if open_trades.empty:
        return

    logger.info("Market Closed. Checking for EOD Expirations...")
    
    # We need the SPX Spot Price to calculate settlement/expiration value.
    # We can fetch a quote for "SPX"
    # Note: SPX spot symbol might be "SPX" or "$SPX" depending on provider, 
    # but Tastytrade usually uses "SPX" for index.
    
    spx_price = None
    try:
        async with DXLinkStreamer(session) as streamer:
            # print("DEBUG: Subscribing to SPX")
            await streamer.subscribe(Quote, ["SPX"])
            start_time = datetime.now()
            async for event in streamer.listen(Quote):
                # print(f"DEBUG: Event received: {event}")
                if (datetime.now() - start_time).seconds > 5:
                    logger.warning("Timeout waiting for SPX quote.")
                    break
                
                # Check for list or single object
                events = event if isinstance(event, list) else [event]
                
                for e in events:
                    if isinstance(e, Quote) and e.event_symbol == "SPX":
                        if e.bid_price and e.ask_price:
                            spx_price = float(e.bid_price + e.ask_price) / 2
                            break
                        elif e.ask_price:
                            spx_price = float(e.ask_price)
                            break
                if spx_price:
                    break
    except Exception as e:
        logger.error(f"Error fetching SPX spot for EOD: {e}")
        return

    if spx_price is None:
        logger.warning("Could not fetch SPX spot price. Cannot process EOD expirations.")
        return

    logger.info(f"SPX Spot Price for Expiration: {spx_price}")
    
    trades_expired = 0
    for index, row in open_trades.iterrows():
        try:
            # Parse Strikes from Symbol string or another way?
            # The CSV columns `Short Call`, etc. currently hold the SYMBOL: ".SPXW..."
            # We need the strike.
            # We can extract it from the symbol string or if we stored it (we didn't explicitly store strikes as columns, only symbols).
            # Tastytrade SPX symbols: .SPXWYYMMDDC##### or P#####
            # Example: .SPXW251210C6875
            
            def get_strike_from_symbol(sym):
                # .SPXW 25 12 10 C 6875
                # Last part is strike. But checking format is tricky.
                # Regex is safer.
                import re
                match = re.search(r'[CP](\d+)$', sym)
                if match:
                    # Strike is usually multiplied? No, Tasty symbols usually have strike.
                    # Wait, verification output showed: '.SPXW251210C6875' and strike Decimal('6875.0')
                    # So the string ends with the strike.
                    return float(match.group(1))
                return None

            short_call_strike = get_strike_from_symbol(row['Short Call'])
            long_call_strike = get_strike_from_symbol(row['Long Call'])
            short_put_strike = get_strike_from_symbol(row['Short Put'])
            long_put_strike = get_strike_from_symbol(row['Long Put'])
            
            if not all([short_call_strike, long_call_strike, short_put_strike, long_put_strike]):
                logger.error(f"Could not parse strikes for trade {index}. Skipping.")
                continue

            # Calculate Expiration Value (Debit)
            # Debit = Call_Debit + Put_Debit
            # Call_Debit = Max(0, Spot - SC) - Max(0, Spot - LC)
            # Put_Debit = Max(0, SP - Spot) - Max(0, LP - Spot)
            
            call_debit = max(0, spx_price - short_call_strike) - max(0, spx_price - long_call_strike)
            put_debit = max(0, short_put_strike - spx_price) - max(0, long_put_strike - spx_price)
            
            total_debit = call_debit + put_debit
            
            credit = row['Credit Collected']
            eod_pl = credit - total_debit
            
            logger.info(f"Expiring Trade {index}. Spot: {spx_price}. Debit: {total_debit:.2f}. P/L: {eod_pl:.2f}")
            
            df.at[index, 'Status'] = 'EXPIRED'
            df.at[index, 'Exit Time'] = datetime.now().strftime("%H:%M:%S")
            df.at[index, 'Exit P/L'] = round(eod_pl, 2)
            
            current_notes = row['Notes'] if pd.notna(row['Notes']) else ""
            df.at[index, 'Notes'] = f"{current_notes} | Settled at {spx_price:.2f}"
            
            trades_expired += 1
            
        except Exception as e:
            logger.error(f"Error expiring trade {index}: {e}")
            
    if trades_expired > 0:
        df.to_csv(csv_path, index=False)
        logger.info(f"Expired {trades_expired} trades.")

def is_market_closed():
    """
    Returns True if current UK time is >= 21:00 (Market Close).
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now_uk = datetime.now(uk_tz)
    return now_uk.hour >= 21
