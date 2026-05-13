#!/usr/bin/env python3
"""
strategy_metrics.py
===================

Deep performance metrics for a single (strategy, entry-bucket) combination.

This is the script behind the Performance page on the public site, but you
can run it for any strategy or any bucket you want — including private ones —
without touching the public site.

Outputs to the terminal:
    - Trade count, win rate, total/avg P/L, std dev, expectancy
    - Avg winner/loser, win-loss size ratio, profit factor
    - Avg/max winning and losing streaks
    - Max drawdown, recovery length, Calmar ratio
    - Sharpe, Sortino (per-trade), skewness, excess kurtosis
    - Drawdown episode distribution
    - IV regime breakdown
    - SPX day-move breakdown
    - Time-of-exit clustering
    - Sequential autocorrelation (lag-1, after-win vs after-loss)
    - Avg hold time, % held to expiry

Usage
-----
    python3 analysis/strategy_metrics.py "Iron Fly V1" --bucket 30
    python3 analysis/strategy_metrics.py "Dynamic 0DTE" --bucket 30
    python3 analysis/strategy_metrics.py "Iron Fly V3" --bucket 60

    # Include private strategies (off by default)
    python3 analysis/strategy_metrics.py "Premium Popper" --bucket 30 --include-private

    # Keep outliers (off by default — outliers are filtered)
    python3 analysis/strategy_metrics.py "Iron Fly V1" --bucket 30 --keep-outliers
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def fmt_money(x: float, sign: bool = True, width: int = 8) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if sign:
        return f"${x:>+{width}.2f}"
    return f"${x:>{width}.2f}"


def report(g: pd.DataFrame, label: str):
    g = g.sort_values(["Date", "Entry Time"]).reset_index(drop=True)
    g = g.copy()
    g["DayMovePct"] = common.derive_day_move_pct(g)
    pl = g["Exit P/L"].values.astype(float)
    n = len(g)

    if n == 0:
        print(f"\n{label}: no trades match. Nothing to report.")
        return

    wins_arr = pl[pl > 0]
    losses_arr = pl[pl <= 0]
    wstreaks, lstreaks = common.streaks(pl)

    win_rate = len(wins_arr) / n
    avg_win = float(wins_arr.mean()) if len(wins_arr) else 0
    avg_loss = float(losses_arr.mean()) if len(losses_arr) else 0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    gp = float(wins_arr.sum())
    gl = float(abs(losses_arr.sum()))
    pf = gp / gl if gl > 0 else float("inf")

    std = float(pl.std(ddof=1)) if n > 1 else 0
    sharpe = float(pl.mean() / std) if std > 0 else 0
    downside = pl[pl < 0]
    dstd = float(np.sqrt(np.mean(downside ** 2))) if len(downside) else 0
    sortino = float(pl.mean() / dstd) if dstd > 0 else 0

    cum = np.cumsum(pl)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(dd.min()) if len(dd) else 0
    calmar = float(cum[-1] / abs(max_dd)) if max_dd < 0 else float("inf")

    if max_dd < 0:
        i_low = int(np.argmin(dd))
        i_peak = int(np.argmax(cum[:i_low + 1])) if i_low > 0 else 0
        peak_val = peak[i_low]
        i_rec = next((i for i in range(i_low + 1, len(cum)) if cum[i] >= peak_val), None)
        dd_to_bot = i_low - i_peak
        dd_to_rec = (i_rec - i_low) if i_rec else None
    else:
        dd_to_bot = 0
        dd_to_rec = 0

    skew = (
        float(((pl - pl.mean()) ** 3).mean() / (std ** 3))
        if std > 0 and n > 3 else 0
    )
    kurt = (
        float(((pl - pl.mean()) ** 4).mean() / (std ** 4) - 3)
        if std > 0 and n > 3 else 0
    )

    width = 80
    print("=" * width)
    print(f"  {label}    ({n} trades, {g['Date'].min()} → {g['Date'].max()})")
    print("=" * width)
    print(f"  Win rate                     {win_rate*100:>9.1f}%   ({len(wins_arr)}W / {len(losses_arr)}L)")
    print(f"  Total P/L                    {fmt_money(float(cum[-1]))}")
    print(f"  Avg P/L per trade            {fmt_money(float(pl.mean()))}")
    print(f"  Std dev of P/L               {fmt_money(std, sign=False)}")
    print(f"  Expectancy                   {fmt_money(expectancy)}")
    print()
    print(f"  Avg winner                   {fmt_money(avg_win)}")
    print(f"  Avg loser                    {fmt_money(avg_loss)}")
    wl = abs(avg_win / avg_loss) if avg_loss < 0 else float("inf")
    print(f"  Avg-win ÷ avg-loss            {wl:>9.2f}")
    print(f"  Profit factor                 {pf:>9.2f}")
    print()
    print(f"  Avg winning streak            {(np.mean(wstreaks) if wstreaks else 0):>9.2f} trades")
    print(f"  Avg losing streak             {(np.mean(lstreaks) if lstreaks else 0):>9.2f} trades")
    print(f"  Longest winning streak        {(max(wstreaks) if wstreaks else 0):>9d} trades")
    print(f"  Longest losing streak         {(max(lstreaks) if lstreaks else 0):>9d} trades")
    print()
    print(f"  Max drawdown                 {fmt_money(max_dd)}")
    print(f"  DD trades to bottom           {dd_to_bot:>9d}")
    rec_str = str(dd_to_rec) if dd_to_rec is not None else "never"
    print(f"  DD trades to recover          {rec_str:>9}")
    print(f"  Calmar ratio                  {calmar:>9.2f}")
    print()
    print(f"  Sharpe (per-trade)            {sharpe:>9.2f}")
    print(f"  Sortino (per-trade)           {sortino:>9.2f}")
    print(f"  Skewness                      {skew:>9.2f}")
    print(f"  Excess kurtosis               {kurt:>9.2f}")
    print()

    # Drawdown distribution
    eps = common.drawdown_episodes(pl)
    if eps:
        dd_mins = sorted([e[0] for e in eps])
        dd_lens = sorted([e[1] for e in eps])
        print(f"  Drawdown episodes:            {len(eps)}")
        print(f"    Median DD:                 {fmt_money(float(np.median(dd_mins)))}")
        print(f"    90th-pctile DD:            {fmt_money(float(np.percentile(dd_mins, 10)))}")
        print(f"    Worst DD:                  {fmt_money(min(dd_mins))}")
        print(f"    Median length:             {int(np.median(dd_lens))} trades")
        print(f"    DDs ≥ $5 / ≥ $10:           {sum(1 for m in dd_mins if m <= -5)} / "
              f"{sum(1 for m in dd_mins if m <= -10)}")
        print()

    # IV regime
    g["IVBin"] = g["IV Rank"].apply(common.iv_bin)
    iv_present = g["IVBin"].notna().any()
    if iv_present:
        print("  IV regime breakdown:")
        for ivb in ["Very Low (<0.20)", "Low (0.20-0.35)", "Mid (0.35-0.50)", "High (>=0.50)"]:
            sub = g[g["IVBin"] == ivb]
            if len(sub):
                print(f"    {ivb:<22}  n={len(sub):>3}  WR={(sub['Exit P/L']>0).mean()*100:>5.1f}%  "
                      f"avg={fmt_money(float(sub['Exit P/L'].mean()))}  "
                      f"total={fmt_money(float(sub['Exit P/L'].sum()))}")
        print()

    # SPX day-move breakdown
    g["MoveBin"] = g["DayMovePct"].apply(common.move_bin)
    if g["MoveBin"].notna().any():
        print("  SPX day-move breakdown:")
        for mb in ["<0.25%", "0.25-0.5%", "0.5-1.0%", "1.0-2.0%", ">2.0%"]:
            sub = g[g["MoveBin"] == mb]
            if len(sub):
                print(f"    {mb:<14}  n={len(sub):>3}  WR={(sub['Exit P/L']>0).mean()*100:>5.1f}%  "
                      f"avg={fmt_money(float(sub['Exit P/L'].mean()))}  "
                      f"total={fmt_money(float(sub['Exit P/L'].sum()))}")
        print()

    # Time-of-exit clustering
    g["ExitBin"] = g["ExitMAO"].apply(common.exit_window_bin)
    if g["ExitBin"].notna().any():
        print("  Time-of-exit clustering:")
        for eb in ["0-30m", "30-60m", "1-2h", "2-3h", "3-4h", "4-6h", "Held to settle"]:
            sub = g[g["ExitBin"] == eb]
            if len(sub):
                wn = int((sub["Exit P/L"] > 0).sum())
                ln = int((sub["Exit P/L"] <= 0).sum())
                wa = float(sub.loc[sub['Exit P/L'] > 0, 'Exit P/L'].mean()) if wn else 0
                la = float(sub.loc[sub['Exit P/L'] <= 0, 'Exit P/L'].mean()) if ln else 0
                print(f"    {eb:<16}  W/L={wn:>2}/{ln:<2}  "
                      f"winAvg={fmt_money(wa)}  lossAvg={fmt_money(la)}")
        print()

    # Autocorrelation
    if n > 2:
        lag1 = float(np.corrcoef(pl[:-1], pl[1:])[0, 1])
        waw = sum(1 for i in range(1, n) if pl[i] > 0 and pl[i-1] > 0) / max(
            sum(1 for i in range(1, n) if pl[i-1] > 0), 1) * 100
        wal = sum(1 for i in range(1, n) if pl[i] > 0 and pl[i-1] <= 0) / max(
            sum(1 for i in range(1, n) if pl[i-1] <= 0), 1) * 100
        print(f"  Sequential autocorrelation:")
        print(f"    Trade-level lag-1 corr     {lag1:>+9.3f}")
        print(f"    Win % after a winner       {waw:>9.1f}%")
        print(f"    Win % after a loser        {wal:>9.1f}%")

    # Hold time
    g["HoldMin"] = g.apply(common.hold_minutes, axis=1)
    holds = g["HoldMin"].dropna().values
    if len(holds):
        print(f"\n  Avg hold time                {np.mean(holds):>9.1f} min")
        print(f"  Median hold time             {np.median(holds):>9.1f} min")

    pct_exp = (g["Status"] == "EXPIRED").mean() * 100
    print(f"  % held to settle             {pct_exp:>9.1f}%")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("strategy", help="Strategy name (e.g. 'Iron Fly V1', 'Dynamic 0DTE')")
    ap.add_argument("--bucket", type=int, default=None,
                    help="Entry bucket in minutes after open (e.g. 30, 60). "
                         "If omitted, all buckets for the strategy are pooled.")
    ap.add_argument("--csv", default=str(common.CSV_PATH))
    ap.add_argument("--include-private", action="store_true",
                    help="Allow private/custom strategies (off by default)")
    ap.add_argument("--keep-outliers", action="store_true",
                    help="Don't filter anomalous-credit outliers")
    args = ap.parse_args()

    df = common.load_trades(
        args.csv,
        drop_private=not args.include_private,
        drop_outliers=not args.keep_outliers,
    )

    if args.strategy not in df["Strategy"].unique():
        print(f"Strategy '{args.strategy}' not found.")
        print(f"Available: {sorted(df['Strategy'].unique())}")
        sys.exit(1)

    sub = df[df["Strategy"] == args.strategy]
    if args.bucket is not None:
        sub = sub[sub["Bucket5"] == args.bucket]
        label = f"{args.strategy} +{args.bucket}m"
    else:
        label = f"{args.strategy} (all buckets)"

    report(sub, label)


if __name__ == "__main__":
    main()
