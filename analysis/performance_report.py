"""
performance_report.py — Cross-strategy & entry-window performance report.

Answers the two recurring questions from one place, using the shared filters
and DST-normalised timing in common.py (no re-implemented logic):

  1. Which strategy performs best?
     Ranked by EXPECTANCY (avg P/L per trade) and RETURN-ON-CAPITAL
     (avg P/L / median buying power) -- NOT raw total P/L, which is confounded
     by trade count, strategy lifespan, and wildly different margin (Iron Flies
     reserve ~$120 vs ~$1,500 for ICs / Dynamic / Jade Lizard).

  2. Which entry time window performs best?
     DST-normalised minutes-after-open buckets, PLUS a controlled Iron Fly
     "natural experiment" that isolates entry timing while holding the
     structure and profit target constant (V1 vs V3 @10% PT; V2 vs V4 @20% PT).

Entry-window analysis is scoped to the fixed-time 0DTE strategies (Iron Flies,
Dynamic, and the retired ICs). ORB Stacking (event-driven breakout entries) and
Jade Lizard (multi-day) do not have a clock-driven entry window and are excluded
from the timing section.

Usage:
  python analysis/performance_report.py                # full history, all strategies
  python analysis/performance_report.py --active-only  # only strategies still trading
  python analysis/performance_report.py --since 2026-04-01
  python analysis/performance_report.py --public-only  # exclude private strategies
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 40)

# Strategies whose entries are driven by a fixed clock time (so a "window" is
# meaningful). ORB Stacking is breakout-driven; Jade Lizard is multi-day.
FIXED_TIME_STRATEGIES = {
    "Iron Fly V1", "Iron Fly V2", "Iron Fly V3", "Iron Fly V4",
    "Dynamic 0DTE", "20 Delta", "30 Delta", "Gap Filter 20D",
}

# "Active" = traded within this many days of the most recent trade in the data.
ACTIVE_WINDOW_DAYS = 14


def _payoff(group: pd.DataFrame) -> float:
    wins = group.loc[group["Exit P/L"] > 0, "Exit P/L"]
    losses = group.loc[group["Exit P/L"] <= 0, "Exit P/L"]
    if len(losses) == 0 or losses.mean() == 0:
        return float("inf")
    return wins.mean() / abs(losses.mean()) if len(wins) else 0.0


def _profit_factor(group: pd.DataFrame) -> float:
    gross_win = group.loc[group["Exit P/L"] > 0, "Exit P/L"].sum()
    gross_loss = abs(group.loc[group["Exit P/L"] <= 0, "Exit P/L"].sum())
    if gross_loss == 0:
        return float("inf")
    return gross_win / gross_loss


def _tstat(pl: np.ndarray) -> float:
    """t-statistic for mean(P/L) != 0. |t| > ~2 ~ 95% confident the edge is real."""
    if len(pl) < 2 or pl.std(ddof=1) == 0:
        return float("nan")
    return pl.mean() / (pl.std(ddof=1) / np.sqrt(len(pl)))


def strategy_leaderboard(df: pd.DataFrame, max_date: date) -> pd.DataFrame:
    rows = []
    for strat, g in df.groupby("Strategy"):
        pl = g["Exit P/L"].to_numpy()
        med_bp = g["Buying Power"].median()
        avg = pl.mean()
        last = g["Date"].max()
        rows.append({
            "Strategy": strat,
            "n": len(g),
            "WR%": (pl > 0).mean() * 100,
            "Total": pl.sum(),
            "Avg/trade": avg,
            "AvgWin": g.loc[g["Exit P/L"] > 0, "Exit P/L"].mean(),
            "AvgLoss": g.loc[g["Exit P/L"] <= 0, "Exit P/L"].mean(),
            "Payoff": _payoff(g),
            "PF": _profit_factor(g),
            "MedBP": med_bp,
            "ROC%/trade": (avg / med_bp * 100) if med_bp and med_bp > 0 else float("nan"),
            "t": _tstat(pl),
            "Last": last,
            "Active": (max_date - last).days <= ACTIVE_WINDOW_DAYS,
            "Private": common.is_private_strategy(strat),
        })
    out = pd.DataFrame(rows).sort_values("Avg/trade", ascending=False)
    return out


def _fmt_leaderboard(df: pd.DataFrame) -> str:
    return df.to_string(index=False, formatters={
        "WR%": "{:.1f}".format,
        "Total": "${:,.2f}".format,
        "Avg/trade": "${:.2f}".format,
        "AvgWin": "${:.2f}".format,
        "AvgLoss": "${:.2f}".format,
        "Payoff": "{:.2f}".format,
        "PF": "{:.2f}".format,
        "MedBP": "${:,.0f}".format,
        "ROC%/trade": "{:.2f}%".format,
        "t": "{:.2f}".format,
    })


def pooled_windows(df: pd.DataFrame) -> pd.DataFrame:
    ft = df[df["Strategy"].isin(FIXED_TIME_STRATEGIES)].copy()
    rows = []
    for b, g in ft.groupby("Bucket5"):
        pl = g["Exit P/L"].to_numpy()
        rows.append({
            "Window": common.bucket_label(b),
            "MAO": b,
            "n": len(g),
            "WR%": (pl > 0).mean() * 100,
            "Total": pl.sum(),
            "Avg/trade": pl.mean(),
            "t": _tstat(pl),
        })
    return pd.DataFrame(rows).sort_values("MAO")


def natural_experiment(df: pd.DataFrame) -> str:
    """Isolate entry timing: same structure & PT, only the entry window differs."""
    lines = []
    pairs = [
        ("Iron Fly V1 (+30m, 10% PT)", "Iron Fly V3 (+1h, 10% PT)", "Iron Fly V1", "Iron Fly V3"),
        ("Iron Fly V2 (+30m, 20% PT)", "Iron Fly V4 (+1h, 20% PT)", "Iron Fly V2", "Iron Fly V4"),
    ]
    for la, lb, a, b in pairs:
        ga = df[df["Strategy"] == a]["Exit P/L"].to_numpy()
        gb = df[df["Strategy"] == b]["Exit P/L"].to_numpy()
        if len(ga) == 0 or len(gb) == 0:
            continue
        # Welch's two-sample t (unequal variance)
        sa, sb = ga.std(ddof=1), gb.std(ddof=1)
        se = np.sqrt(sa**2 / len(ga) + sb**2 / len(gb))
        tw = (ga.mean() - gb.mean()) / se if se else float("nan")
        lines.append(f"  {la:<30} n={len(ga):>3}  avg=${ga.mean():+.2f}  WR={ (ga>0).mean()*100:4.1f}%  total=${ga.sum():+.2f}")
        lines.append(f"  {lb:<30} n={len(gb):>3}  avg=${gb.mean():+.2f}  WR={ (gb>0).mean()*100:4.1f}%  total=${gb.sum():+.2f}")
        winner = "+30m" if ga.mean() > gb.mean() else "+1h"
        lines.append(f"    -> +30m minus +1h edge = ${ga.mean()-gb.mean():+.2f}/trade   Welch t={tw:+.2f}   favours {winner}")
        lines.append("")
    return "\n".join(lines)


def monthly_active(df: pd.DataFrame, max_date: date) -> str:
    active = sorted({s for s, g in df.groupby("Strategy")
                     if (max_date - g["Date"].max()).days <= ACTIVE_WINDOW_DAYS})
    sub = df[df["Strategy"].isin(active)].copy()
    piv = sub.pivot_table(index="Month", columns="Strategy", values="Exit P/L",
                          aggfunc="sum", margins=True, margins_name="TOTAL")
    return piv.to_string(float_format=lambda x: f"{x:+.1f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--active-only", action="store_true", help="only strategies still trading")
    ap.add_argument("--public-only", action="store_true", help="exclude private strategies")
    ap.add_argument("--since", type=str, default=None, help="only trades on/after YYYY-MM-DD")
    args = ap.parse_args()

    df = common.load_trades(drop_private=args.public_only, drop_outliers=True)
    max_date = df["Date"].max()

    if args.since:
        since = pd.to_datetime(args.since).date()
        df = df[df["Date"] >= since].copy()

    lb = strategy_leaderboard(df, max_date)
    if args.active_only:
        lb = lb[lb["Active"]]

    print("=" * 110)
    print(f"PERFORMANCE REPORT  |  {df['Date'].min()} -> {df['Date'].max()}  |  "
          f"{len(df)} closed trades  |  grand total ${df['Exit P/L'].sum():+,.2f}")
    print("=" * 110)
    print("\n### STRATEGY LEADERBOARD (sorted by expectancy = avg P/L per trade)")
    print("Payoff = avgWin/|avgLoss|;  PF = grossWin/grossLoss;  ROC%/trade = avg P/L / median buying power;")
    print("t = single-sample t-stat for avg!=0 (|t|>2 ~ 95% confident).  Active = traded within "
          f"{ACTIVE_WINDOW_DAYS}d of {max_date}.\n")
    print(_fmt_leaderboard(lb))

    print("\n" + "=" * 110)
    print("### ENTRY-WINDOW ANALYSIS  (fixed-time 0DTE strategies only; ORB/JadeLizard excluded)")
    print("=" * 110)
    print("\nPooled across fixed-time strategies (DST-normalised; confounded by strategy mix):\n")
    print(pooled_windows(df).to_string(index=False, formatters={
        "WR%": "{:.1f}".format, "Total": "${:,.2f}".format,
        "Avg/trade": "${:.2f}".format, "t": "{:.2f}".format,
    }))
    print("\nControlled natural experiment (structure & PT fixed, only entry window differs):\n")
    print(natural_experiment(df))

    print("=" * 110)
    print("### RECENCY: monthly P/L by currently-active strategy")
    print("=" * 110 + "\n")
    print(monthly_active(df, max_date))


if __name__ == "__main__":
    main()
