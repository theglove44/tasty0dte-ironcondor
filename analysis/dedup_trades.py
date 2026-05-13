#!/usr/bin/env python3
"""
dedup_trades.py
===============

Find and (optionally) remove duplicate trade rows from paper_trades.csv.

Duplicates can arise from re-running the bot, Discord notifications causing
re-entries, or other accidental double-logging. This script identifies them
two ways:

    1. Exact duplicates: identical Date + Strategy + Entry Time (down to the
       second). These are unambiguous — two trades cannot fire at the same
       second.
    2. Probable duplicates: same Date + Strategy + StrategyId + identical
       strikes, with entry times less than 60 seconds apart.

Usage
-----
    python3 analysis/dedup_trades.py                # report only, no changes
    python3 analysis/dedup_trades.py --apply        # remove dups in place
    python3 analysis/dedup_trades.py --apply --no-backup   # skip backup

When --apply is set, the original CSV is backed up to
paper_trades.csv.backup_YYYYMMDD_HHMMSS unless --no-backup is given.

The earlier-timestamp row is kept; later rows in each duplicate group are
dropped. This matches the scheduler-intent semantic (only one trade per
scheduled slot).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


PROBABLE_DUP_WINDOW_SECONDS = 60


def entry_seconds(t: str) -> int:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def find_duplicates(df: pd.DataFrame) -> list[tuple[int, str, str, str, str]]:
    """Return list of (index, kind, date, time, strategy) for rows to drop.

    `kind` is 'exact' or 'probable'. The earliest row in each group is kept;
    all subsequent rows in the group are flagged.
    """
    flagged: list[tuple[int, str, str, str, str]] = []
    seen_exact: set[tuple] = set()

    # Group by Date + Strategy + Entry Time for exact dups.
    df_sorted = df.sort_values(["Date", "Strategy", "Entry Time"]).reset_index()
    for key, group in df_sorted.groupby(["Date", "Strategy", "Entry Time"]):
        if len(group) > 1:
            # Keep first (lowest original index), flag the rest.
            keep_idx = group.iloc[0]["index"]
            for _, r in group.iloc[1:].iterrows():
                flagged.append((r["index"], "exact", r["Date"], r["Entry Time"], r["Strategy"]))
                seen_exact.add(r["index"])

    # Group by Date + Strategy + StrategyId + strikes for probable dups.
    leg_cols = ["Short Call", "Long Call", "Short Put", "Long Put"]
    by_strat = df_sorted.groupby(["Date", "Strategy", "StrategyId"] + leg_cols)
    for _, group in by_strat:
        if len(group) <= 1:
            continue
        rows = group.sort_values("Entry Time").reset_index(drop=True)
        for i in range(1, len(rows)):
            cur, prev = rows.iloc[i], rows.iloc[i - 1]
            if cur["index"] in seen_exact:
                continue  # already flagged exact
            gap = entry_seconds(cur["Entry Time"]) - entry_seconds(prev["Entry Time"])
            if 0 < gap <= PROBABLE_DUP_WINDOW_SECONDS:
                flagged.append(
                    (cur["index"], "probable", cur["Date"], cur["Entry Time"], cur["Strategy"])
                )
    return sorted(flagged, key=lambda r: r[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", default=str(common.CSV_PATH), help="Path to paper_trades.csv")
    ap.add_argument("--apply", action="store_true", help="Remove duplicates (default: report only)")
    ap.add_argument("--no-backup", action="store_true", help="Skip the timestamped backup file")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}")

    flagged = find_duplicates(df)
    if not flagged:
        print("\nNo duplicates found. Nothing to do.")
        return

    print(f"\nFound {len(flagged)} duplicate row(s) to drop (keeping earliest in each group):")
    print(f"  {'idx':>5}  {'kind':<9}  {'date':<10}  {'time':<9}  strategy")
    for idx, kind, d, t, s in flagged:
        print(f"  {idx:>5}  {kind:<9}  {d:<10}  {t:<9}  {s}")

    if not args.apply:
        print("\nRun with --apply to remove these rows.")
        return

    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = csv_path.with_name(f"{csv_path.name}.backup_{ts}")
        shutil.copy(csv_path, backup)
        print(f"\nBackup saved: {backup}")

    indexes_to_drop = [f[0] for f in flagged]
    df_clean = df.drop(indexes_to_drop).reset_index(drop=True)
    df_clean.to_csv(csv_path, index=False)
    print(f"Wrote cleaned CSV: {csv_path}  ({len(df_clean)} rows, was {len(df)})")


if __name__ == "__main__":
    main()
