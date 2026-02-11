from datetime import date, datetime
from tastytrade import Session, DXLinkStreamer
from tastytrade.instruments import NestedOptionChain, Option
from tastytrade.dxfeed import Summary
from tastytrade.utils import get_tasty_monthly
import pandas as pd
import logging
import inspect

logger = logging.getLogger("0dte-strategy")

async def _unwrap_awaitable(x, max_depth: int = 5):
    """Await nested awaitables (some SDK calls return coroutine objects).

    Raises underlying exceptions; does not swallow auth/network failures.
    """
    for _ in range(max_depth):
        if not inspect.isawaitable(x):
            break
        x = await x
    return x


def get_0dte_expiration_date():
    return date.today()


async def get_overnight_gap(session: Session, timeout_s: int = 5) -> dict | None:
    """
    Fetch SPX overnight gap data using Summary event.
    
    Returns dict with:
        - prev_close: Previous day's close price
        - day_open: Current day's open price  
        - gap_pct: Overnight gap as percentage
        - gap_classification: 'large_up', 'small_up', 'flat', 'down'
    """
    try:
        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe(Summary, ["SPX"])
            start_time = datetime.now()
            async for event in streamer.listen(Summary):
                if (datetime.now() - start_time).seconds > timeout_s:
                    logger.warning("Timeout fetching SPX Summary")
                    break
                events = event if isinstance(event, list) else [event]
                for e in events:
                    if isinstance(e, Summary) and e.event_symbol == "SPX":
                        prev_close = e.prev_day_close_price
                        day_open = e.day_open_price
                        
                        if prev_close and day_open and prev_close > 0:
                            gap_pct = ((day_open - prev_close) / prev_close) * 100
                            
                            # Classify the gap
                            if gap_pct > 0.5:
                                classification = 'large_up'
                            elif gap_pct < -0.5:
                                classification = 'large_down'  
                            elif -0.2 <= gap_pct <= 0.2:
                                classification = 'flat'
                            elif gap_pct > 0.2:
                                classification = 'small_up'
                            else:
                                classification = 'small_down'
                            
                            return {
                                'prev_close': float(prev_close),
                                'day_open': float(day_open),
                                'gap_pct': gap_pct,
                                'gap_classification': classification
                            }
    except Exception as e:
        logger.error(f"Error fetching overnight gap: {type(e).__name__}: {e}")
    
    return None


def should_trade_overnight_filter(gap_data: dict | None) -> tuple[bool, str]:
    """
    Apply overnight gap filter logic.
    
    Returns (should_trade, reason)
    
    Rules:
        - Gap > +0.5% (large up) → TRADE
        - Gap -0.2% to +0.2% (flat) → TRADE
        - Gap +0.2% to +0.5% (small up) → SKIP
        - Gap < 0% (any down) → SKIP
    """
    if gap_data is None:
        return True, "No gap data available, trading anyway"
    
    classification = gap_data['gap_classification']
    gap_pct = gap_data['gap_pct']
    
    if classification == 'large_up':
        return True, f"Large UP gap ({gap_pct:+.2f}%) - expecting chop/flat day"
    elif classification == 'flat':
        return True, f"Flat overnight ({gap_pct:+.2f}%) - consistent performer"
    elif classification == 'small_up':
        return False, f"Small UP grind ({gap_pct:+.2f}%) - skip (underperforms)"
    elif classification in ('small_down', 'large_down'):
        return False, f"DOWN gap ({gap_pct:+.2f}%) - skip (no research data)"
    else:
        return True, f"Unknown classification, trading anyway"


from tastytrade.instruments import get_option_chain, OptionType
from tastytrade.metrics import get_market_metrics

async def fetch_spx_iv_rank(session: Session) -> float:
    """
    Fetches the IV Rank for SPX.
    """
    logger.info("Fetching SPX IV Rank...")
    try:
        metrics = await _unwrap_awaitable(get_market_metrics(session, ["SPX"]))

        if metrics and getattr(metrics[0], 'implied_volatility_index_rank', None) is not None:
            iv_rank = float(metrics[0].implied_volatility_index_rank)
            logger.info(f"SPX IV Rank: {iv_rank}")
            return iv_rank
        else:
            logger.warning("IV Rank attribute not found or metrics empty")
    except Exception as e:
        logger.error(f"Error fetching IV Rank: {type(e).__name__}: {e}")

    return 0.0


async def fetch_spx_option_chain(session: Session):
    """Fetch the SPX option chain.

    tastytrade SDK versions differ: in some, get_option_chain is sync; in others
    it returns an awaitable. Handle both.
    """
    logger.info("Fetching SPX option chain...")
    symbol = "SPX"

    chain = await _unwrap_awaitable(get_option_chain(session, symbol))
    return chain
def filter_for_0dte(chain: dict):
    """
    Filters the chain for today's expiration.
    Chain is Dict[date, List[Option]]
    """
    today = get_0dte_expiration_date()
    logger.info(f"Looking for expiration: {today}")
    
    # DEBUG Override for testing if today has no 0DTE (uncomment to test)
    # if chain:
    #     today = sorted(chain.keys())[0]
    
    if today in chain:
        logger.info(f"Found 0DTE expiration: {today} with {len(chain[today])} options")
        return chain[today]

    logger.warning(f"No 0DTE expiration found for {today}")
    return None

from tastytrade.dxfeed import Greeks, Quote


async def get_spx_spot(session: Session, timeout_s: int = 3) -> float | None:
    """Fetch current SPX mid-price. Returns None on failure."""
    try:
        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe(Quote, ["SPX"])
            start_time = datetime.now()
            async for event in streamer.listen(Quote):
                if (datetime.now() - start_time).seconds > timeout_s:
                    break
                events = event if isinstance(event, list) else [event]
                for e in events:
                    if isinstance(e, Quote) and e.event_symbol == "SPX":
                        if e.bid_price and e.ask_price:
                            return float((e.bid_price + e.ask_price) / 2)
                        elif e.ask_price:
                            return float(e.ask_price)
    except Exception as e:
        logger.warning(f"Failed to get SPX spot: {type(e).__name__}: {e}")
    return None


async def get_quote_snapshot(session: Session, symbols: list):
    """
    Fetches a snapshot of quotes for a list of symbols.
    """
    quotes = {}
    if not symbols:
        return quotes
        
    logger.info(f"Fetching quotes for {len(symbols)} symbols...")
    
    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(Quote, symbols)
        
        start_time = datetime.now()
        async for event in streamer.listen(Quote):
            if (datetime.now() - start_time).seconds > 5:
                # logger.warning("Timeout waiting for Quotes.")
                break
            
            if isinstance(event, list):
                for e in event:
                     if isinstance(e, Quote):
                        quotes[e.event_symbol] = e
            elif isinstance(event, Quote):
                quotes[event.event_symbol] = event

            if len(quotes) >= len(symbols):
                break
                
    return quotes

async def get_greeks_for_chain(session: Session, options_list: list):
    """
    Subscribes to Greeks for all options in the list to find deltas.
    """
    # options_list is a list of FutureOption objects
    symbols = [o.streamer_symbol for o in options_list]
            
    if not symbols:
        logger.error("No symbols found in expiration.")
        return {}

    logger.info(f"Subscribing to Greeks for {len(symbols)} symbols...")
    
    # Setup Streamer
    greeks_data = {}
    
    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(Greeks, symbols)
        
        start_time = datetime.now()
        async for event in streamer.listen(Greeks):
            if (datetime.now() - start_time).seconds > 10:
                logger.warning("Timeout waiting for Greeks.")
                break
            
            # Event handling
            # event is likely the object itself (Greeks object) or list
            # The SDK usually yields the event object
            
            if isinstance(event, list):
                for e in event:
                     # Check type
                     if isinstance(e, Greeks):
                        greeks_data[e.event_symbol] = e
            elif isinstance(event, Greeks):
                greeks_data[event.event_symbol] = event

            if len(greeks_data) >= len(symbols) * 0.9:
                break
            
    return greeks_data

def _separate_calls_puts(options_list: list, greeks: dict):
    """Separate options into sorted call/put lists with greeks attached."""
    calls = []
    puts = []
    for option in options_list:
        if option.streamer_symbol in greeks:
            delta = float(greeks[option.streamer_symbol].delta)
            entry = {'symbol': option.streamer_symbol, 'strike': option.strike_price, 'delta': delta}
            if option.option_type == OptionType.CALL:
                calls.append(entry)
            elif option.option_type == OptionType.PUT:
                puts.append(entry)
    calls.sort(key=lambda x: x['strike'])
    puts.sort(key=lambda x: x['strike'])
    return calls, puts


async def _fetch_leg_prices(session: Session, legs: dict):
    """Populate each leg dict with a 'price' key from live quotes."""
    leg_symbols = [legs[k]['symbol'] for k in legs]
    quotes = await get_quote_snapshot(session, leg_symbols)
    for k in legs:
        sym = legs[k]['symbol']
        price = 0.0
        if sym in quotes:
            q = quotes[sym]
            if q.bid_price and q.ask_price:
                price = (q.bid_price + q.ask_price) / 2
            else:
                price = q.ask_price or q.bid_price or 0.0
        legs[k]['price'] = float(price)


async def find_iron_condor_legs(session: Session, options_list: list, target_delta: float = 0.20):
    """Finds the legs for the Iron Condor based on Target Delta."""
    greeks = await get_greeks_for_chain(session, options_list)
    if not greeks:
        logger.error("No Greeks data found.")
        return None

    calls, puts = _separate_calls_puts(options_list, greeks)
    if not calls or not puts:
        logger.error("No calls or puts found with greeks.")
        return None

    short_call = min(calls, key=lambda x: abs(x['delta'] - target_delta))
    short_put = min(puts, key=lambda x: abs(x['delta'] + target_delta))

    long_call = min(calls, key=lambda c: abs(c['strike'] - (short_call['strike'] + 20)), default=None)
    long_put = min(puts, key=lambda p: abs(p['strike'] - (short_put['strike'] - 20)), default=None)

    if not long_call or not long_put:
        logger.error(f"Could not find wings. Short Call: {short_call['strike']}, Short Put: {short_put['strike']}")
        return None

    legs = {
        'short_call': short_call,
        'long_call': long_call,
        'short_put': short_put,
        'long_put': long_put
    }
    await _fetch_leg_prices(session, legs)
    logger.info(f"Selected Legs with Prices: {legs}")
    return legs


async def find_iron_fly_legs(session: Session, options_list: list, target_delta: float = 0.50, wing_width: int = 10):
    """
    Finds the legs for the Iron Fly.
    ATM Short Call and Put (closest to target_delta usually 0.50).
    Long Call at ATM + wing_width, Long Put at ATM - wing_width.
    """
    greeks = await get_greeks_for_chain(session, options_list)
    if not greeks:
        logger.error("No Greeks data found.")
        return None

    calls, puts = _separate_calls_puts(options_list, greeks)
    if not calls or not puts:
        logger.error("No calls or puts found with greeks.")
        return None

    # Find ATM Call (closest to target_delta e.g. 0.50)
    atm_call = min(calls, key=lambda x: abs(x['delta'] - target_delta))
    atm_strike = atm_call['strike']

    # Verify we have a put at this strike
    atm_put = next((p for p in puts if p['strike'] == atm_strike), None)

    if not atm_put:
        logger.warning(f"No Put found at ATM strike {atm_strike}. Looking for closest ATM Put.")
        atm_put = min(puts, key=lambda x: abs(abs(x['delta']) - target_delta))
        if atm_put['strike'] != atm_strike:
            logger.warning(f"ATM Call Strike {atm_strike} != ATM Put Strike {atm_put['strike']}. Using Call Strike as anchor.")
            retry_put = next((p for p in puts if p['strike'] == atm_strike), None)
            if retry_put:
                atm_put = retry_put
            else:
                logger.error(f"Cannot find Put at {atm_strike}. Aborting.")
                return None

    long_call = min(calls, key=lambda c: abs(c['strike'] - (atm_strike + wing_width)), default=None)
    long_put = min(puts, key=lambda p: abs(p['strike'] - (atm_strike - wing_width)), default=None)

    if not long_call or not long_put:
        logger.error(f"Could not find wings. ATM: {atm_strike}. Needed: +{wing_width}/-{wing_width}")
        return None

    legs = {
        'short_call': atm_call,
        'long_call': long_call,
        'short_put': atm_put,
        'long_put': long_put
    }
    await _fetch_leg_prices(session, legs)
    logger.info(f"Selected Iron Fly Legs ({wing_width} wide) at {atm_strike}: {legs}")
    return legs
