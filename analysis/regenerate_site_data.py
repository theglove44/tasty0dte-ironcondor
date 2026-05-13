#!/usr/bin/env python3
"""
regenerate_site_data.py
=======================

Regenerate public_site/data.js from paper_trades.csv.

This is the script that drives every number on the public research site at
public_site/. Run it any time paper_trades.csv changes (new trades, closed
positions, manual edits, dedup, etc.).

Usage
-----
    python3 analysis/regenerate_site_data.py
    python3 analysis/regenerate_site_data.py --csv /path/to/trades.csv
    python3 analysis/regenerate_site_data.py --out /path/to/data.js

What it writes
--------------
A single JS file at public_site/data.js with a `window.SITE_DATA` object
containing:
    - meta (date range, totals, outliers removed count)
    - overall stats
    - per-strategy stats and per-bucket breakdown
    - monthly P/L grids
    - daily equity curve
    - deep metrics (streaks, drawdowns, IV regime, exits, autocorrelation)
      for the top five profitable strategies
    - day-of-week × month grid for Iron Fly V1 and Dynamic 0DTE

Filters applied
---------------
    - Closed/expired trades only (drops OPEN positions)
    - Private strategies excluded (Premium Popper, ORB-STACK-*, JadeLizard_*)
    - Anomalous-credit outliers excluded (Credit Collected > $30)

Top-5 strategy buckets analysed for deep metrics:
    Iron Fly V1 +30m, V2 +30m, V3 +60m, V4 +60m, Dynamic 0DTE +30m
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


# Top 5 (strategy, bucket_minutes_after_open, display_label) — the profitable set.
TOP_STRATEGIES = [
    ("Iron Fly V1", 30, "Iron Fly V1 +30m"),
    ("Iron Fly V2", 30, "Iron Fly V2 +30m"),
    ("Iron Fly V3", 60, "Iron Fly V3 +60m"),
    ("Iron Fly V4", 60, "Iron Fly V4 +60m"),
    ("Dynamic 0DTE", 30, "Dynamic 0DTE +30m"),
]

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def basic_stats(g: pd.DataFrame) -> dict | None:
    n = len(g)
    if n == 0:
        return None
    wins = int((g["Exit P/L"] > 0).sum())
    losses = int((g["Exit P/L"] <= 0).sum())
    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "winPct": round(wins / n * 100, 1),
        "expired": int((g["Status"] == "EXPIRED").sum()),
        "totalPL": round(float(g["Exit P/L"].sum()), 2),
        "avgPL": round(float(g["Exit P/L"].mean()), 2),
        "avgCredit": round(float(g["Credit Collected"].mean()), 2),
        "avgBP": round(
            float(g["Buying Power"].mean()) if g["Buying Power"].notna().any() else 0, 2
        ),
        "avgWinner": round(float(g.loc[g["Exit P/L"] > 0, "Exit P/L"].mean()), 2) if wins else 0,
        "avgLoser": round(float(g.loc[g["Exit P/L"] <= 0, "Exit P/L"].mean()), 2) if losses else 0,
        "best": round(float(g["Exit P/L"].max()), 2),
        "worst": round(float(g["Exit P/L"].min()), 2),
        "roi": 0,
    }


def deep_metrics(g: pd.DataFrame) -> dict:
    g = g.sort_values(["Date", "Entry Time"]).reset_index(drop=True)
    pl = g["Exit P/L"].values.astype(float)
    n = len(g)

    wins_arr = pl[pl > 0]
    losses_arr = pl[pl <= 0]
    wstreaks, lstreaks = common.streaks(pl)

    win_rate = len(wins_arr) / n
    avg_win = float(wins_arr.mean()) if len(wins_arr) else 0
    avg_loss = float(losses_arr.mean()) if len(losses_arr) else 0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    gp = float(wins_arr.sum())
    gl = float(abs(losses_arr.sum()))
    pf = gp / gl if gl > 0 else None

    std = float(pl.std(ddof=1)) if n > 1 else 0
    sharpe = float(pl.mean() / std) if std > 0 else 0
    downside = pl[pl < 0]
    dstd = float(np.sqrt(np.mean(downside ** 2))) if len(downside) else 0
    sortino = float(pl.mean() / dstd) if dstd > 0 else 0

    cum = np.cumsum(pl)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(dd.min()) if len(dd) else 0
    calmar = float(cum[-1] / abs(max_dd)) if max_dd < 0 else None

    if max_dd < 0:
        i_low = int(np.argmin(dd))
        i_peak = int(np.argmax(cum[:i_low + 1])) if i_low > 0 else 0
        peak_val = peak[i_low]
        i_rec = next((i for i in range(i_low + 1, len(cum)) if cum[i] >= peak_val), None)
        dd_to_bot = i_low - i_peak
        dd_to_rec = (i_rec - i_low) if i_rec else None
    else:
        dd_to_bot, dd_to_rec = 0, 0

    skew = (
        float(((pl - pl.mean()) ** 3).mean() / (std ** 3))
        if std > 0 and n > 3
        else 0
    )
    kurt = (
        float(((pl - pl.mean()) ** 4).mean() / (std ** 4) - 3)
        if std > 0 and n > 3
        else 0
    )

    eps = common.drawdown_episodes(pl)
    dd_mins = sorted([e[0] for e in eps]) if eps else []
    dd_lens = sorted([e[1] for e in eps]) if eps else []
    dd_summary = {
        "episodes": len(eps),
        "medianDD": round(float(np.median(dd_mins)), 2) if dd_mins else 0,
        "p90DD": round(float(np.percentile(dd_mins, 10)), 2) if dd_mins else 0,
        "worstDD": round(float(min(dd_mins)), 2) if dd_mins else 0,
        "medianLen": int(np.median(dd_lens)) if dd_lens else 0,
        "p90Len": int(np.percentile(dd_lens, 90)) if dd_lens else 0,
        "overFive": sum(1 for m in dd_mins if m <= -5),
        "overTen": sum(1 for m in dd_mins if m <= -10),
    }

    g["IVBin"] = g["IV Rank"].apply(common.iv_bin)
    iv_breakdown = {}
    for ivb in ["Very Low (<0.20)", "Low (0.20-0.35)", "Mid (0.35-0.50)", "High (>=0.50)"]:
        sub = g[g["IVBin"] == ivb]
        if len(sub) > 0:
            iv_breakdown[ivb] = {
                "n": len(sub),
                "winPct": round((sub["Exit P/L"] > 0).mean() * 100, 1),
                "avgPL": round(float(sub["Exit P/L"].mean()), 2),
                "totalPL": round(float(sub["Exit P/L"].sum()), 2),
            }

    g["MoveBin"] = g["DayMovePct"].apply(common.move_bin)
    move_breakdown = {}
    for mb in ["<0.25%", "0.25-0.5%", "0.5-1.0%", "1.0-2.0%", ">2.0%"]:
        sub = g[g["MoveBin"] == mb]
        if len(sub) > 0:
            move_breakdown[mb] = {
                "n": len(sub),
                "winPct": round((sub["Exit P/L"] > 0).mean() * 100, 1),
                "avgPL": round(float(sub["Exit P/L"].mean()), 2),
                "totalPL": round(float(sub["Exit P/L"].sum()), 2),
            }

    g["ExitBin"] = g["ExitMAO"].apply(common.exit_window_bin)
    exit_breakdown = {}
    for eb in ["0-30m", "30-60m", "1-2h", "2-3h", "3-4h", "4-6h", "Held to settle"]:
        sub = g[g["ExitBin"] == eb]
        if len(sub) > 0:
            wn = int((sub["Exit P/L"] > 0).sum())
            ln = int((sub["Exit P/L"] <= 0).sum())
            wa = round(float(sub.loc[sub["Exit P/L"] > 0, "Exit P/L"].mean()), 2) if wn else 0
            la = round(float(sub.loc[sub["Exit P/L"] <= 0, "Exit P/L"].mean()), 2) if ln else 0
            exit_breakdown[eb] = {"wins": wn, "losses": ln, "winsAvg": wa, "lossesAvg": la}

    if n > 2:
        lag1 = float(np.corrcoef(pl[:-1], pl[1:])[0, 1])
        waw = sum(1 for i in range(1, n) if pl[i] > 0 and pl[i - 1] > 0) / max(
            sum(1 for i in range(1, n) if pl[i - 1] > 0), 1
        ) * 100
        wal = sum(1 for i in range(1, n) if pl[i] > 0 and pl[i - 1] <= 0) / max(
            sum(1 for i in range(1, n) if pl[i - 1] <= 0), 1
        ) * 100
    else:
        lag1, waw, wal = 0, 0, 0

    return {
        "trades": n,
        "winRate": round(win_rate * 100, 1),
        "totalPL": round(float(cum[-1]), 2),
        "avgPL": round(float(pl.mean()), 2),
        "stdDev": round(std, 2),
        "expectancy": round(expectancy, 2),
        "avgWin": round(avg_win, 2),
        "avgLoss": round(avg_loss, 2),
        "profitFactor": round(pf, 2) if pf else None,
        "maxDD": round(max_dd, 2),
        "ddToBottom": dd_to_bot,
        "ddToRecover": dd_to_rec,
        "calmar": round(calmar, 2) if calmar else None,
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "skewness": round(skew, 2),
        "kurtosis": round(kurt, 2),
        "avgWinStreak": round(float(np.mean(wstreaks)), 2) if wstreaks else 0,
        "avgLossStreak": round(float(np.mean(lstreaks)), 2) if lstreaks else 0,
        "maxWinStreak": max(wstreaks) if wstreaks else 0,
        "maxLossStreak": max(lstreaks) if lstreaks else 0,
        "numWinStreaks": len(wstreaks),
        "numLossStreaks": len(lstreaks),
        "best": round(float(pl.max()), 2),
        "worst": round(float(pl.min()), 2),
        "drawdowns": dd_summary,
        "ivRegime": iv_breakdown,
        "moveBuckets": move_breakdown,
        "exitClusters": exit_breakdown,
        "lag1Corr": round(lag1, 3),
        "winAfterWin": round(waw, 1),
        "winAfterLoss": round(wal, 1),
    }


def build_data(df: pd.DataFrame, outliers_removed: int) -> dict:
    df = df.copy()
    df["DayMovePct"] = common.derive_day_move_pct(df)

    data: dict = {
        "meta": {
            "firstDate": str(df["Date"].min()),
            "lastDate": str(df["Date"].max()),
            "totalDays": int(pd.to_datetime(df["Date"]).nunique()),
            "totalTrades": int(len(df)),
            "outliersRemoved": outliers_removed,
        },
        "overall": basic_stats(df),
        "strategies": {},
        "buckets": {},
        "monthly": {},
        "dayOfWeek": {},
        "bestPicks": {},
    }

    for s in sorted(df["Strategy"].unique()):
        sub = df[df["Strategy"] == s]
        data["strategies"][s] = basic_stats(sub)
        data["buckets"][s] = {}
        for b in sorted(sub["Bucket5"].unique()):
            bsub = sub[sub["Bucket5"] == b]
            st = basic_stats(bsub)
            st["bucket"] = common.bucket_label(int(b))
            st["minsAfterOpen"] = int(b)
            data["buckets"][s][common.bucket_label(int(b))] = st
        data["monthly"][s] = {
            m: round(float(sub[sub["Month"] == m]["Exit P/L"].sum()), 2)
            for m in sorted(sub["Month"].unique())
        }

    for s in ("Iron Fly V1", "Dynamic 0DTE"):
        sub = df[(df["Strategy"] == s) & (df["Bucket5"] == 30)]
        data["dayOfWeek"][s] = {
            d: basic_stats(sub[sub["DOW"] == d]) for d in DOW_ORDER if len(sub[sub["DOW"] == d])
        }
        data["dayOfWeek"][s + " (no outliers)"] = data["dayOfWeek"][s]

    data["monthsAll"] = sorted(df["Month"].unique())

    daily = df.groupby("Date")["Exit P/L"].sum().sort_values()
    data["worstDays"] = [
        {"date": str(d), "pl": round(float(p), 2)} for d, p in daily.head(5).items()
    ]
    data["bestDays"] = [
        {"date": str(d), "pl": round(float(p), 2)} for d, p in daily.tail(5).iloc[::-1].items()
    ]

    daily_full = df.groupby("Date")["Exit P/L"].sum().sort_index()
    cum = daily_full.cumsum()
    data["equityCurve"] = [
        {"date": str(d), "daily": round(float(p), 2), "cum": round(float(c), 2)}
        for d, p, c in zip(cum.index, daily_full.values, cum.values)
    ]
    data["strategyOrder"] = list(
        df.groupby("Strategy")["Exit P/L"].sum().sort_values(ascending=False).index
    )

    deep = {}
    for strategy, bucket, label in TOP_STRATEGIES:
        g = df[(df["Strategy"] == strategy) & (df["Bucket5"] == bucket)]
        if len(g) == 0:
            continue
        deep[label] = deep_metrics(g)
    data["deep"] = deep

    dow_month = {}
    for strategy, bucket, label in [
        ("Iron Fly V1", 30, "Iron Fly V1 +30m"),
        ("Dynamic 0DTE", 30, "Dynamic 0DTE +30m"),
    ]:
        g = df[(df["Strategy"] == strategy) & (df["Bucket5"] == bucket)]
        months = sorted(g["Month"].unique())
        grid = {}
        for d in DOW_ORDER:
            grid[d] = {}
            total_pl = 0.0
            total_n = 0
            for m in months:
                cell = g[(g["DOW"] == d) & (g["Month"] == m)]
                if len(cell) > 0:
                    pl_v = round(float(cell["Exit P/L"].sum()), 2)
                    grid[d][m] = {"pl": pl_v, "n": len(cell)}
                    total_pl += pl_v
                    total_n += len(cell)
                else:
                    grid[d][m] = None
            grid[d]["Total"] = {"pl": round(total_pl, 2), "n": total_n}
        dow_month[label] = {"months": months, "grid": grid}
    data["dowMonth"] = dow_month

    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", default=str(common.CSV_PATH), help="Path to paper_trades.csv")
    ap.add_argument("--out", default=str(common.DATA_JS_PATH), help="Path to write data.js")
    ap.add_argument("--quiet", action="store_true", help="Suppress summary output")
    args = ap.parse_args()

    # Count outliers removed (transparently reportable).
    raw = pd.read_csv(args.csv)
    raw["Credit Collected"] = pd.to_numeric(raw["Credit Collected"], errors="coerce")
    raw = raw[~raw["Strategy"].apply(common.is_private_strategy)]
    raw = raw[raw["Status"].isin(["CLOSED", "EXPIRED"])]
    raw = raw.dropna(subset=["Exit P/L"])
    outliers_removed = int((raw["Credit Collected"] > common.OUTLIER_CREDIT_THRESHOLD).sum())

    df = common.load_trades(args.csv)
    data = build_data(df, outliers_removed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("// Auto-generated trading analysis data — public, anonymised\n")
        f.write("// Outlier filter: trades with Credit Collected > $30 excluded\n")
        f.write("window.SITE_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";\n")

    if not args.quiet:
        print(f"Wrote {out_path}  ({out_path.stat().st_size:,} bytes)")
        o = data["overall"]
        print(f"  Trades:    {o['trades']}  ({outliers_removed} outliers filtered)")
        print(f"  Win rate:  {o['winPct']}%")
        print(f"  Total P/L: ${o['totalPL']:+.2f}")
        print(f"  Avg P/L:   ${o['avgPL']:+.2f}")
        print(f"  Date range: {data['meta']['firstDate']} → {data['meta']['lastDate']}")


if __name__ == "__main__":
    main()
