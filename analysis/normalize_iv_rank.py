#!/usr/bin/env python3
"""
normalize_iv_rank.py
====================

Normalise the ``IV Rank`` column in paper_trades.csv to the canonical 0-1 ratio.

Background
----------
``IV Rank`` was historically logged on two different scales:

    * 0-1 ratio (the tastytrade SDK's native ``implied_volatility_index_rank``),
      e.g. ``0.12`` -- used for rows up to 2026-01-16.
    * 0-100 percentage, e.g. ``25.55`` -- used from 2026-01-20 onward, after a
      write-time guard in logger.py started multiplying ratios by 100.

The mixed scale broke ``analysis/common.iv_bin`` (which assumes a 0-1 ratio):
every percentage-encoded row was misclassified into the ">=0.50" bin, so the
IV-regime breakdown was meaningless. logger.py now normalises to the ratio at
write time; this script backfills the historical rows to match.

A true IV-rank ratio never exceeds 1.0, so any stored value > 1.5 is a 0-100
percentage and is divided by 100. Ratio rows and the ``0.00`` "no data"
sentinels are left untouched. The script is idempotent: after one run no value
exceeds 1.5, so re-running is a no-op.

Note: values are reformatted to two decimals to match logger.py's output and the
existing ratio rows. The bin boundaries (0.20 / 0.35 / 0.50) sit on the 2-dp
grid, so a handful of rows whose true ratio is within ~0.005 of a boundary
(e.g. 19.67% -> 0.20) bin by their rounded value. This is a fundamental limit of
the CSV's 2-dp precision (monitor.py rewrites with ``float_format='%.2f'``), not
of this backfill.

Usage
-----
    python3 analysis/normalize_iv_rank.py                 # report only
    python3 analysis/normalize_iv_rank.py --apply         # rewrite in place
    python3 analysis/normalize_iv_rank.py --apply --no-backup

When --apply is set, the original CSV is backed up to
paper_trades.csv.backup_YYYYMMDD_HHMMSS unless --no-backup is given (mirrors
analysis/dedup_trades.py).
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

IV_COLUMN = "IV Rank"
# A true IV-rank ratio is in [0, 1]; anything above this must be a 0-100 percentage.
PERCENTAGE_THRESHOLD = 1.5


def normalize_cell(raw: str) -> tuple[str, bool]:
    """Return ``(new_value, changed)`` for one IV Rank cell.

    Percentage-encoded values (> 1.5) are divided by 100 and formatted to two
    decimals. Empty cells, non-numeric cells, and values already on the ratio
    scale are returned unchanged.
    """
    if raw is None or raw.strip() == "":
        return raw, False
    try:
        value = float(raw)
    except ValueError:
        return raw, False
    if value > PERCENTAGE_THRESHOLD:
        return f"{value / 100.0:.2f}", True
    return raw, False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", default=str(common.CSV_PATH), help="Path to paper_trades.csv")
    ap.add_argument("--apply", action="store_true", help="Rewrite the CSV (default: report only)")
    ap.add_argument("--no-backup", action="store_true", help="Skip the timestamped backup file")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    with open(csv_path, newline="") as fh:
        rows = list(csv.reader(fh))

    if not rows:
        print(f"{csv_path} is empty; nothing to do.")
        return

    header, data = rows[0], rows[1:]
    if IV_COLUMN not in header:
        print(f"No '{IV_COLUMN}' column in {csv_path}; nothing to do.")
        return
    iv_idx = header.index(IV_COLUMN)

    changes: list[tuple[int, str, str]] = []  # (1-based row number incl. header, old, new)
    for i, row in enumerate(data):
        if iv_idx >= len(row):
            continue
        new_val, changed = normalize_cell(row[iv_idx])
        if changed:
            changes.append((i + 2, row[iv_idx], new_val))
            row[iv_idx] = new_val

    print(f"Loaded {len(data)} data rows from {csv_path}")
    if not changes:
        print("All IV Rank values are already on the 0-1 ratio scale. Nothing to do.")
        return

    print(f"\n{len(changes)} percentage-encoded IV Rank value(s) to rescale (/100):")
    to_show = changes if len(changes) <= 12 else changes[:6] + [None] + changes[-6:]
    for entry in to_show:
        if entry is None:
            print(f"  ... ({len(changes) - 12} more) ...")
            continue
        rownum, old, new = entry
        print(f"  row {rownum}: {old} -> {new}")

    if not args.apply:
        print("\nRun with --apply to rewrite the CSV.")
        return

    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = csv_path.with_name(f"{csv_path.name}.backup_{ts}")
        shutil.copy(csv_path, backup)
        print(f"\nBackup saved: {backup}")

    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(data)
    print(f"Wrote normalised CSV: {csv_path}  ({len(data)} rows, {len(changes)} values rescaled)")


if __name__ == "__main__":
    main()
