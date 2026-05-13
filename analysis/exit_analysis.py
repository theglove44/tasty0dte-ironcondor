#!/usr/bin/env python3
"""
exit_analysis.py
================

Exit-reason breakdown for one or all strategies.

Categorises each trade exit as:
    - PROFIT-TARGET — closed early at a debit (typically the strategy's profit target)
    - TIME-STOP     — closed at the scheduled time exit (Notes contain 'Time Exit')
    - SETTLED       — held to expiration (Status=EXPIRED or Notes contain 'Settled at')

Reports per category:
    - Trade count, win count, total/avg P/L
    - Win-rate and avg P/L for winners and losers within the category
    - Hold time stats
    - Day-of-week and month breakdown (for the time-stop category specifically)

Usage
-----
    python3 analysis/exit_analysis.py "Iron Fly V1"
    python3 analysis/exit_analysis.py "Iron Fly V1" --bucket 30
    python3 analysis/exit_analysis.py --all     # one-line summary per strategy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def summarise_category(g: pd.DataFrame, cat: str):
    sub = g[g["Exit"] == cat]
    n = len(sub)
    if n == 0:
        print(f"  {cat:<16}  no trades")
        return
    wins = (sub["Exit P/L"] > 0).sum()
    total = sub["Exit P/L"].sum()
    avg = sub["Exit P/L"].mean()
    print(f"  {cat:<16}  n={n:>3}  W/L={wins:>2}/{n-wins:<2}  "
          f"avg=${avg:>+6.2f}  total=${total:>+7.2f}")


def deep_category_dive(g: pd.DataFrame, cat: str):
    sub = g[g["Exit"] == cat].copy()
    if len(sub) == 0:
        return
    print(f"\n--- {cat} deep dive ({len(sub)} trades) ---")
    wins = sub[sub["Exit P/L"] > 0]
    losses = sub[sub["Exit P/L"] <= 0]

    if len(wins):
        print(f"  Winners  (n={len(wins)}, WR={len(wins)/len(sub)*100:.1f}%):")
        print(f"    Avg P/L:   ${wins['Exit P/L'].mean():>+6.2f}")
        print(f"    Median:    ${wins['Exit P/L'].median():>+6.2f}")
        print(f"    Best:      ${wins['Exit P/L'].max():>+6.2f}")
        print(f"    Total:     ${wins['Exit P/L'].sum():>+6.2f}")
    if len(losses):
        print(f"  Losers   (n={len(losses)}):")
        print(f"    Avg P/L:   ${losses['Exit P/L'].mean():>+6.2f}")
        print(f"    Median:    ${losses['Exit P/L'].median():>+6.2f}")
        print(f"    Worst:     ${losses['Exit P/L'].min():>+6.2f}")
        print(f"    Total:     ${losses['Exit P/L'].sum():>+6.2f}")
    if len(wins) and len(losses):
        wl = abs(wins["Exit P/L"].mean() / losses["Exit P/L"].mean())
        print(f"  Win/loss size ratio: {wl:.2f}x")

    holds = sub.apply(common.hold_minutes, axis=1).dropna()
    if len(holds):
        print(f"  Hold time mean/median: {holds.mean():.0f} / {holds.median():.0f} min")

    if cat == "TIME-STOP":
        exit_times = sub["Exit Time"].str[:5].value_counts()
        print(f"  Time-stop exit clock distribution: {dict(exit_times.head(6))}")
        print(f"\n  By day of week:")
        for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            dsub = sub[sub["DOW"] == d]
            if len(dsub):
                w = (dsub["Exit P/L"] > 0).sum()
                print(f"    {d:<10} n={len(dsub):>2}  W/L={w}/{len(dsub)-w}  "
                      f"avg=${dsub['Exit P/L'].mean():>+6.2f}  total=${dsub['Exit P/L'].sum():>+6.2f}")
        print(f"\n  By month:")
        for m in sorted(sub["Month"].unique()):
            msub = sub[sub["Month"] == m]
            w = (msub["Exit P/L"] > 0).sum()
            print(f"    {m}  n={len(msub):>2}  W/L={w}/{len(msub)-w}  "
                  f"avg=${msub['Exit P/L'].mean():>+6.2f}  total=${msub['Exit P/L'].sum():>+6.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("strategy", nargs="?", help="Strategy name (e.g. 'Iron Fly V1')")
    ap.add_argument("--bucket", type=int, default=None)
    ap.add_argument("--all", action="store_true",
                    help="Summarise exit mix for every strategy (one line each)")
    ap.add_argument("--csv", default=str(common.CSV_PATH))
    ap.add_argument("--include-private", action="store_true")
    ap.add_argument("--keep-outliers", action="store_true")
    args = ap.parse_args()

    if not args.all and not args.strategy:
        ap.error("Provide a strategy name or pass --all")

    df = common.load_trades(
        args.csv,
        drop_private=not args.include_private,
        drop_outliers=not args.keep_outliers,
    )
    df["Exit"] = df.apply(common.classify_exit, axis=1)

    if args.all:
        print(f"\n{'Strategy':<22}  {'Total':>4}  {'PT':>4} W%   {'TS':>4} W%   {'SET':>4} W%")
        print("-" * 80)
        for s in sorted(df["Strategy"].unique()):
            g = df[df["Strategy"] == s]
            n = len(g)
            row = [f"{s:<22}", f"{n:>4}"]
            for cat in ("PROFIT-TARGET", "TIME-STOP", "SETTLED"):
                sub = g[g["Exit"] == cat]
                if len(sub):
                    wr = (sub["Exit P/L"] > 0).mean() * 100
                    row.append(f"{len(sub):>4} {wr:>3.0f}%")
                else:
                    row.append("   —     ")
            print("  ".join(row))
        return

    if args.strategy not in df["Strategy"].unique():
        print(f"Strategy '{args.strategy}' not found.")
        print(f"Available: {sorted(df['Strategy'].unique())}")
        sys.exit(1)

    g = df[df["Strategy"] == args.strategy]
    label = args.strategy
    if args.bucket is not None:
        g = g[g["Bucket5"] == args.bucket]
        label = f"{args.strategy} +{args.bucket}m"

    print(f"\n=== Exit-reason breakdown: {label} ({len(g)} trades) ===\n")
    for cat in ("PROFIT-TARGET", "TIME-STOP", "SETTLED"):
        summarise_category(g, cat)

    for cat in ("PROFIT-TARGET", "TIME-STOP", "SETTLED"):
        deep_category_dive(g, cat)


if __name__ == "__main__":
    main()
