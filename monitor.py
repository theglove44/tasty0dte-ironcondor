import asyncio
import re
import pandas as pd
import logging
import pytz
from datetime import datetime, time
from decimal import Decimal
from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Quote, Summary
import strategy as strategy_mod
import sys
try:
    from local import discord_notify
except Exception:
    discord_notify = None
logger = logging.getLogger("0dte-monitor")


async def _cache_spx_price(session: Session) -> None:
    """Fetch and cache SPX price for EOD settlement."""
    try:
        quotes = {}
        summaries = {}
        
        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe(Quote, ["SPX"])
            await streamer.subscribe(Summary, ["SPX"])
            
            # Wait for SPX data (max 5 seconds)
            start_time = datetime.now()
            while (datetime.now() - start_time).seconds < 5:
                try:
                    event = await asyncio.wait_for(streamer.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                    
                events = event if isinstance(event, list) else [event]
                for e in events:
                    if isinstance(e, Quote):
                        quotes[e.event_symbol] = e
                    elif isinstance(e, Summary):
                        summaries[e.event_symbol] = e
                        
                if "SPX" in quotes:
                    break
            
            # Save SPX price if we have it
            if "SPX" in quotes:
                spx_q = quotes["SPX"]
                bid = spx_q.bid_price if spx_q.bid_price is not None else Decimal(0)
                ask = spx_q.ask_price if spx_q.ask_price is not None else Decimal(0)
                if bid > 0 and ask > 0:
                    spx_price = (bid + ask) / 2
                    strategy_mod.save_spx_price(float(spx_price))
                    logger.info(f"Cached SPX price: {spx_price}")
    except Exception as e:
        logger.warning(f"Failed to cache SPX price: {e}")


# Track lines for console refresh
_last_lines_count = 0
_NUMERIC_COLS_TO_FORMAT = ['Credit Collected', 'Buying Power', 'Profit Target', 'Exit P/L', 'IV Rank']
_TEXT_COLS_FOR_UPDATES = ['Exit Time', 'Notes']


def _normalize_numeric_columns(df):
    for col in _NUMERIC_COLS_TO_FORMAT:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round(2)


def _ensure_text_columns(df, columns=None):
    for col in (columns or _TEXT_COLS_FOR_UPDATES):
        if col in df.columns:
            df[col] = df[col].astype('object')


def _append_note(df, index, note):
    if 'Notes' not in df.columns:
        return
    current_notes = df.at[index, 'Notes']
    if pd.isna(current_notes):
        current_notes = ""
    df.at[index, 'Notes'] = f"{current_notes} | {note}"


def _quote_mark(quote):
    if quote is None:
        return None
    if quote.bid_price and quote.ask_price:
        return (quote.bid_price + quote.ask_price) / 2
    return quote.ask_price if quote.ask_price else quote.bid_price


def _mark_for_symbol(quotes, symbol):
    return _quote_mark(quotes.get(symbol))


def _parse_strike_token(symbol):
    match = re.search(r'[CP](\d+)$', symbol)
    return match.group(1) if match else "?"


def _parse_strike_float(symbol):
    token = _parse_strike_token(symbol)
    if token == "?":
        return None
    return float(token)

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

async def close_trade(df, index, debit_to_close, current_profit, csv_path, session=None, reason="Profit Target"):
    """
    Updates the trade status to CLOSED in the dataframe and saves to CSV.
    Optionally sends Discord webhook notification.
    """
    try:
        _ensure_text_columns(df)
        df.at[index, 'Status'] = 'CLOSED'
        df.at[index, 'Exit Time'] = datetime.now().strftime("%H:%M:%S")
        df.at[index, 'Exit P/L'] = round(current_profit, 2)
        _append_note(df, index, f"Closed at Debit: {debit_to_close:.2f}")
        _normalize_numeric_columns(df)

        df.to_csv(csv_path, index=False, float_format='%.2f')
        logger.info(f"Trade {index} closed and saved to {csv_path}")

        # Send Discord webhook notification
        try:
            spx_spot = await strategy_mod.get_spx_spot(session) if session else None
            strategy_name = df.at[index, 'Strategy'] if 'Strategy' in df.columns and pd.notna(df.at[index, 'Strategy']) else "Unknown"

            if discord_notify is None:
                logger.info(f"Trade {index}: Discord notifier not configured; skipping notification.")
                return

            payload = discord_notify.format_trade_close_payload(
                strategy_name=strategy_name,
                short_call_symbol=df.at[index, 'Short Call'],
                long_call_symbol=df.at[index, 'Long Call'],
                short_put_symbol=df.at[index, 'Short Put'],
                long_put_symbol=df.at[index, 'Long Put'],
                debit_to_close=debit_to_close,
                pl=current_profit,
                reason=reason,
                spx_spot=spx_spot
            )
            discord_notify.send_discord_webhook(payload)
            logger.info(f"Trade {index}: Discord webhook sent for trade close.")
        except Exception as e:
            logger.warning(f"Trade {index}: Failed to send Discord webhook: {e}")

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

    # Auto-expire stale 0DTE trades from prior days
    today_str = datetime.now().strftime('%Y-%m-%d')
    stale_mask = (df['Status'] == 'OPEN') & (df['Date'].astype(str) < today_str)
    if stale_mask.any():
        _ensure_text_columns(df)
        for idx in df[stale_mask].index:
            logger.warning(f"Auto-expiring stale trade {idx} from {df.at[idx, 'Date']}")
            df.at[idx, 'Status'] = 'EXPIRED'
            df.at[idx, 'Exit Time'] = '00:00:00'
            credit = float(df.at[idx, 'Credit Collected'])
            call_width = abs((_parse_strike_float(df.at[idx, 'Short Call']) or 0) - (_parse_strike_float(df.at[idx, 'Long Call']) or 0))
            put_width = abs((_parse_strike_float(df.at[idx, 'Short Put']) or 0) - (_parse_strike_float(df.at[idx, 'Long Put']) or 0))
            max_width = max(call_width, put_width)
            df.at[idx, 'Exit P/L'] = round(credit - max_width, 2)
            _append_note(df, idx, "Stale 0DTE: auto-expired (prior day)")
        _normalize_numeric_columns(df)
        df.to_csv(csv_path, index=False, float_format='%.2f')
        df = pd.read_csv(csv_path)
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
    
    # Always monitor SPX for EOD settlement cache
    if "SPX" not in symbols:
        symbols.add("SPX")
    
    if not symbol_list:
        status_lines.append(f"[{current_time}] Monitoring {len(open_trades)} trades but no symbols found.")
        refresh_console(status_lines, reset_cursor=False)
        # Still try to cache SPX price even with no open trades
        await _cache_spx_price(session)
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
        logger.error(f"Error streaming quotes: {type(e).__name__}: {e}")
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
        
        # Cache SPX price for EOD settlement fallback
        if spx_price > 0:
            strategy_mod.save_spx_price(float(spx_price))

    # Calculate P/L for each trade

    # Calculate P/L for each trade
    trades_closed = 0
    
    for index, row in open_trades.iterrows():
        try:
            sc_mark = _mark_for_symbol(quotes, row['Short Call'])
            lc_mark = _mark_for_symbol(quotes, row['Long Call'])
            sp_mark = _mark_for_symbol(quotes, row['Short Put'])
            lp_mark = _mark_for_symbol(quotes, row['Long Put'])

            if sc_mark is None or lc_mark is None or sp_mark is None or lp_mark is None:
                status_lines.append(f"Trade {index}: Waiting for data...")
                continue

            sc_mark = float(sc_mark)
            lc_mark = float(lc_mark)
            sp_mark = float(sp_mark)
            lp_mark = float(lp_mark)

            # Calculate Debit to Close (Buying back shorts, Selling longs)
            # Debit = (Shorts Buyback) - (Longs Sell)
            debit_to_close = (sc_mark + sp_mark) - (lc_mark + lp_mark)
            
            initial_credit = row['Credit Collected']
            profit_target = row['Profit Target'] 
            
            target_debit = initial_credit - profit_target
            
            current_profit = initial_credit - debit_to_close
            
            sc_str = _parse_strike_token(row['Short Call'])
            lc_str = _parse_strike_token(row['Long Call'])
            sp_str = _parse_strike_token(row['Short Put'])
            lp_str = _parse_strike_token(row['Long Put'])
            
            description = f"SPX IC {sc_str}/{lc_str}C / {sp_str}/{lp_str}P"
            
            # Change color based on P/L? For now just text.
            iv_rank_str = ""
            if "IV Rank" in row:
                try:
                    ivr = float(row["IV Rank"])
                    iv_rank_str = f", IVR={ivr:.2f}"
                except Exception:
                    pass
            
            # Check Time Exit for 30 Delta Strategy
            strategy_name = row['Strategy'] if 'Strategy' in row and pd.notna(row['Strategy']) else "20 Delta"
            
            # UK Time Check
            uk_tz = pytz.timezone('Europe/London')
            now_uk = datetime.now(uk_tz)
            
            is_time_exit = False
            # Time exit at 18:00 UK for 30 Delta and Iron Flies
            if strategy_name in ["30 Delta", "Iron Fly V1", "Iron Fly V2", "Iron Fly V3", "Iron Fly V4"]:
                # Exit at 18:00 UK
                if now_uk.time() >= time(18, 0):
                    is_time_exit = True
            
            status_lines.append(f"Trade {index} [{description}]: Credit={initial_credit:.2f}, Current Debit={debit_to_close:.2f}, P/L={current_profit:.2f}, Target={profit_target:.2f}{iv_rank_str}")

            if debit_to_close <= target_debit:
                if read_only:
                    status_lines.append(f"   >>> PROFIT TARGET REACHED (Read-Only)")
                else:
                    logger.info(f"Profit Target Reached for Trade {index}! Closing...")
                    await close_trade(df, index, debit_to_close, current_profit, csv_path, session, reason="Profit Target")
                    trades_closed += 1
            elif is_time_exit:
                if read_only:
                    status_lines.append(f"   >>> TIME EXIT REACHED (Read-Only)")
                else:
                    logger.info(f"Time Exit (18:00 UK) Reached for Trade {index} ({strategy_name})! Closing...")
                    _ensure_text_columns(df, ['Notes'])
                    _append_note(df, index, "Time Exit 18:00")

                    await close_trade(df, index, debit_to_close, current_profit, csv_path, session, reason="Time Exit (18:00 UK)")
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
    
    # Use Summary event for closing price (works after market close)
    spx_price = await strategy_mod.get_spx_close(session, timeout_s=5)

    if spx_price is None:
        logger.warning("Could not fetch SPX closing price. Cannot process EOD expirations.")
        return

    logger.info(f"SPX Closing Price for Expiration: {spx_price}")
    
    _ensure_text_columns(df)
    trades_expired = 0
    for index, row in open_trades.iterrows():
        try:
            short_call_strike = _parse_strike_float(row['Short Call'])
            long_call_strike = _parse_strike_float(row['Long Call'])
            short_put_strike = _parse_strike_float(row['Short Put'])
            long_put_strike = _parse_strike_float(row['Long Put'])
            
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
            _append_note(df, index, f"Settled at {spx_price:.2f}")

            trades_expired += 1

            # Send Discord webhook for expiration
            try:
                strategy_name = df.at[index, 'Strategy'] if 'Strategy' in df.columns and pd.notna(df.at[index, 'Strategy']) else "Unknown"

                if discord_notify is None:
                    logger.info(f"Trade {index}: Discord notifier not configured; skipping expiration notification.")
                    continue

                payload = discord_notify.format_trade_close_payload(
                    strategy_name=strategy_name,
                    short_call_symbol=df.at[index, 'Short Call'],
                    long_call_symbol=df.at[index, 'Long Call'],
                    short_put_symbol=df.at[index, 'Short Put'],
                    long_put_symbol=df.at[index, 'Long Put'],
                    debit_to_close=total_debit,
                    pl=eod_pl,
                    reason=f"EOD Expired (settled at {spx_price:.2f})",
                    spx_spot=spx_price
                )
                discord_notify.send_discord_webhook(payload)
                logger.info(f"Trade {index}: Discord webhook sent for expiration.")
            except Exception as e:
                logger.warning(f"Trade {index}: Failed to send Discord webhook: {e}")

        except Exception as e:
            logger.error(f"Error expiring trade {index}: {e}")

    if trades_expired > 0:
        _normalize_numeric_columns(df)
        df.to_csv(csv_path, index=False, float_format='%.2f')
        logger.info(f"Expired {trades_expired} trades.")

def is_market_closed():
    """
    Returns True if current UK time is >= 21:00 (Market Close).
    """
    uk_tz = pytz.timezone('Europe/London')
    now_uk = datetime.now(uk_tz)
    return now_uk.hour >= 21
