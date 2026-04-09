"""ORB Stacking demo CLI — Slice 12.

Read-only demo that prints trade intents and skip events from the
OrbStackingEngine driven by live DXLink bars or a historical replay.
No orders are placed. Safe to run alongside the live bot.

Usage:
  python orb_stacking_demo.py                        # live mode
  python orb_stacking_demo.py --replay 2026-04-08   # replay mode
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timezone

from dotenv import load_dotenv
from tastytrade import Session

from orb_stacking.bar_fetcher import BarFetcher
from orb_stacking.engine import OrbStackingEngine
from orb_stacking.time_utils import to_et, to_uk
from orb_stacking.trade_intent import OrbSkipEvent, OrbTradeIntent


SYMBOL = "SPX"
INTERVAL = "5m"
DEFAULT_LOOKBACK_DAYS = 1
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
    for bar in history_bars:
        engine._atr.update(bar)
    value = engine._atr.value
    value_text = f"{value:.2f}" if value is not None else "None"
    print(f"  ATR warmup: {len(history_bars)} bars, value={value_text}")


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
    print("Fetching history for ATR warmup...")
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
    today = to_et(datetime.now(timezone.utc)).date()
    lookback_days = max(2, (today - target_date).days + 1)
    fetcher = BarFetcher(SYMBOL, INTERVAL, lookback_days=lookback_days)
    print(f"Fetching bars for replay of {target_date}...")
    all_bars = await fetcher.fetch_history_with_retry(session)
    warmup_bars = [b for b in all_bars if to_et(b["start"]).date() < target_date]
    replay_bars = [b for b in all_bars if to_et(b["start"]).date() == target_date]
    warmup_engine(engine, warmup_bars)
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
