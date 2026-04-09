"""Slice 13 — Historical backtest gate for ORB Stacking.
Ingests SPX 5m CSVs (2010–2026), replays each ET session through
OrbStackingEngine, reproduces Doc1 §4.1 permutation table, asserts gates.

Usage:
    venv/bin/python -m tools.backtest_orb_stacking [--docs-dir docs]
Exit code: 0 on gate pass, 1 on gate fail.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from collections import Counter, deque
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

import pytz

from orb_stacking.engine import OrbStackingEngine
from orb_stacking.time_utils import to_et
from orb_stacking.trade_intent import OrbSkipEvent, OrbTradeIntent


DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
CSV_GLOB = "SPX 5 min + MACDv*.txt"
MIN_BARS_PER_SESSION = 10
GATE_PLUS_THRESHOLD = 0.780
GATE_DOUBLE_THRESHOLD = 0.880
UK_TZ = pytz.timezone("Europe/London")


@dataclass
class Bar:
    start: datetime
    open: float
    high: float
    low: float
    close: float

    def as_dict(self) -> dict:
        return {
            "start": self.start,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": 0.0,
            "time": int(self.start.timestamp() * 1000),
        }


@dataclass
class SessionResult:
    session_date: date
    bar_count: int
    session_open: float
    session_close: float
    direction: Optional[str]
    last_stack_tier: str
    closes_aligned_count: int
    reached_orb20_break: bool
    orb30_confirmed: bool
    orb30_opposed: bool
    orb60_confirmed: bool
    orb60_opposed: bool
    no_breakout_before_noon: bool
    aborted: bool
    category: str
    day_fav: Optional[bool]


def _parse_timestamp(date_str: str, time_str: str) -> Optional[datetime]:
    naive = datetime.strptime(f"{date_str} {time_str}", "%m/%d/%Y %H:%M")
    try:
        localized = UK_TZ.localize(naive, is_dst=None)
    except pytz.AmbiguousTimeError:
        localized = UK_TZ.localize(naive, is_dst=False)
    except pytz.NonExistentTimeError:
        return None
    return localized.astimezone(pytz.UTC)


def parse_csv_file(path: Path) -> Iterator[Bar]:
    # CSV uses end-of-bar labeling: the timestamp is the bar's CLOSE time.
    # OrbBuilder expects start-of-bar timestamps. Subtract one interval.
    from datetime import timedelta
    _interval = timedelta(minutes=5)
    with path.open("r", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if len(row) < 6:
                continue
            ts = _parse_timestamp(row[0], row[1])
            if ts is None:
                continue
            yield Bar(
                start=ts - _interval,
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
            )


def load_all_bars(docs_dir: Path) -> list[Bar]:
    deduped: list[Bar] = []
    seen: set[datetime] = set()
    for path in sorted(docs_dir.glob(CSV_GLOB)):
        for bar in parse_csv_file(path):
            if bar.start in seen:
                continue
            seen.add(bar.start)
            deduped.append(bar)
    deduped.sort(key=lambda bar: bar.start)
    return deduped


def classify_session(r: SessionResult) -> str:
    if not r.reached_orb20_break:
        return "no_break_before_noon"
    if r.aborted:
        return "no_break_before_noon"
    if r.last_stack_tier == "DOUBLE":
        return "double"
    if r.orb60_confirmed:
        return "plus"
    if r.orb60_opposed:
        return "orb60_opposes"
    if r.orb30_opposed:
        return "orb30_opposes"
    if r.no_breakout_before_noon:
        return "no_break_before_noon"
    if r.last_stack_tier == "NORMAL":
        return "orb60_no_breakout"
    if r.last_stack_tier == "HALF":
        return "half_only"
    return "no_break_before_noon"


def _day_favorable(direction: Optional[str], session_open: float, session_close: float) -> Optional[bool]:
    if direction == "bull":
        return session_close > session_open
    if direction == "bear":
        return session_close < session_open
    return None


def run_session(
    engine: OrbStackingEngine,
    session_bars: list[Bar],
    warmup_bars: list[Bar],
) -> SessionResult:
    engine.reset_for_new_session()
    for warmup_bar in warmup_bars:
        engine._atr.update(warmup_bar.as_dict())

    reached_orb20_break = False
    orb30_confirmed = False
    orb30_opposed = False
    orb60_confirmed = False
    orb60_opposed = False
    no_breakout_before_noon = False
    aborted = False
    last_stack_tier = "FLAT"
    direction: Optional[str] = None
    closes_aligned_count = 0

    for bar in session_bars:
        events = engine.on_closed_bar(bar.as_dict())
        for event in events:
            if isinstance(event, OrbTradeIntent):
                last_stack_tier = event.stack_tier
                direction = event.direction
                closes_aligned_count = event.closes_aligned_count
                reached_orb20_break = True
                if event.stack_tier in ("NORMAL", "PLUS", "DOUBLE"):
                    orb30_confirmed = True
                if event.stack_tier in ("PLUS", "DOUBLE"):
                    orb60_confirmed = True
            elif isinstance(event, OrbSkipEvent):
                if event.reason == "orb30_opposes_warning":
                    orb30_opposed = True
                elif event.reason == "orb60_opposes_hard_exit":
                    orb60_opposed = True
                    if direction is None:
                        direction = event.direction
                elif event.reason == "no_breakout_before_noon":
                    no_breakout_before_noon = True
                elif event.reason in {"api_error", "credit_too_low"}:
                    aborted = True
                if direction is None:
                    direction = event.direction

    result = SessionResult(
        session_date=to_et(session_bars[0].start).date(),
        bar_count=len(session_bars),
        session_open=session_bars[0].open,
        session_close=session_bars[-1].close,
        direction=direction,
        last_stack_tier=last_stack_tier,
        closes_aligned_count=closes_aligned_count,
        reached_orb20_break=reached_orb20_break,
        orb30_confirmed=orb30_confirmed,
        orb30_opposed=orb30_opposed,
        orb60_confirmed=orb60_confirmed,
        orb60_opposed=orb60_opposed,
        no_breakout_before_noon=no_breakout_before_noon,
        aborted=aborted,
        category="",
        day_fav=None,
    )
    result.category = classify_session(result)
    result.day_fav = _day_favorable(result.direction, result.session_open, result.session_close)
    return result


def aggregate(results: list[SessionResult]) -> dict:
    by_category = Counter(result.category for result in results)
    day_fav_by_category = Counter(
        result.category for result in results if result.day_fav is True
    )

    plus_count = by_category["plus"] + by_category["double"]
    plus_day_fav = day_fav_by_category["plus"] + day_fav_by_category["double"]
    double_count = by_category["double"]
    double_day_fav = day_fav_by_category["double"]

    plus_rate = (plus_day_fav / plus_count) if plus_count else 0.0
    double_rate = (double_day_fav / double_count) if double_count else 0.0

    return {
        "total": len(results),
        "by_category": dict(by_category),
        "day_fav_by_category": dict(day_fav_by_category),
        "plus_count": plus_count,
        "plus_day_fav": plus_day_fav,
        "plus_rate": plus_rate,
        "double_count": double_count,
        "double_day_fav": double_day_fav,
        "double_rate": double_rate,
    }


def print_report(agg: dict, gate_pass: bool, skipped_sessions: int = 0) -> None:
    categories = [
        ("half_only",            "ORB20 break → HALF only"),
        ("plus",                 "  + ORB60 confirms → PLUS"),
        ("double",               "    + all closes aligned → DOUBLE"),
        ("orb30_opposes",        "ORB30 opposes"),
        ("orb60_opposes",        "ORB60 opposes"),
        ("orb60_no_breakout",    "ORB60 no breakout"),
        ("no_break_before_noon", "No breakout before noon"),
    ]

    total = agg["total"]
    print("ORB Stacking Backtest — 21yr SPX 5m")
    print(f"Sessions processed: {total}")
    if skipped_sessions:
        print(f"Sessions skipped (< {MIN_BARS_PER_SESSION} bars): {skipped_sessions}")
    print()
    print(f"{'Permutation':<38} {'Days':>6} {'%':>6} {'Day-Fav':>8}")
    print("-" * 62)
    for key, label in categories:
        count = agg["by_category"].get(key, 0)
        fav = agg["day_fav_by_category"].get(key, 0)
        pct = count / total if total else 0.0
        rate = (fav / count) if count else 0.0
        print(f"{label:<38} {count:>6} {pct:>5.1%} {rate:>7.1%}")

    print("-" * 62)
    plus_label = "PLUS+DOUBLE (gate ≥ 78.0%)"
    double_label = "  DOUBLE (gate ≥ 88.0%)"
    for label, count, fav, rate, threshold in [
        (plus_label,   agg["plus_count"],   agg["plus_day_fav"],   agg["plus_rate"],   GATE_PLUS_THRESHOLD),
        (double_label, agg["double_count"], agg["double_day_fav"], agg["double_rate"], GATE_DOUBLE_THRESHOLD),
    ]:
        status = "PASS" if rate >= threshold else "FAIL"
        print(f"{label:<38} {count:>6}       {rate:>7.1%}  {status}")

    print()
    print(f"Gate: {'PASS' if gate_pass else 'FAIL'} "
          f"(PLUS={agg['plus_rate']:.1%} ≥ {GATE_PLUS_THRESHOLD:.1%}, "
          f"DOUBLE={agg['double_rate']:.1%} ≥ {GATE_DOUBLE_THRESHOLD:.1%})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    bars = load_all_bars(docs_dir)
    engine = OrbStackingEngine()

    results: list[SessionResult] = []
    skipped_sessions = 0
    warmup_sessions: deque[list[Bar]] = deque(maxlen=15)

    grouped = itertools.groupby(bars, key=lambda bar: to_et(bar.start).date())
    for session_date, bar_iter in grouped:
        session_bars = list(bar_iter)
        if args.start is not None and session_date.year < args.start:
            warmup_sessions.append(session_bars)
            continue
        if args.end is not None and session_date.year > args.end:
            break

        warmup_bars = [bar for session in warmup_sessions for bar in session]
        if len(session_bars) < MIN_BARS_PER_SESSION:
            skipped_sessions += 1
            warmup_sessions.append(session_bars)
            continue

        results.append(run_session(engine, session_bars, warmup_bars))
        warmup_sessions.append(session_bars)

    agg = aggregate(results)
    gate_pass = (
        agg["plus_rate"] >= GATE_PLUS_THRESHOLD
        and agg["double_rate"] >= GATE_DOUBLE_THRESHOLD
    )
    print_report(agg, gate_pass, skipped_sessions=skipped_sessions)
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
