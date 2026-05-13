"""ORB Stacking demo CLI — Slice 12.

Read-only demo that prints trade intents and skip events from the
OrbStackingEngine driven by live DXLink bars or a historical replay.
No orders are placed. Safe to run alongside the live bot.

Usage:
  python tools/orb_stacking_demo.py                        # live mode
  python tools/orb_stacking_demo.py --replay 2026-04-08   # replay mode
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from tastytrade import Session

from orb_stacking.bar_fetcher import (
    BarFetcher,
    trading_lookback_days,
    fetch_daily_bars,
    MIN_DAILY_BARS_FOR_ATR,
)
from orb_stacking.engine import OrbStackingEngine
from orb_stacking.time_utils import to_et, to_uk
from orb_stacking.trade_intent import OrbSkipEvent, OrbTradeIntent


SYMBOL = "SPX"
INTERVAL = "5m"
DEFAULT_LOOKBACK_DAYS = trading_lookback_days()
TERMINAL_SKIP_REASONS = frozenset({"no_breakout_before_noon", "orb60_opposes_hard_exit"})


def _uk_hhmm(dt: datetime) -> str:
    return to_uk(dt).strftime("%H:%M UK")


def format_intent(intent: OrbTradeIntent) -> str:
    labels_suffix = (
        f" [{','.join(intent.calendar_labels)}]" if intent.calendar_labels else ""
    )
    return (
        f"[{_uk_hhmm(intent.timestamp)}] INTENT {intent.stack_tier} {intent.direction} | "
        f"{intent.spread_side} {intent.short_strike:.0f}/{intent.long_strike:.0f} | "
        f"{intent.contracts}x | base={intent.base_tier} "
        f"score={intent.stack_score}+{intent.base_score} | "
        f"re={intent.range_expansion_ratio:.2f} | "
        f"cal={intent.calendar_score}{labels_suffix}"
    )


def format_skip(skip: OrbSkipEvent) -> str:
    notes_suffix = f" | notes={skip.notes}" if skip.notes else ""
    direction = skip.direction or "-"
    return (
        f"[{_uk_hhmm(skip.timestamp)}] SKIP  {skip.reason} | "
        f"dir={direction} | tier={skip.stack_tier}{notes_suffix}"
    )


def warmup_engine(engine: OrbStackingEngine, history_bars: list[dict]) -> None:
    """Feed today's 5m bars through engine.on_closed_bar. ATR is seeded
    separately from daily bars via seed_daily_atr."""
    today_et = to_et(datetime.now(timezone.utc)).date()
    for bar in history_bars:
        if to_et(bar["start"]).date() == today_et:
            engine.on_closed_bar(bar)


async def seed_daily_atr(session: Session, engine: OrbStackingEngine) -> None:
    """Fetch and feed daily bars to _atr. Prints a status line."""
    daily_bars = await fetch_daily_bars(session, symbol=SYMBOL)
    if len(daily_bars) < MIN_DAILY_BARS_FOR_ATR:
        print(f"  ATR warmup: only {len(daily_bars)} daily bars available, "
              f"ATR will be None. ORB20 break will skip with atr_not_ready.")
        return
    seed_bars = daily_bars[-MIN_DAILY_BARS_FOR_ATR:]
    for bar in seed_bars:
        engine._atr.update(bar)
    print(f"  ATR(14) seeded from {len(seed_bars)} daily bars, "
          f"value={engine._atr.value:.2f}")


def print_events(events: list) -> bool:
    terminal = False
    for ev in events:
        if isinstance(ev, OrbTradeIntent):
            print(format_intent(ev))
        elif isinstance(ev, OrbSkipEvent):
            print(format_skip(ev))
            if ev.reason in TERMINAL_SKIP_REASONS:
                terminal = True
    return terminal


async def run_live(session: Session, engine: OrbStackingEngine) -> None:
    fetcher = BarFetcher(SYMBOL, INTERVAL, lookback_days=DEFAULT_LOOKBACK_DAYS)
    print("Seeding ATR(14) from daily bars...")
    await seed_daily_atr(session, engine)
    print("Fetching 5m history for engine warmup...")
    history = await fetcher.fetch_history_with_retry(session)
    warmup_engine(engine, history)
    print("Starting live bar stream. Ctrl-C to stop.")
    async for bar in fetcher.stream_closed_bars(session):
        today_et = to_et(datetime.now(timezone.utc)).date()
        if to_et(bar["start"]).date() != today_et:
            continue
        events = engine.on_closed_bar(bar)
        terminal = print_events(events)
        if terminal:
            print("Session complete.")
            break


async def run_replay(session: Session, target_date: date, engine: OrbStackingEngine) -> None:
    """Replay a past session. ATR is seeded by aggregating 5m bars into daily
    OHLC for the 14 completed sessions before target_date, matching backtest
    semantics."""
    today = to_et(datetime.now(timezone.utc)).date()
    # Extra calendar days so 5m fetch covers 14+ prior trading sessions
    lookback_days = trading_lookback_days(n=MIN_DAILY_BARS_FOR_ATR + 4) + (today - target_date).days
    fetcher = BarFetcher(SYMBOL, INTERVAL, lookback_days=lookback_days)
    print(f"Fetching 5m bars for replay of {target_date}...")
    all_bars = await fetcher.fetch_history_with_retry(session)

    # Aggregate prior-session 5m bars into daily OHLC, feed last 14 to _atr
    prior_bars = [b for b in all_bars if to_et(b["start"]).date() < target_date]
    by_date: dict = {}
    for bar in prior_bars:
        d = to_et(bar["start"]).date()
        if d not in by_date:
            by_date[d] = {"start": bar["start"], "open": bar["open"],
                          "high": bar["high"], "low": bar["low"], "close": bar["close"]}
        else:
            agg = by_date[d]
            agg["high"] = max(agg["high"], bar["high"])
            agg["low"] = min(agg["low"], bar["low"])
            agg["close"] = bar["close"]

    daily_bars = [by_date[d] for d in sorted(by_date)]
    if len(daily_bars) >= MIN_DAILY_BARS_FOR_ATR:
        seed_bars = daily_bars[-MIN_DAILY_BARS_FOR_ATR:]
        for bar in seed_bars:
            engine._atr.update(bar)
        print(f"  ATR(14) seeded from {len(seed_bars)} aggregated daily bars, "
              f"value={engine._atr.value:.2f}")
    else:
        print(f"  ATR warmup: only {len(daily_bars)} prior sessions available, "
              f"ATR will be None.")

    replay_bars = [b for b in all_bars if to_et(b["start"]).date() == target_date]
    print(f"Replaying {len(replay_bars)} bars for {target_date}...")
    for bar in replay_bars:
        events = engine.on_closed_bar(bar)
        print_events(events)
    print(f"Replay complete: {target_date} ({len(replay_bars)} bars processed)")


async def main_async(args: argparse.Namespace) -> None:
    load_dotenv()
    rt = os.getenv("TASTY_REFRESH_TOKEN")
    cs = os.getenv("TASTY_CLIENT_SECRET")
    if not rt or not cs:
        print(
            "Missing TASTY_REFRESH_TOKEN or TASTY_CLIENT_SECRET in environment.",
            file=sys.stderr,
        )
        sys.exit(2)
    print("Connecting to tastytrade...")
    session = Session(provider_secret=cs, refresh_token=rt)
    print("Connected.")
    engine = OrbStackingEngine()
    if args.replay_date:
        await run_replay(session, args.replay_date, engine)
    else:
        await run_live(session, engine)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ORB Stacking demo CLI")
    parser.add_argument(
        "--replay",
        metavar="DATE",
        dest="replay_date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Replay a specific date (YYYY-MM-DD) from DXLink history",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted — exiting cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    main()
