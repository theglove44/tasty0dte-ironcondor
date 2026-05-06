"""Jade Lizard strategy: short put + bear call spread with zero upside risk."""

import asyncio
import logging
import math
from datetime import date, timedelta
from tastytrade import Session
from tastytrade.instruments import OptionType

import strategy as strategy_mod
import logger as trade_logger
from strategy import (
    fetch_spx_option_chain,
    get_spx_spot,
    _unwrap_awaitable,
    validate_credit_sanity,
)


logger = logging.getLogger("0dte-trader")

# Constants
CREDIT_FLOOR: float = 4.50
CALL_WING_WIDTH: int = 5
PUT_WING_WIDTH: int = 20
PROFIT_TARGET_PCT: float = 0.25
PAPER_TRADES_CSV: str = "paper_trades.csv"
STRATEGY_PREFIX: str = "JadeLizard_"


def round_to_nearest_5(x: float) -> int:
    """Round to nearest 5."""
    return int(round(x / 5.0)) * 5


def select_target_expiry(chain: dict, today: date, target_dte: int) -> date | None:
    """Select target expiry from chain.

    Args:
        chain: dict[date, list[Option]]
        today: reference date
        target_dte: target days to expiration

    Returns:
        Earliest expiry >= today + target_dte, or None if none available.
    """
    target = today + timedelta(days=target_dte)
    candidates = sorted(d for d in chain.keys() if d >= target)
    return candidates[0] if candidates else None


def filter_for_target_expiry(chain: dict, target_date: date) -> list | None:
    """Extract options for a specific expiry date.

    Args:
        chain: dict[date, list[Option]]
        target_date: target expiry date

    Returns:
        List of options, or None if date absent or list empty.
    """
    opts = chain.get(target_date)
    return opts if opts and len(opts) > 0 else None


async def fetch_expected_move(
    session: Session, spx_spot: float, target_expiry: date, today: date
) -> float | None:
    """Fetch expected move from market metrics IV.

    Uses: expected_move = spot * IV * sqrt(dte / 365)

    Args:
        session: tastytrade Session
        spx_spot: current SPX price
        target_expiry: target expiry date
        today: reference date

    Returns:
        Expected move in points, or None on error.
    """
    try:
        from tastytrade.metrics import get_market_metrics

        metrics = await _unwrap_awaitable(get_market_metrics(session, ["SPX"]))
        if not metrics:
            logger.warning("fetch_expected_move: no metrics returned")
            return None

        spx_metric = metrics[0]
        expiry_iv_list = spx_metric.option_expiration_implied_volatilities
        if expiry_iv_list is None:
            logger.warning("fetch_expected_move: option_expiration_implied_volatilities is None")
            return None

        matching = next(
            (e for e in expiry_iv_list if e.expiration_date == target_expiry), None
        )
        if matching is None:
            available = [str(e.expiration_date) for e in expiry_iv_list]
            logger.warning(
                f"fetch_expected_move: no IV for {target_expiry}. "
                f"Available: {available}"
            )
            return None

        iv_raw = matching.implied_volatility
        if iv_raw is None:
            return None

        iv = float(iv_raw)
        if iv <= 0:
            return None

        dte = (target_expiry - today).days
        if dte <= 0:
            return None

        # Tastytrade displays expected move as ~0.68σ (50th-percentile of |move|, not 1σ)
        em = spx_spot * iv * math.sqrt(dte / 365.0) * 0.68
        logger.info(
            f"fetch_expected_move: expiry={target_expiry} iv_raw={iv_raw} iv={iv:.4f} "
            f"dte={dte} spot={spx_spot:.2f} em={em:.2f}"
        )
        return em

    except Exception as e:
        logger.error(f"fetch_expected_move failed: {type(e).__name__}: {e}", exc_info=True)
        return None


def find_jade_lizard_legs(
    options_list: list, spx_spot: float, expected_move: float
) -> dict | None:
    """Find the four legs of a Jade Lizard.

    Strikes:
      - short_put = round_to_nearest_5(spot - em)
      - long_put = short_put - 20
      - short_call = round_to_nearest_5(spot + em)
      - long_call = short_call + 5

    Args:
        options_list: list of Option objects
        spx_spot: current SPX price
        expected_move: expected move in points

    Returns:
        Dict with keys: short_put, long_put, short_call, long_call
        Each sub-dict: {'symbol': opt.streamer_symbol, 'occ_symbol': opt.symbol, 'strike': opt.strike_price}
        Or None if any leg missing or sanity check fails.
    """
    # Compute target strikes
    short_put = round_to_nearest_5(spx_spot - expected_move)
    long_put = short_put - PUT_WING_WIDTH
    short_call = round_to_nearest_5(spx_spot + expected_move)
    long_call = short_call + CALL_WING_WIDTH

    logger.info(
        f"find_jade_lizard_legs: spot={spx_spot:.2f} em={expected_move:.2f} "
        f"SP={short_put} LP={long_put} SC={short_call} LC={long_call}"
    )

    # Sanity check
    if short_call <= short_put:
        logger.error(
            f"Inverted strikes: short_call={short_call} <= short_put={short_put}. Skipping."
        )
        return None

    # Build lookup maps
    by_strike_call = {}
    by_strike_put = {}

    for opt in options_list:
        strike_int = int(opt.strike_price)
        if opt.option_type == OptionType.CALL:
            by_strike_call[strike_int] = opt
        elif opt.option_type == OptionType.PUT:
            by_strike_put[strike_int] = opt

    # Lookup each leg
    needed_strikes = {
        'short_call': (short_call, 'CALL'),
        'long_call': (long_call, 'CALL'),
        'short_put': (short_put, 'PUT'),
        'long_put': (long_put, 'PUT'),
    }

    legs = {}
    for leg_name, (strike, opt_type) in needed_strikes.items():
        lookup = by_strike_call if opt_type == 'CALL' else by_strike_put
        if strike not in lookup:
            available = sorted(lookup.keys())
            logger.error(
                f"Missing {opt_type} {strike}. Available {opt_type} strikes: {available}"
            )
            return None
        opt = lookup[strike]
        legs[leg_name] = {
            'symbol': opt.streamer_symbol,
            'occ_symbol': opt.symbol,
            'strike': opt.strike_price,
        }

    return legs


def is_jade_lizard_variant_open(strategy_name: str, csv_path: str = PAPER_TRADES_CSV) -> bool:
    """Check if a specific JL variant already has an open position.

    Args:
        strategy_name: e.g. "JadeLizard_5DTE"
        csv_path: path to paper_trades.csv

    Returns:
        True if that exact variant has an OPEN row.
    """
    import csv

    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return False
            for row in reader:
                if 'Strategy' not in row or 'Status' not in row:
                    continue
                if row.get('Strategy') == strategy_name and row.get('Status') == 'OPEN':
                    return True
        return False
    except FileNotFoundError:
        return False


async def execute_jade_lizard(
    session: Session,
    target_dte: int,
    strategy_name: str,
    strategy_id: str,
    profit_target_pct: float = PROFIT_TARGET_PCT,
    today: date | None = None,
    discord_notify=None,
) -> bool:
    """Execute Jade Lizard trade.

    Args:
        session: tastytrade Session
        target_dte: target days to expiration
        strategy_name: name (e.g. "JadeLizard_5DTE")
        strategy_id: code (e.g. "JL5")
        profit_target_pct: profit target as pct of credit (default 0.25)
        today: reference date (default today)

    Returns:
        True if trade logged, False otherwise.
    """
    try:
        today = today or date.today()

        # Check if this specific variant already has an open position
        if is_jade_lizard_variant_open(strategy_name):
            logger.info(f"[{strategy_name}] Already has an open position, skipping.")
            return False

        # Get SPX spot
        spx_spot = await get_spx_spot(session)
        if spx_spot is None:
            logger.warning(f"[{strategy_name}] Could not fetch SPX spot. Skipping.")
            return False

        # Fetch chain
        chain = await _unwrap_awaitable(fetch_spx_option_chain(session))
        if not chain:
            logger.warning(f"[{strategy_name}] No option chain. Skipping.")
            return False

        # Select expiry
        target_expiry = select_target_expiry(chain, today, target_dte)
        if target_expiry is None:
            logger.warning(f"[{strategy_name}] No expiry >= {target_dte} DTE. Skipping.")
            return False

        # Get options for expiry
        options_list = filter_for_target_expiry(chain, target_expiry)
        if options_list is None:
            logger.warning(f"[{strategy_name}] No options for {target_expiry}. Skipping.")
            return False

        # Fetch expected move
        expected_move = await fetch_expected_move(session, spx_spot, target_expiry, today)
        if expected_move is None:
            logger.warning(f"[{strategy_name}] Could not fetch expected move. Skipping.")
            return False

        # Find legs
        legs = find_jade_lizard_legs(options_list, spx_spot, expected_move)
        if legs is None:
            return False

        # Fetch leg prices
        await strategy_mod._fetch_leg_prices(session, legs)

        # Verify prices
        for leg_name in ['short_put', 'long_put', 'short_call', 'long_call']:
            if legs[leg_name].get('price') is None or legs[leg_name].get('price') == 0.0:
                logger.info(f"[{strategy_name}] missing_leg_price for {leg_name}. Skipping.")
                return False

        # Compute credit
        credit = (
            legs['short_put']['price'] + legs['short_call']['price']
        ) - (
            legs['long_put']['price'] + legs['long_call']['price']
        )

        # Check credit floor
        if credit < CREDIT_FLOOR:
            logger.info(
                f"[{strategy_name}] Credit ${credit:.2f} below floor ${CREDIT_FLOOR:.2f}. Skipping."
            )
            return False

        # Sanity check
        is_valid, reason = validate_credit_sanity(
            legs, credit, PUT_WING_WIDTH, spx_spot, strategy_name
        )
        if not is_valid:
            logger.warning(f"[{strategy_name}] {reason}")
            return False

        # Compute buying power and profit target
        buying_power = PUT_WING_WIDTH * 100 - credit * 100
        profit_target = credit * profit_target_pct

        # Build notes
        dte_actual = (target_expiry - today).days
        notes = f"target_expiry={target_expiry.isoformat()};dte={dte_actual};em={expected_move:.2f}"

        # Log trade
        trade_logger.log_trade_entry(
            legs,
            credit,
            buying_power,
            profit_target,
            iv_rank=0.0,
            strategy_name=strategy_name,
            strategy_id=strategy_id,
            notes=notes,
            short_delta="",
            spx_spot=spx_spot,
        )

        short_put_strike = int(legs['short_put']['strike'])
        long_put_strike = int(legs['long_put']['strike'])
        short_call_strike = int(legs['short_call']['strike'])
        long_call_strike = int(legs['long_call']['strike'])

        logger.info(
            f"[{strategy_name}] Trade logged. "
            f"PCS {short_put_strike}/{long_put_strike}P, "
            f"CCS {short_call_strike}/{long_call_strike}C. "
            f"Expiry={target_expiry}, Credit=${credit:.2f}"
        )

        if discord_notify:
            try:
                profit_target_debit = credit - profit_target
                payload = discord_notify.format_trade_open_payload(
                    strategy_name=strategy_name,
                    short_call_symbol=legs['short_call']['symbol'],
                    long_call_symbol=legs['long_call']['symbol'],
                    short_put_symbol=legs['short_put']['symbol'],
                    long_put_symbol=legs['long_put']['symbol'],
                    credit=float(credit),
                    profit_target=float(profit_target),
                    profit_target_debit=profit_target_debit,
                    wing_width=None,
                    credit_pct=None,
                    spx_spot=spx_spot,
                    iv_rank=None,
                )
                discord_notify.send_discord_webhook(payload)
            except Exception as e:
                logger.warning(f"[{strategy_name}] Discord notification failed: {e}")

        return True

    except Exception as e:
        logger.error(
            f"execute_jade_lizard({strategy_name}) failed: {type(e).__name__}: {e}",
            exc_info=True,
        )
        return False
