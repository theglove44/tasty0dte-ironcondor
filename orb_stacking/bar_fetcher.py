"""
SPX bar fetcher for ORB Stacking.

Subscribes to DXLink Candle events with a historical start_time, dedupes by
timestamp, filters out O=0 garbage bars, and exposes both:

  - fetch_history(): one-shot historical batch (for indicator warmup)
  - stream_closed_bars(): async iterator of newly closed live bars

Bar format: dict with keys {time, start, open, high, low, close}
  - time: epoch ms (dedup key)
  - start: timezone-aware datetime in UK_TZ
  - open/high/low/close: floats
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import AsyncIterator
import pytz

from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Candle


UK_TZ = pytz.timezone('Europe/London')
logger = logging.getLogger("orb-stacking-bars")

DEFAULT_INTERVAL = "30m"
DEFAULT_LOOKBACK_DAYS = 10
WARMUP_LISTEN_SECONDS = 20


def candle_to_bar(c: Candle) -> dict | None:
    """Convert a DXLink Candle event to a bar dict, or None if incomplete."""
    if c.time is None:
        return None
    if c.open is None or c.high is None or c.low is None or c.close is None:
        return None
    return {
        'time': c.time,
        'start': datetime.fromtimestamp(c.time / 1000, tz=UK_TZ),
        'open': float(c.open),
        'high': float(c.high),
        'low': float(c.low),
        'close': float(c.close),
    }


def is_garbage_bar(bar: dict) -> bool:
    """DXLink occasionally emits sentinel bars with O=0 / C=0 (e.g. weekend
    timestamps at the start of a historical window). Filter them out."""
    return bar['open'] == 0 or bar['close'] == 0


def clean_and_sort(bars_by_time: dict) -> list[dict]:
    """Sort a {time: bar} dict into a list ordered by timestamp."""
    return sorted(bars_by_time.values(), key=lambda b: b['time'])


class BarFetcher:
    """Fetches and streams SPX bars from DXLink for the ORB Stacking strategy.

    History and live streaming use SEPARATE DXLink connections so callers can
    warm up indicators synchronously, then start streaming when ready. ORB
    Stacking opens at most one fetcher per session, so connection overhead is
    immaterial.
    """

    def __init__(self, symbol: str = "SPX", interval: str = DEFAULT_INTERVAL,
                 lookback_days: int = DEFAULT_LOOKBACK_DAYS):
        self.symbol = symbol
        self.interval = interval
        self.lookback_days = lookback_days

    async def fetch_history(self, session: Session) -> list[dict]:
        """Subscribe with historical start_time, drain for WARMUP_LISTEN_SECONDS,
        return cleaned + deduped + sorted bars.
        """
        start_time = datetime.now(UK_TZ) - timedelta(days=self.lookback_days)
        logger.info(
            f"Fetching {self.symbol} {self.interval} history from "
            f"{start_time.isoformat()} (lookback={self.lookback_days}d)"
        )

        by_time: dict = {}

        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe_candle([self.symbol], self.interval, start_time)

            loop_start = datetime.now()
            try:
                async for event in streamer.listen(Candle):
                    if (datetime.now() - loop_start).total_seconds() > WARMUP_LISTEN_SECONDS:
                        break
                    events = event if isinstance(event, list) else [event]
                    for e in events:
                        if not isinstance(e, Candle):
                            continue
                        bar = candle_to_bar(e)
                        if bar is None or is_garbage_bar(bar):
                            continue
                        by_time[bar['time']] = bar
            except Exception as ex:
                logger.error(f"History fetch error: {type(ex).__name__}: {ex}")

        bars = clean_and_sort(by_time)
        if bars:
            logger.info(
                f"Fetched {len(bars)} historical bars: "
                f"{bars[0]['start'].isoformat()} -> {bars[-1]['start'].isoformat()}"
            )
        else:
            logger.warning("No historical bars received")
        return bars

    async def stream_closed_bars(self, session: Session) -> AsyncIterator[dict]:
        """Async iterator yielding each newly closed bar.

        Subscribes with start_time = now, then watches for the timestamp to
        advance — when it does, the previous bar is closed and gets emitted.
        """
        start_time = datetime.now(UK_TZ)
        logger.info(
            f"Streaming live closed {self.symbol} {self.interval} bars "
            f"from {start_time.isoformat()}"
        )

        last_bar: dict | None = None

        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe_candle([self.symbol], self.interval, start_time)

            async for event in streamer.listen(Candle):
                events = event if isinstance(event, list) else [event]
                for e in events:
                    if not isinstance(e, Candle):
                        continue
                    bar = candle_to_bar(e)
                    if bar is None or is_garbage_bar(bar):
                        continue

                    if last_bar is None:
                        last_bar = bar
                        continue

                    if bar['time'] > last_bar['time']:
                        # Timestamp advanced -> previous bar closed
                        logger.info(
                            f"Bar closed: {last_bar['start'].isoformat()} "
                            f"O={last_bar['open']:.2f} H={last_bar['high']:.2f} "
                            f"L={last_bar['low']:.2f} C={last_bar['close']:.2f}"
                        )
                        yield last_bar
                        last_bar = bar
                    elif bar['time'] == last_bar['time']:
                        # Same bar, fresher values
                        last_bar = bar
                    # bar['time'] < last_bar['time'] -> stale event, ignore
