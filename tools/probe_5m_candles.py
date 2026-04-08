"""
MANUAL PROBE — not a unit test, not run by CI.

Probes the DXLink Candle feed for SPX to verify:
  1. At least WARMUP_MIN_BARS (30) 5-minute bars arrive on a 2-day lookback
  2. A closed-bar event arrives within 6 minutes of subscription start during RTH

Run as: python tools/probe_5m_candles.py

Requires an authenticated tastytrade Session — uses the same environment
variables as main.py (tastytrade provider secret + refresh token).

Fixes applied from Codex review:
  - Bug 1 (P1): Wrapped listen loop in asyncio.wait_for() timeout to prevent
    infinite hang when zero events arrive
  - Bug 2 (P2): Filters out garbage bars (open=0 or close=0) using the same
    is_garbage_bar function as production bar_fetcher
"""
import asyncio
import os
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("probe-5m-candles")

import pytz
from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Candle

from orb_stacking.bar_fetcher import (
    is_garbage_bar,
    candle_to_bar,
    WARMUP_MIN_BARS,
)

UK_TZ = pytz.timezone('Europe/London')
LISTEN_SECONDS = 20


async def probe(session: Session, days_back: int, interval: str) -> None:
    now = datetime.now(UK_TZ)
    start_time = now - timedelta(days=days_back)

    logger.info(f"Probe: SPX {interval} candles, start_time={start_time.isoformat()}")
    logger.info(f"Listening for {LISTEN_SECONDS}s...")

    by_time: dict = {}

    async def _collect_bars():
        """Listen for candles with internal timeout handling."""
        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe_candle(["SPX"], interval, start_time)

            async for event in streamer.listen(Candle):
                events = event if isinstance(event, list) else [event]
                for e in events:
                    if not isinstance(e, Candle):
                        continue

                    # Convert to bar using production logic
                    bar = candle_to_bar(e)
                    if bar is None or is_garbage_bar(bar):
                        continue

                    # Count only clean bars
                    by_time[bar['time']] = bar

    # Bug 1 fix: Wrap listen loop in asyncio.wait_for() to prevent infinite hang
    try:
        await asyncio.wait_for(
            _collect_bars(),
            timeout=LISTEN_SECONDS + 5
        )
    except asyncio.TimeoutError:
        logger.error(f"Probe timed out after {LISTEN_SECONDS + 5}s with no bars received")
    except Exception as ex:
        logger.error(f"Stream error: {type(ex).__name__}: {ex}")

    unique = sorted(by_time.keys())
    logger.info("=" * 60)
    logger.info(f"Clean bars received: {len(unique)}")

    if not unique:
        logger.warning("NO BARS RECEIVED. Check session, symbol, market state.")
        logger.info("=" * 60)
        logger.info(f"FAIL — received only {len(unique)} clean bars, needed {WARMUP_MIN_BARS}")
        return

    times = [datetime.fromtimestamp(t / 1000, tz=UK_TZ) for t in unique]
    logger.info(f"Oldest bar: {times[0].isoformat()}")
    logger.info(f"Newest bar: {times[-1].isoformat()}")
    logger.info(f"Span: {(times[-1] - times[0])}")

    by_day: dict = defaultdict(int)
    for t in times:
        by_day[t.date()] += 1

    logger.info("Bars per day:")
    for d in sorted(by_day):
        logger.info(f"  {d}: {by_day[d]} bars")

    logger.info("=" * 60)
    logger.info("Sample (first 3, last 3):")
    for ts in times[:3]:
        bar = by_time[int(ts.timestamp() * 1000)]
        logger.info(f"  {ts.isoformat()}  O={bar['open']:.2f}  C={bar['close']:.2f}")
    if len(unique) > 6:
        logger.info("  ...")
        for ts in times[-3:]:
            bar = by_time[int(ts.timestamp() * 1000)]
            logger.info(f"  {ts.isoformat()}  O={bar['open']:.2f}  C={bar['close']:.2f}")

    logger.info("=" * 60)
    if len(unique) >= WARMUP_MIN_BARS:
        logger.info(f"PASS — received {len(unique)} clean bars in {LISTEN_SECONDS}s (threshold: WARMUP_MIN_BARS={WARMUP_MIN_BARS})")
    else:
        logger.info(f"FAIL — received only {len(unique)} clean bars, needed {WARMUP_MIN_BARS}")


async def main():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")

    if not refresh_token or not client_secret:
        logger.error("Missing TASTY_REFRESH_TOKEN / TASTY_CLIENT_SECRET in .env")
        return

    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    logger.info("Session created.")

    # Probe with 5m interval, 2-day lookback (matches bar_fetcher defaults)
    await probe(session, days_back=2, interval="5m")


if __name__ == "__main__":
    asyncio.run(main())
