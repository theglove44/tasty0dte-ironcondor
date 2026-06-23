"""Iron Fly V1 historical backtest.

Replays one year or more of SPXW 0DTE data (downloaded by fetch_v1_backtest_data.py)
through the exact same entry/exit logic as the live bot:

  - Entry   : 10:00 ET  — sell ATM straddle, buy 10-point wings
  - ATM     : put-call parity (F = K + (C_mid – P_mid) → nearest 5-pt strike)
  - Exit PT : debit-to-close (mid-mark) ≤ initial_credit × 0.90 (10% profit target)
  - Exit TS : 13:00 ET time-stop regardless of P/L
  - Fill    : mid-mark (reconcile mode) and realistic bid/ask (slippage mode)

Usage
-----
    venv/bin/python tools/backtest_iron_fly_v1.py
    venv/bin/python tools/backtest_iron_fly_v1.py --start 2024-01-01 --end 2025-12-31
    venv/bin/python tools/backtest_iron_fly_v1.py --mode real   # bid/ask fills
    venv/bin/python tools/backtest_iron_fly_v1.py --reconcile   # compare vs paper_trades.csv

Requirements
------------
    data/v1_backtest/ must exist and contain parquet files from fetch_v1_backtest_data.py
    venv/bin/pip install pandas pyarrow
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "v1_backtest"
CSV_PATH = ROOT / "data" / "paper_trades.csv"

WING_WIDTH = 10          # dollars either side of ATM
PROFIT_TARGET_PCT = 0.10 # take off when current debit ≤ initial_credit × (1 − 0.10)
STRIKE_STEP = 5

ENTRY_TIME = (10, 0)    # ET
EXIT_TIME  = (13, 0)    # ET  (= 18:00 UK BST)

BACKTEST_START_DEFAULT = date(2022, 5, 23)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    date: date
    atm: int
    entry_credit_mid: float
    entry_credit_real: float
    exit_time: datetime
    exit_debit_mid: float
    exit_reason: str            # "PT" or "TS"
    pl_mid: float = field(init=False)
    pl_real: float = field(init=False)

    def __post_init__(self) -> None:
        self.pl_mid = round(self.entry_credit_mid - self.exit_debit_mid, 4)

    @property
    def win_mid(self) -> bool:
        return self.pl_mid > 0


# ---------------------------------------------------------------------------
# OSI helpers
# ---------------------------------------------------------------------------

def osi(expiry: date, side: str, strike: int) -> str:
    return f"SPXW  {expiry.strftime('%y%m%d')}{side.upper()}{strike * 1000:08d}"


def parse_strike(symbol: str) -> int:
    """Extract strike in dollars from OCC symbol (strike × 1000 encoded in last 8 chars)."""
    return int(symbol[-8:]) // 1000


def parse_side(symbol: str) -> str:
    return symbol[12].upper()  # 'C' or 'P'


# ---------------------------------------------------------------------------
# ATM via put-call parity
# ---------------------------------------------------------------------------

def find_atm(df_minute) -> int | None:
    """
    At entry minute, find ATM via put-call parity.

    For each matched call/put pair at same strike:
        F ≈ K + (C_mid − P_mid)
    Collect all pairs, take median F, round to nearest 5-pt grid.

    Returns None if fewer than 3 matched pairs exist.
    """
    calls = df_minute[df_minute["side"] == "C"][["strike", "mid"]].set_index("strike")
    puts  = df_minute[df_minute["side"] == "P"][["strike", "mid"]].set_index("strike")
    common = calls.index.intersection(puts.index)
    if len(common) < 3:
        return None
    forwards = []
    for k in common:
        c_mid = calls.loc[k, "mid"]
        p_mid = puts.loc[k, "mid"]
        if c_mid > 0 and p_mid > 0:
            forwards.append(k + (c_mid - p_mid))
    if not forwards:
        return None
    median_f = sorted(forwards)[len(forwards) // 2]
    return int(round(median_f / STRIKE_STEP) * STRIKE_STEP)


# ---------------------------------------------------------------------------
# Credit / debit calculators
# ---------------------------------------------------------------------------

def entry_credit(df_minute, atm: int, mode: str = "mid") -> float | None:
    """
    Iron fly credit = received from short straddle − paid for wings.

    mid  : (C_mid(ATM) + P_mid(ATM)) − (C_mid(ATM+10) + P_mid(ATM−10))
    real : (C_bid(ATM) + P_bid(ATM)) − (C_ask(ATM+10) + P_ask(ATM−10))
    """
    def get(side: str, strike: int, col: str) -> float | None:
        rows = df_minute[(df_minute["side"] == side) & (df_minute["strike"] == strike)]
        if rows.empty or rows[col].iloc[0] <= 0:
            return None
        return float(rows[col].iloc[0])

    lc_strike = atm + WING_WIDTH
    lp_strike = atm - WING_WIDTH

    if mode == "mid":
        sc = get("C", atm,      "mid")
        sp = get("P", atm,      "mid")
        lc = get("C", lc_strike, "mid")
        lp = get("P", lp_strike, "mid")
        if None in (sc, sp, lc, lp):
            return None
        return sc + sp - lc - lp
    else:  # real / slippage mode
        sc = get("C", atm,       "bid")
        sp = get("P", atm,       "bid")
        lc = get("C", lc_strike, "ask")
        lp = get("P", lp_strike, "ask")
        if None in (sc, sp, lc, lp):
            return None
        return sc + sp - lc - lp


def running_debit(df_minute, atm: int) -> float | None:
    """
    Mid-mark cost to close the position (buy back shorts, sell longs).

    debit = (C_mid(ATM) + P_mid(ATM)) − (C_mid(ATM+10) + P_mid(ATM−10))
    """
    def get_mid(side: str, strike: int) -> float | None:
        rows = df_minute[(df_minute["side"] == side) & (df_minute["strike"] == strike)]
        if rows.empty:
            return None
        v = float(rows["mid"].iloc[0])
        return v if v > 0 else None

    lc_strike = atm + WING_WIDTH
    lp_strike = atm - WING_WIDTH

    sc = get_mid("C", atm)
    sp = get_mid("P", atm)
    lc = get_mid("C", lc_strike)
    lp = get_mid("P", lp_strike)

    if None in (sc, sp):
        return None
    # If wing quotes missing (very OTM at EOD), treat wing value as 0
    lc = lc or 0.0
    lp = lp or 0.0
    return sc + sp - lc - lp


# ---------------------------------------------------------------------------
# Per-day simulation
# ---------------------------------------------------------------------------

def _monitor_1s(df_legs, atm: int, initial_credit: float,
                entry_dt: datetime, exit_limit: datetime) -> tuple[datetime, float, str]:
    """
    Second-by-second exit monitoring using the Phase 2 cbbo-1s leg file.
    Returns (exit_time, final_debit, reason).
    """
    import pandas as pd

    df = df_legs.copy()
    df["ts_et"] = pd.to_datetime(df["ts_et"])
    df["side"]   = df["symbol"].str[12].str.upper()
    df["strike"] = (df["symbol"].str[-8:].astype(int) // 1000).astype(int)

    lc_strike = atm + WING_WIDTH
    lp_strike = atm - WING_WIDTH
    target_debit = initial_credit * (1 - PROFIT_TARGET_PCT)

    df["ts_s"] = df["ts_et"].dt.floor("s")

    # Build per-symbol ts→mid dicts: avoids per-second pandas overhead entirely.
    # Each legs file has exactly 4 symbols (~11k rows each), so 4 small filters.
    # Only store positive, non-NaN values so NaN mid prices never reach debit calc.
    def _ts_mid(side: str, strike: int) -> dict:
        sub = df[(df["side"] == side) & (df["strike"] == strike)]
        return {ts: m for ts, m in zip(sub["ts_s"], sub["mid"]) if m == m and m > 0}

    c_atm = _ts_mid("C", atm)
    p_atm = _ts_mid("P", atm)
    c_lc  = _ts_mid("C", lc_strike)
    p_lp  = _ts_mid("P", lp_strike)

    seconds = sorted(df["ts_s"].unique())

    last_debit = None
    for ts in seconds:
        if ts <= entry_dt:
            continue
        if ts > exit_limit:
            break

        sc = c_atm.get(ts, 0.0)
        sp = p_atm.get(ts, 0.0)
        if sc == 0.0 or sp == 0.0:
            continue
        lc = c_lc.get(ts, 0.0)
        lp = p_lp.get(ts, 0.0)
        debit = sc + sp - lc - lp
        last_debit = debit

        if debit <= target_debit:
            return ts, debit, "PT"

    return exit_limit, last_debit or 0.0, "TS"


def simulate_day(day: date, df_raw, mode: str = "mid",
                 df_legs_1s=None) -> Trade | None:
    """
    Replay one trading day. Returns a Trade or None (no entry / no data).

    df_legs_1s: optional Phase 2 DataFrame (cbbo-1s for 4 legs).
                If provided, exit monitoring uses 1-second resolution
                instead of 1-minute, eliminating most PT trigger misses.
    """
    import pandas as pd

    # Parse symbol → side + strike, add columns
    df = df_raw.copy()
    df["side"]   = df["symbol"].str[12].str.upper()
    df["strike"] = (df["symbol"].str[-8:].astype(int) // 1000).astype(int)

    # Keep only 0DTE expiry for this day
    day_str = day.strftime("%y%m%d")
    df = df[df["symbol"].str[6:12] == day_str]

    if df.empty:
        return None

    if "ts_et" in df.columns:
        df["ts_et"] = pd.to_datetime(df["ts_et"], utc=False)

    # Precompute floored timestamps once (single pass over the DataFrame)
    ts_floored = df["ts_et"].dt.floor("min")

    # ---- Entry at 10:00 ET ----
    entry_dt = datetime(day.year, day.month, day.day, *ENTRY_TIME, tzinfo=ET)
    entry_rows = df[ts_floored == entry_dt]

    if entry_rows.empty:
        return None

    atm = find_atm(entry_rows)
    if atm is None:
        return None

    ec_mid  = entry_credit(entry_rows, atm, "mid")
    ec_real = entry_credit(entry_rows, atm, "real")
    if ec_mid is None or ec_mid <= 0:
        return None

    target_debit = ec_mid * (1 - PROFIT_TARGET_PCT)
    exit_limit   = datetime(day.year, day.month, day.day, *EXIT_TIME, tzinfo=ET)

    # ---- 1-second exit monitoring (Phase 2) ----
    if df_legs_1s is not None and not df_legs_1s.empty:
        exit_dt, final_debit, exit_reason = _monitor_1s(
            df_legs_1s, atm, ec_mid, entry_dt, exit_limit
        )
        if final_debit == 0.0:
            final_debit = None
    else:
        # ---- Fallback: 1-minute monitoring ----
        # Pre-build per-symbol ts→mid dicts for O(1) lookup (avoids per-minute pandas ops)
        lc_strike = atm + WING_WIDTH
        lp_strike = atm - WING_WIDTH
        df["ts_min"] = ts_floored

        def _mid_1m(side: str, strike: int) -> dict:
            sub = df[(df["side"] == side) & (df["strike"] == strike)]
            return {ts: m for ts, m in zip(sub["ts_min"], sub["mid"]) if m == m and m > 0}

        c_atm_m = _mid_1m("C", atm)
        p_atm_m = _mid_1m("P", atm)
        c_lc_m  = _mid_1m("C", lc_strike)
        p_lp_m  = _mid_1m("P", lp_strike)

        minutes = sorted(ts_floored.unique())
        exit_dt     = exit_limit
        exit_reason = "TS"
        final_debit = None

        for minute in minutes:
            if minute <= entry_dt:
                continue
            sc = c_atm_m.get(minute, 0.0)
            sp = p_atm_m.get(minute, 0.0)
            if sc <= 0 or sp <= 0:
                continue
            lc = c_lc_m.get(minute, 0.0)
            lp = p_lp_m.get(minute, 0.0)
            debit = sc + sp - lc - lp
            final_debit = debit
            if debit <= target_debit:
                exit_reason = "PT"
                exit_dt = minute
                break

    if final_debit is None:
        return None

    return Trade(
        date=day,
        atm=atm,
        entry_credit_mid=round(ec_mid,  4),
        entry_credit_real=round(ec_real or 0.0, 4),
        exit_time=exit_dt,
        exit_debit_mid=round(final_debit, 4),
        exit_reason=exit_reason,
    )


# ---------------------------------------------------------------------------
# Reconciliation vs paper_trades.csv
# ---------------------------------------------------------------------------

def load_paper_v1(start: date, end: date) -> list[dict]:
    """Load Iron Fly V1 closed trades from paper_trades.csv in the overlap window."""
    import csv
    rows = []
    if not CSV_PATH.exists():
        return rows
    with open(CSV_PATH, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("Strategy") != "Iron Fly V1":
                continue
            if row.get("Status") not in ("CLOSED", "EXPIRED"):
                continue
            try:
                d = date.fromisoformat(row["Date"])
            except ValueError:
                continue
            if start <= d <= end:
                try:
                    rows.append({
                        "date": d,
                        "credit": float(row.get("Credit Collected", 0)),
                        "pl": float(row.get("Exit P/L", 0)),
                        "notes": row.get("Notes", ""),
                    })
                except (ValueError, KeyError):
                    pass
    return rows


def reconcile(trades: list[Trade], start: date, end: date) -> None:
    """Print side-by-side comparison of backtest vs paper for overlapping dates."""
    paper = {r["date"]: r for r in load_paper_v1(start, end)}
    bt    = {t.date: t for t in trades}
    shared = sorted(set(paper) & set(bt))

    if not shared:
        print("\nReconciliation: no overlapping dates between backtest and paper_trades.csv")
        return

    print(f"\n{'='*72}")
    print(f"RECONCILIATION  ({len(shared)} shared days)")
    print(f"{'='*72}")
    hdr = f"{'Date':<12} {'Paper Cr':>9} {'BT Cr(mid)':>11} {'Paper P/L':>10} {'BT P/L':>8} {'Match':>6}"
    print(hdr)
    print("-" * 72)

    credit_diffs = []
    pl_diffs = []
    for d in shared:
        p = paper[d]
        b = bt[d]
        cr_diff = b.entry_credit_mid - p["credit"]
        pl_diff = b.pl_mid - p["pl"]
        credit_diffs.append(cr_diff)
        pl_diffs.append(pl_diff)
        match = "✓" if abs(cr_diff) < 1.0 else "?"
        print(f"{d!s:<12} {p['credit']:>9.2f} {b.entry_credit_mid:>11.2f} "
              f"{p['pl']:>10.2f} {b.pl_mid:>8.2f} {match:>6}")

    n = len(credit_diffs)
    avg_cr_diff = sum(credit_diffs) / n
    avg_pl_diff = sum(pl_diffs) / n
    print("-" * 72)
    print(f"{'Average diff':>40}  cr={avg_cr_diff:+.2f}   pl={avg_pl_diff:+.2f}")
    print()
    print("If credit diff is consistently ≈ 0, mid-fill is matching live fills.")
    print("If it's consistently +, the live bot was getting better fills than mid.")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(trades: list[Trade]) -> None:
    if not trades:
        print("No trades simulated.")
        return

    wins   = [t for t in trades if t.win_mid]
    losses = [t for t in trades if not t.win_mid]
    total_pl = sum(t.pl_mid for t in trades)
    avg_pl   = total_pl / len(trades)
    wr       = len(wins) / len(trades) * 100
    avg_win  = sum(t.pl_mid for t in wins)  / max(len(wins), 1)
    avg_loss = sum(t.pl_mid for t in losses) / max(len(losses), 1)
    payoff   = abs(avg_win / avg_loss) if avg_loss and avg_win else 0.0
    pts      = [t for t in trades if t.exit_reason == "PT"]
    tss      = [t for t in trades if t.exit_reason == "TS"]

    print(f"\n{'='*60}")
    print(f"IRON FLY V1 BACKTEST RESULTS  ({len(trades)} sessions)")
    print(f"{'='*60}")
    print(f"  Total P/L (mid)   : ${total_pl:+.2f}")
    print(f"  Avg P/L / trade   : ${avg_pl:+.4f}")
    print(f"  Win rate          : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Avg win           : ${avg_win:+.2f}")
    print(f"  Avg loss          : ${avg_loss:+.2f}")
    print(f"  Payoff ratio      : {payoff:.2f}x")
    print(f"  PT exits          : {len(pts)}  ({len(pts)/len(trades)*100:.1f}%)")
    print(f"  TS exits          : {len(tss)}  ({len(tss)/len(trades)*100:.1f}%)")

    # Monthly breakdown
    by_month: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        by_month[t.date.strftime("%Y-%m")].append(t)

    print(f"\n  Monthly P/L (mid-fill):")
    print(f"  {'Month':<8}  {'Trades':>6}  {'P/L':>8}  {'WR':>7}")
    for month in sorted(by_month):
        mt = by_month[month]
        mpl = sum(t.pl_mid for t in mt)
        mwr = sum(1 for t in mt if t.win_mid) / len(mt) * 100
        print(f"  {month:<8}  {len(mt):>6}  {mpl:>+8.2f}  {mwr:>6.1f}%")

    print(f"{'='*60}")

    # Entry credit distribution
    credits = sorted(t.entry_credit_mid for t in trades)
    n = len(credits)
    p25 = credits[n // 4]
    p50 = credits[n // 2]
    p75 = credits[3 * n // 4]
    avg_cr = sum(credits) / n
    print(f"\n  Entry credit (mid) distribution over {n} sessions:")
    print(f"  avg={avg_cr:.2f}  p25={p25:.2f}  p50={p50:.2f}  p75={p75:.2f}")
    print(f"  min={credits[0]:.2f}  max={credits[-1]:.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", default=str(BACKTEST_START_DEFAULT))
    parser.add_argument("--end",   default=str(date.today() - timedelta(days=1)))
    parser.add_argument("--mode",  choices=["mid", "real"], default="mid",
                        help="mid = mid-mark fills; real = bid/ask fills")
    parser.add_argument("--reconcile", action="store_true",
                        help="Cross-check backtest vs paper_trades.csv on overlapping dates")
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError:
        sys.exit("Install pandas: venv/bin/pip install pandas pyarrow")

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    # Discover available Phase 1 parquet files (no suffix = 1m chain data)
    parquet_files: dict[date, Path] = {}
    for p in sorted(DATA_DIR.rglob("*.parquet")):
        if "_legs_1s" in p.stem:
            continue
        try:
            d = date.fromisoformat(p.stem)
            if start <= d <= end:
                parquet_files[d] = p
        except ValueError:
            pass

    if not parquet_files:
        sys.exit(
            f"No parquet files found in {DATA_DIR} for {start} → {end}.\n"
            "Run:  venv/bin/python tools/fetch_v1_backtest_data.py --confirm"
        )

    # Check how many 1s leg files are available
    legs_files: dict[date, Path] = {}
    for p in sorted(DATA_DIR.rglob("*_legs_1s.parquet")):
        try:
            d = date.fromisoformat(p.stem.replace("_legs_1s", ""))
            if start <= d <= end:
                legs_files[d] = p
        except ValueError:
            pass

    resolution = "1s" if legs_files else "1m"
    print(f"Replaying {len(parquet_files)} sessions  [{start} → {end}]  "
          f"mode={args.mode}  exit-resolution={resolution} "
          f"({len(legs_files)}/{len(parquet_files)} days with 1s legs)")

    trades: list[Trade] = []
    skipped = 0

    for day, path in sorted(parquet_files.items()):
        df = pd.read_parquet(path)
        if df.empty:
            skipped += 1
            continue

        df_legs = None
        if day in legs_files:
            df_legs = pd.read_parquet(legs_files[day])

        trade = simulate_day(day, df, mode=args.mode, df_legs_1s=df_legs)
        if trade is None:
            skipped += 1
            print(f"  {day}  SKIP — no valid entry (missing data or zero credit)")
        else:
            trades.append(trade)

    print(f"  {skipped} sessions skipped (holiday / missing data)")

    print_report(trades)

    if args.reconcile:
        reconcile(trades, start, end)


if __name__ == "__main__":
    main()
