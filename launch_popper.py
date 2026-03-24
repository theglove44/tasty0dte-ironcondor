"""One-off launcher: fetch ORB retroactively via DXLink Candle events, then run breakout monitoring."""

import asyncio
import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("popper-launcher")

import pytz
from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Candle

import premium_popper


UK_TZ = pytz.timezone('Europe/London')


async def fetch_orb_from_candles(session: Session) -> dict | None:
    """Fetch 5-min candles from 13:30-13:50 UK today via DXLink Candle events."""
    now = datetime.now(UK_TZ)
    orb_start = now.replace(hour=13, minute=30, second=0, microsecond=0)

    candles = []

    logger.info(f"Fetching 5-min candles for SPX from {orb_start.strftime('%H:%M')} UK...")

    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe_candle(["SPX"], "5m", orb_start)

        start = datetime.now()
        async for event in streamer.listen(Candle):
            if (datetime.now() - start).seconds > 10:
                break

            events = event if isinstance(event, list) else [event]
            for e in events:
                if not isinstance(e, Candle):
                    continue
                # Filter to only the 13:30-13:50 window (4 candles)
                if e.time and e.open and e.high and e.low and e.close:
                    candle_time = datetime.fromtimestamp(e.time / 1000, tz=UK_TZ)
                    if orb_start <= candle_time < orb_start + timedelta(minutes=20):
                        candles.append({
                            'open': float(e.open),
                            'high': float(e.high),
                            'low': float(e.low),
                            'close': float(e.close),
                            'start': candle_time,
                        })

    # Deduplicate by start time and sort
    seen = set()
    unique = []
    for c in candles:
        key = c['start'].strftime('%H:%M')
        if key not in seen:
            seen.add(key)
            unique.append(c)
    candles = sorted(unique, key=lambda c: c['start'])

    logger.info(f"Got {len(candles)} candles: {[c['start'].strftime('%H:%M') for c in candles]}")

    if len(candles) < 4:
        logger.error(f"Need 4 candles, got {len(candles)}. Cannot build ORB.")
        return None

    # Use premium_popper's ORB calculator
    return premium_popper._calculate_orb(candles[:4])


async def main():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")

    if not refresh_token or not client_secret:
        logger.error("Missing credentials in .env")
        return

    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    logger.info("Session created.")

    # Phase A: Fetch ORB retroactively
    orb = await fetch_orb_from_candles(session)
    if not orb:
        logger.error("Could not build ORB. Exiting.")
        return

    logger.info(f"ORB: {orb['low']:.2f}-{orb['high']:.2f}, range={orb['range']:.2f}, bias={orb['bias']}")

    # Phase B & C: Monitor for breakout and execute (reuse premium_popper functions)
    breakout = await premium_popper._monitor_for_breakout(session, orb)
    if not breakout:
        logger.info("No breakout detected. Done.")
        return

    await premium_popper._execute_trade(session, breakout, orb)
    logger.info("Premium Popper launcher complete.")


if __name__ == "__main__":
    asyncio.run(main())
