"""
SPX bar fetcher for ORB Stacking.

Subscribes to DXLink Candle events (5-minute bars) with a historical start_time,
dedupes by timestamp, filters out O=0 garbage bars, and exposes both:

  - fetch_history(): one-shot historical batch (for indicator warmup)
  - fetch_history_with_retry(): historical fetch with automatic retry if insufficient bars
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

DEFAULT_INTERVAL = "5m"
DEFAULT_LOOKBACK_DAYS = 2
WARMUP_LISTEN_SECONDS = 20
WARMUP_MIN_BARS = 30

# Maximum calendar gap between consecutive US trading days (Mon after Easter:
# Fri + Mon both holidays → last trade was Thu = 4 calendar days back).
_HOLIDAY_BUFFER_DAYS = 4


def trading_lookback_days(n: int = 1) -> int:
    """Calendar days to look back to guarantee n full prior trading sessions.

    lookback_days=1 fails on Mondays (looks back to Sunday) and after long
    weekends. Adding _HOLIDAY_BUFFER_DAYS covers all US holiday gaps safely.
    """
    return n + _HOLIDAY_BUFFER_DAYS
STREAM_MAX_RETRIES = 5
STREAM_RETRY_SLEEP_S = 4
KEEPALIVE_INTERVAL_S = 30  # SDK doesn't respond to server KA pings; we must send proactively


async def _dxlink_keepalive(streamer: DXLinkStreamer) -> None:
    """Send KEEPALIVE to the DXLink server every 30s.

    The tastytrade SDK receives KEEPALIVE pings from the server but does `pass`
    (never replies). The SETUP handshake sets keepaliveTimeout=60, so the server
    kills the connection after 60s of silence. This task keeps it alive.
    """
    try:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_S)
            await streamer._websocket.send_json({"type": "KEEPALIVE", "channel": 0})
            logger.debug("DXLink KEEPALIVE sent")
    except asyncio.CancelledError:
        pass


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
    """Fetches and streams 5-minute SPX bars from DXLink for the ORB Stacking strategy.

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
                logger.error(f"History fetch error: {type(ex).__name__}: {ex}", exc_info=True)

        bars = clean_and_sort(by_time)
        if bars:
            logger.info(
                f"Fetched {len(bars)} historical bars: "
                f"{bars[0]['start'].isoformat()} -> {bars[-1]['start'].isoformat()}"
            )
        else:
            logger.warning("No historical bars received")
        return bars

    async def fetch_history_with_retry(self, session: Session) -> list[dict]:
        """Fetch history once; if result has < WARMUP_MIN_BARS, retry once after a brief delay.

        Returns the larger of the two results. Does NOT raise if both attempts are
        below WARMUP_MIN_BARS; always returns whatever bars are available.
        Logs a WARNING if the final result is still below threshold.
        """
        bars = await self.fetch_history(session)

        if len(bars) >= WARMUP_MIN_BARS:
            return bars

        logger.warning(
            f"First fetch returned only {len(bars)} bars (< {WARMUP_MIN_BARS}), retrying..."
        )
        await asyncio.sleep(2)
        bars_retry = await self.fetch_history(session)

        result = bars_retry if len(bars_retry) > len(bars) else bars

        if len(result) < WARMUP_MIN_BARS:
            logger.warning(
                f"Only received {len(result)} bars after retry, needed {WARMUP_MIN_BARS}"
            )

        return result

    async def stream_closed_bars(self, session: Session) -> AsyncIterator[dict]:
        """Async iterator yielding each newly closed bar.

        Subscribes with start_time = now, then watches for the timestamp to
        advance — when it does, the previous bar is closed and gets emitted.
        Includes automatic reconnect/retry logic with up to STREAM_MAX_RETRIES attempts.
        """
        start_time = datetime.now(UK_TZ)
        logger.info(
            f"Streaming live closed {self.symbol} {self.interval} bars "
            f"from {start_time.isoformat()}"
        )

        last_bar: dict | None = None  # persists across reconnects

        for attempt in range(STREAM_MAX_RETRIES):
            if attempt > 0:
                reconnect_start_time = datetime.now(UK_TZ)
                logger.info(
                    f"stream_closed_bars reconnect attempt {attempt}/{STREAM_MAX_RETRIES - 1}, "
                    f"last_bar={'set' if last_bar else 'none'}"
                )
                await asyncio.sleep(STREAM_RETRY_SLEEP_S)
            else:
                reconnect_start_time = start_time

            try:
                async with DXLinkStreamer(session) as streamer:
                    await streamer.subscribe_candle([self.symbol], self.interval, reconnect_start_time)

                    keepalive_task = asyncio.create_task(_dxlink_keepalive(streamer))
                    try:
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
                                    logger.info(
                                        f"Bar closed: {last_bar['start'].isoformat()} "
                                        f"O={last_bar['open']:.2f} H={last_bar['high']:.2f} "
                                        f"L={last_bar['low']:.2f} C={last_bar['close']:.2f}"
                                    )
                                    yield last_bar
                                    last_bar = bar
                                elif bar['time'] == last_bar['time']:
                                    last_bar = bar
                    finally:
                        keepalive_task.cancel()

                break  # clean exit

            except Exception as ex:
                logger.error(
                    f"stream_closed_bars error on attempt {attempt + 1}/{STREAM_MAX_RETRIES}: "
                    f"{type(ex).__name__}: {ex}",
                    exc_info=True,
                )
                if isinstance(ex, BaseExceptionGroup):
                    for i, sub in enumerate(ex.exceptions):
                        logger.error(
                            f"  stream sub-exception[{i}]: {type(sub).__name__}: {sub}",
                            exc_info=(type(sub), sub, sub.__traceback__),
                        )
                is_terminal = "Session not found" in str(ex)
                if is_terminal:
                    logger.error("stream_closed_bars: terminal error (Session not found), no retry")
                    raise
                if attempt == STREAM_MAX_RETRIES - 1:
                    logger.error(f"stream_closed_bars: exhausted {STREAM_MAX_RETRIES} retries, giving up")
                    raise
                logger.warning(
                    f"stream_closed_bars: retrying after error (attempt {attempt + 1} of {STREAM_MAX_RETRIES})"
                )

        logger.info("stream_closed_bars: exited retry loop normally")
