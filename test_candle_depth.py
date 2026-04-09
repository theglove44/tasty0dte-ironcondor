"""DXLink candle depth probe.

Question: when we call subscribe_candle() with a historical start_time,
how many historical bars does DXLink actually deliver?

ORB Stacking uses ATR(14) on 5m bars (needs 14 prior bars). Earlier Tag N
Turn iterations used BB(30) on 30m bars (needed 30). The --interval and
--warmup-threshold flags let the caller pick which warmup requirement to
check against.

Usage:
    python test_candle_depth.py                                   # 5m, report count only
    python test_candle_depth.py --interval 5m --warmup-threshold 14
    python test_candle_depth.py --interval 30m --warmup-threshold 30

--days is calendar days, not trading days; weekends and holidays are
included in the subtraction window. Run during market hours (or pre/post)
— DXLink should still serve the historical candles regardless of session
state.
"""
import asyncio
import argparse
import os
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("candle-depth")

import pytz
from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Candle


UK_TZ = pytz.timezone('Europe/London')
LISTEN_SECONDS = 20


async def probe(session: Session, days_back: int, interval: str, threshold: int | None) -> None:
    now = datetime.now(UK_TZ)
    start_time = now - timedelta(days=days_back)

    logger.info(f"Probe: SPX {interval} candles, start_time={start_time.isoformat()}")
    logger.info(f"Listening for {LISTEN_SECONDS}s...")

    raw_count = 0
    by_time: dict = {}

    async def _drain(streamer):
        nonlocal raw_count
        async for event in streamer.listen(Candle):
            events = event if isinstance(event, list) else [event]
            for e in events:
                if not isinstance(e, Candle):
                    continue
                raw_count += 1
                if not (e.time and e.open is not None and e.close is not None):
                    continue
                # Skip DXLink sentinel bars (O=0 or C=0) — these are
                # placeholder markers at the edge of historical windows
                # and are not usable for warmup. bar_fetcher.py filters
                # them in production; the probe must match to avoid
                # reporting a false "sufficient" verdict.
                if float(e.open) == 0 or float(e.close) == 0:
                    continue
                ts = datetime.fromtimestamp(e.time / 1000, tz=UK_TZ)
                by_time[ts] = {
                    'open': float(e.open),
                    'high': float(e.high) if e.high is not None else None,
                    'low': float(e.low) if e.low is not None else None,
                    'close': float(e.close),
                }

    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe_candle(["SPX"], interval, start_time)
        # Hard timeout: wait_for enforces LISTEN_SECONDS even if DXLink
        # stays silent (the inner `async for` would otherwise block
        # forever). TimeoutError is the normal terminating path.
        try:
            await asyncio.wait_for(_drain(streamer), timeout=LISTEN_SECONDS)
        except asyncio.TimeoutError:
            pass
        except Exception as ex:
            logger.error(f"Stream error: {type(ex).__name__}: {ex}")

    unique = sorted(by_time.keys())
    logger.info("=" * 60)
    logger.info(f"Raw events received: {raw_count}")
    logger.info(f"Unique bars: {len(unique)}")

    if not unique:
        logger.warning("NO BARS RECEIVED. Check session, symbol, market state.")
        return

    logger.info(f"Oldest bar: {unique[0].isoformat()}")
    logger.info(f"Newest bar: {unique[-1].isoformat()}")
    logger.info(f"Span: {(unique[-1] - unique[0])}")

    by_day: dict = defaultdict(int)
    for ts in unique:
        by_day[ts.date()] += 1

    logger.info("Bars per day:")
    for d in sorted(by_day):
        logger.info(f"  {d}: {by_day[d]} bars")

    logger.info("=" * 60)
    logger.info("Sample (first 3, last 3):")
    for ts in unique[:3]:
        b = by_time[ts]
        logger.info(f"  {ts.isoformat()}  O={b['open']}  C={b['close']}")
    if len(unique) > 6:
        logger.info("  ...")
        for ts in unique[-3:]:
            b = by_time[ts]
            logger.info(f"  {ts.isoformat()}  O={b['open']}  C={b['close']}")

    logger.info("=" * 60)
    # Warmup threshold depends on what indicator the interval is feeding.
    # ORB Stacking uses ATR(14) on 5m bars (needs 14). BB(30) on 30m bars
    # was the original Tag N Turn warmup need. For anything else, the
    # caller must pass --warmup-threshold explicitly; we refuse to guess.
    if threshold is None:
        logger.info(
            f"VERDICT: {len(unique)} bars fetched for interval={interval}. "
            f"Pass --warmup-threshold N to get a pass/fail verdict."
        )
    elif len(unique) >= threshold:
        logger.info(
            f"VERDICT: {len(unique)} bars >= {threshold} "
            f"(warmup threshold for interval={interval}) — sufficient."
        )
    else:
        logger.info(
            f"VERDICT: {len(unique)} bars < {threshold} "
            f"(warmup threshold for interval={interval}) — INSUFFICIENT."
        )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=10, help="Calendar days to look back (default: 10)")
    parser.add_argument("--interval", type=str, default="5m", help="Candle interval (default: 5m)")
    parser.add_argument(
        "--warmup-threshold",
        type=int,
        default=None,
        help="Minimum bars considered sufficient for warmup (interval-dependent; "
             "e.g. 14 for ATR(14) on 5m, 30 for BB(30) on 30m). "
             "If omitted, the probe reports the count without a pass/fail verdict.",
    )
    args = parser.parse_args()

    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")

    if not refresh_token or not client_secret:
        logger.error("Missing TASTY_REFRESH_TOKEN / TASTY_CLIENT_SECRET in .env")
        return

    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    logger.info("Session created.")

    await probe(session, args.days, args.interval, args.warmup_threshold)


if __name__ == "__main__":
    asyncio.run(main())
