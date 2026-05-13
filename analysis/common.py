"""
Shared utilities for the trade-analysis scripts in this directory.

Centralises the things every analysis needs to do consistently:

- Load paper_trades.csv with the right dtype coercions
- DST-normalised entry/exit timing (minutes after US market open)
- Outlier filter (anomalous credit logging, primarily 2026-03-20)
- Private-strategy exclusion (custom strategies kept out of public analysis)
- Streak detection, drawdown episode detection, bucket labelling

If you add a new analysis script, import from here rather than re-implementing.
"""

from __future__ import annotations

import re
import sys
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

# --- Paths -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_paths import PAPER_TRADES_CSV, PUBLIC_SITE_DIR as PROJECT_PUBLIC_SITE_DIR

CSV_PATH = PAPER_TRADES_CSV
PUBLIC_SITE_DIR = PROJECT_PUBLIC_SITE_DIR
DATA_JS_PATH = PUBLIC_SITE_DIR / "data.js"


# --- Strategy exclusions -----------------------------------------------------

# Custom/proprietary strategies are kept out of public analysis.
PRIVATE_STRATEGY_PREFIXES = ("JadeLizard",)
PRIVATE_STRATEGY_EXACT = {
    "Premium Popper",
    "ORB-STACK-HALF",
    "ORB-STACK-NORMAL",
    "ORB-STACK-PLUS",
}


def is_private_strategy(name: str) -> bool:
    return name in PRIVATE_STRATEGY_EXACT or name.startswith(PRIVATE_STRATEGY_PREFIXES)


# --- Outlier filter ----------------------------------------------------------

# Trades with credit > $30 are anomalous in this dataset (typical is $5-15).
# The known cases are 5 trades on 2026-03-20 with credits of $64-70 that
# appear to be logging quirks rather than real positions.
OUTLIER_CREDIT_THRESHOLD = 30.0


# --- DST normalisation -------------------------------------------------------

# US clocks moved forward 2026-03-08. UK clocks didn't move until 2026-03-29.
# During that window, US market open at 9:30 ET corresponded to 13:30 UK
# instead of the usual 14:30 UK.
US_DST_START = date(2026, 3, 8)
UK_BST_START = date(2026, 3, 29)


def market_open_uk(d: date) -> time:
    """Return US market open (9:30 ET) expressed in UK local time for date d."""
    if US_DST_START <= d < UK_BST_START:
        return time(13, 30)
    return time(14, 30)


def minutes_after_open(entry_date: date, entry_time_str: str) -> int:
    """Compute minutes elapsed from US market open at the trade's entry time."""
    h, m, _ = entry_time_str.split(":")
    op = market_open_uk(entry_date)
    return (int(h) * 60 + int(m)) - (op.hour * 60 + op.minute)


def bucket_label(minutes: int) -> str:
    """Format a minutes-after-open integer as a human-readable bucket."""
    if minutes == 0:
        return "OPEN"
    sign = "+" if minutes > 0 else "-"
    absmin = abs(minutes)
    h, m = absmin // 60, absmin % 60
    if h == 0:
        return f"{sign}{m}m"
    return f"{sign}{h}h{m:02d}m" if m else f"{sign}{h}h00m"


# --- Loading -----------------------------------------------------------------

def load_trades(
    csv_path: str | Path = CSV_PATH,
    *,
    closed_only: bool = True,
    drop_private: bool = True,
    drop_outliers: bool = True,
) -> pd.DataFrame:
    """Load and prep the trades CSV with the project's standard filters.

    Args:
        csv_path: location of paper_trades.csv (defaults to project root).
        closed_only: drop OPEN positions and rows missing Exit P/L.
        drop_private: drop private/custom strategies.
        drop_outliers: drop rows with Credit Collected > OUTLIER_CREDIT_THRESHOLD.

    Returns a DataFrame with numeric columns coerced and derived columns added:
        - 'EntryMAO' / 'ExitMAO': minutes after open for entry and exit
        - 'Bucket5': entry bucket rounded to nearest 5 minutes
        - 'DOW': day of week ('Monday'..'Friday')
        - 'Month': 'YYYY-MM'
    """
    df = pd.read_csv(csv_path)
    for col in ("Exit P/L", "Credit Collected", "Buying Power", "IV Rank", "SPX Spot"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Date"] = pd.to_datetime(df["Date"]).dt.date

    if drop_private:
        df = df[~df["Strategy"].apply(is_private_strategy)].copy()
    if closed_only:
        df = df[df["Status"].isin(["CLOSED", "EXPIRED"])].dropna(subset=["Exit P/L"]).copy()
    if drop_outliers:
        df = df[df["Credit Collected"] <= OUTLIER_CREDIT_THRESHOLD].copy()

    df["EntryMAO"] = df.apply(
        lambda r: minutes_after_open(r["Date"], r["Entry Time"]), axis=1
    )

    def _exit_mao(r):
        if pd.isna(r["Exit Time"]) or r["Exit Time"] == "":
            return None
        try:
            return minutes_after_open(r["Date"], r["Exit Time"])
        except Exception:
            return None

    df["ExitMAO"] = df.apply(_exit_mao, axis=1)
    df["Bucket5"] = (5 * (df["EntryMAO"] / 5).round()).astype(int)
    df["DOW"] = pd.to_datetime(df["Date"]).dt.day_name()
    df["Month"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m")

    return df.sort_values(["Date", "Entry Time"]).reset_index(drop=True)


# --- SPX day-move derivation -------------------------------------------------

def derive_day_move_pct(df: pd.DataFrame) -> pd.Series:
    """Best-effort SPX percent move per trading day.

    Uses the first trade's strike (close to ATM at entry) as the day-open proxy,
    and the 'Settled at X' value parsed from Notes as the close. Returns a Series
    keyed by Date in pct (so 1.0 = 1%).
    """

    def _spx_entry(r):
        if pd.notna(r["SPX Spot"]) and r["SPX Spot"] > 0:
            return float(r["SPX Spot"])
        sc = str(r["Short Call"])
        m = re.search(r"C(\d+(?:\.\d+)?)$", sc)
        return float(m.group(1)) if m else None

    def _spx_settle(notes):
        if pd.isna(notes):
            return None
        m = re.search(r"[Ss]ettled at ([\d.]+)", str(notes))
        return float(m.group(1)) if m else None

    spx_entry = df.apply(_spx_entry, axis=1)
    spx_settle = df["Notes"].apply(_spx_settle)

    day_settle = (
        df.assign(_settle=spx_settle).dropna(subset=["_settle"]).groupby("Date")["_settle"].first()
    )
    day_open = (
        df.assign(_open=spx_entry)
        .dropna(subset=["_open"])
        .sort_values(["Date", "Entry Time"])
        .groupby("Date")["_open"]
        .first()
    )
    moves = pd.DataFrame({"open_proxy": day_open, "settle": day_settle}).dropna()
    moves["pct"] = (moves["settle"] / moves["open_proxy"] - 1) * 100
    return df["Date"].map(moves["pct"])


# --- Bin labels --------------------------------------------------------------

def iv_bin(iv: float | None) -> str | None:
    if iv is None or pd.isna(iv):
        return None
    if iv < 0.20:
        return "Very Low (<0.20)"
    if iv < 0.35:
        return "Low (0.20-0.35)"
    if iv < 0.50:
        return "Mid (0.35-0.50)"
    return "High (>=0.50)"


def move_bin(p: float | None) -> str | None:
    if p is None or pd.isna(p):
        return None
    a = abs(p)
    if a < 0.25:
        return "<0.25%"
    if a < 0.5:
        return "0.25-0.5%"
    if a < 1.0:
        return "0.5-1.0%"
    if a < 2.0:
        return "1.0-2.0%"
    return ">2.0%"


def exit_window_bin(mins: float | None) -> str | None:
    if mins is None or pd.isna(mins):
        return None
    if mins < 30:
        return "0-30m"
    if mins < 60:
        return "30-60m"
    if mins < 120:
        return "1-2h"
    if mins < 180:
        return "2-3h"
    if mins < 240:
        return "3-4h"
    if mins < 360:
        return "4-6h"
    return "Held to settle"


# --- Stat helpers ------------------------------------------------------------

def streaks(pl: np.ndarray) -> tuple[list[int], list[int]]:
    """Return (win_streaks, loss_streaks) — lengths of consecutive runs."""
    wins, losses = [], []
    cw = cl = 0
    for v in pl:
        if v > 0:
            cw += 1
            if cl > 0:
                losses.append(cl)
                cl = 0
        else:
            cl += 1
            if cw > 0:
                wins.append(cw)
                cw = 0
    if cw > 0:
        wins.append(cw)
    if cl > 0:
        losses.append(cl)
    return wins, losses


def drawdown_episodes(pl: np.ndarray) -> list[tuple[float, int]]:
    """Return list of (min_drawdown_value, length_in_trades) for each DD episode."""
    cum = np.cumsum(pl)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    episodes: list[tuple[float, int]] = []
    in_dd = False
    cur_min = 0.0
    cur_len = 0
    for d in dd:
        if d < 0:
            if not in_dd:
                in_dd = True
                cur_min = float(d)
                cur_len = 1
            else:
                cur_min = min(cur_min, float(d))
                cur_len += 1
        else:
            if in_dd:
                episodes.append((cur_min, cur_len))
                in_dd = False
                cur_min, cur_len = 0.0, 0
    if in_dd:
        episodes.append((cur_min, cur_len))
    return episodes


def classify_exit(row: pd.Series) -> str:
    """Classify a trade exit as PROFIT-TARGET, TIME-STOP, or SETTLED."""
    notes = str(row["Notes"]) if pd.notna(row["Notes"]) else ""
    status = str(row["Status"])
    if "Time Exit" in notes:
        return "TIME-STOP"
    if status == "EXPIRED" or "Settled at" in notes:
        return "SETTLED"
    return "PROFIT-TARGET"


def hold_minutes(row: pd.Series) -> int | None:
    """Trade hold time in minutes from entry to exit (None if not exited yet)."""
    if pd.isna(row.get("Exit Time")) or row.get("Exit Time") == "":
        return None
    try:
        eh, em, _ = row["Entry Time"].split(":")
        xh, xm, _ = row["Exit Time"].split(":")
        return (int(xh) * 60 + int(xm)) - (int(eh) * 60 + int(em))
    except Exception:
        return None
