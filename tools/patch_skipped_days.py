"""Patch the 10 sessions skipped by the V1 backtest due to narrow strike band.

On crash days (e.g. Liberation Day Apr 3 2025, Black Monday Aug 5 2024) the
STRIKE_BAND=150pt in fetch_v1_backtest_data.py centred on the prior-day close,
which meant the true ATM (already gapped down) was outside the downloaded range.

This script:
  1. For each skipped day — loads the existing Phase 1 parquet
  2. Runs put-call parity on ALL downloaded strikes to derive the true ATM
  3. Downloads just the 4 iron fly leg symbols for that ATM (cbbo-1m, full window)
  4. Merges the new rows into the existing parquet (overwrite)

Then optionally downloads the cbbo-1s legs (Phase 2) if the date is >=2025-02-20.

Usage
-----
    # Preview cost only:
    venv/bin/python tools/patch_skipped_days.py

    # Execute:
    venv/bin/python tools/patch_skipped_days.py --confirm
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET  = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

ENTRY_HOUR_ET, ENTRY_MIN_ET = 10, 0
EXIT_HOUR_ET,  EXIT_MIN_ET  = 13, 0
WING_WIDTH  = 10
STRIKE_STEP = 5

# These are the 10 sessions the backtest reported as SKIP:
SKIPPED_DAYS = [
    date(2022,  6,  2),
    date(2022, 11, 10),
    date(2024,  8,  5),
    date(2025,  4,  3),
    date(2025,  4,  4),
    date(2025,  4,  8),
    date(2025,  4, 10),
    date(2025,  4, 23),
    date(2025,  5, 12),
    date(2026,  4,  8),
]

CBBO_1S_START = date(2025, 2, 20)

ROOT     = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import BACKTEST_DATA_DIR  # noqa: E402
DATA_DIR = BACKTEST_DATA_DIR


def osi(expiry: date, side: str, strike: int) -> str:
    return f"SPXW  {expiry.strftime('%y%m%d')}{side.upper()}{strike * 1000:08d}"


def window_utc(day: date, extra_exit_mins: int = 10) -> tuple[str, str]:
    entry = datetime(day.year, day.month, day.day, ENTRY_HOUR_ET, ENTRY_MIN_ET, tzinfo=ET)
    exit_ = datetime(day.year, day.month, day.day, EXIT_HOUR_ET, EXIT_MIN_ET, tzinfo=ET)
    start = (entry - timedelta(minutes=5)).astimezone(UTC)
    end   = (exit_ + timedelta(minutes=extra_exit_mins)).astimezone(UTC)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def find_atm_from_parquet(path: Path) -> int | None:
    """Derive ATM via put-call parity on the 10:00 ET minute of the existing parquet."""
    import pandas as pd
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")

    df = pd.read_parquet(path)
    df["ts_et"]  = pd.to_datetime(df["ts_et"])
    df["side"]   = df["symbol"].str[12].str.upper()
    df["strike"] = df["symbol"].str[-8:].astype(int) // 1000
    df["mid"]    = df.get("mid", (df["bid"] + df["ask"]) / 2.0)

    day = date(df["ts_et"].dt.year.iloc[0],
               df["ts_et"].dt.month.iloc[0],
               df["ts_et"].dt.day.iloc[0])
    entry_dt = datetime(day.year, day.month, day.day, ENTRY_HOUR_ET, ENTRY_MIN_ET, tzinfo=ET)
    minute_rows = df[df["ts_et"].dt.floor("min") == entry_dt]

    calls = minute_rows[minute_rows["side"] == "C"][["strike", "mid"]].set_index("strike")
    puts  = minute_rows[minute_rows["side"] == "P"][["strike", "mid"]].set_index("strike")
    common = calls.index.intersection(puts.index)
    if len(common) < 3:
        return None
    forwards = [
        k + (calls.loc[k, "mid"] - puts.loc[k, "mid"])
        for k in common
        if calls.loc[k, "mid"] > 0 and puts.loc[k, "mid"] > 0
    ]
    if not forwards:
        return None
    median_f = sorted(forwards)[len(forwards) // 2]
    return int(round(median_f / STRIKE_STEP) * STRIKE_STEP)


def merge_into_parquet(new_df, path: Path) -> None:
    """Append new rows to existing parquet, dedup by (symbol, ts_et)."""
    import pandas as pd
    existing = pd.read_parquet(path)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["symbol", "ts_et"])
    combined = combined.sort_values("ts_et").reset_index(drop=True)
    combined.to_parquet(path, index=False)


def df_from_store(store, day: date, schema: str) -> "pd.DataFrame":
    import pandas as pd
    ET = ZoneInfo("America/New_York")
    df = store.to_df()
    if df.index.name in ("ts_recv", "ts_event") or hasattr(df.index, "tz"):
        df = df.reset_index()
    rename = {}
    for col in df.columns:
        lc = col.lower()
        if lc in ("bid_px_00", "bid_px"):
            rename[col] = "bid"
        elif lc in ("ask_px_00", "ask_px"):
            rename[col] = "ask"
    df = df.rename(columns=rename)
    for col in ("bid", "ask"):
        if col in df.columns and df[col].dtype.kind in ("i", "u"):
            df[col] = df[col] / 1_000_000_000.0
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    ts_col = "ts_recv" if "ts_recv" in df.columns else None
    if ts_col:
        if hasattr(df[ts_col], "dt"):
            df["ts_et"] = df[ts_col].dt.tz_convert(ET)
        else:
            df["ts_et"] = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert(ET)
        df = df.drop(columns=[ts_col])
    keep = [c for c in ("symbol", "bid", "ask", "mid", "ts_et", "atm") if c in df.columns]
    return df[keep]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true", help="Execute downloads (charges Databento)")
    args = parser.parse_args()

    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        print("Set DATABENTO_API_KEY in your environment first.", flush=True)
        sys.exit(1)

    try:
        import databento as db
    except ImportError:
        print("Missing package — install with: venv/bin/pip install databento", flush=True)
        sys.exit(1)

    print(f"Patching {len(SKIPPED_DAYS)} skipped days …", flush=True)
    print(f"Mode: {'EXECUTE' if args.confirm else 'PREVIEW (add --confirm to download)'}", flush=True)

    try:
        client = db.Historical(api_key)
    except Exception as e:
        print(f"Databento client error: {e}", flush=True)
        sys.exit(1)

    total_cost = 0.0

    for day in SKIPPED_DAYS:
        print(f"\n=== {day} ===", flush=True)
        p1_path = DATA_DIR / str(day.year) / f"{day}.parquet"

        if not p1_path.exists():
            print(f"  Phase 1 parquet missing — cannot derive ATM. Re-run fetch_v1_backtest_data.py for this day.")
            continue

        atm = find_atm_from_parquet(p1_path)
        if atm is None:
            print(f"  Cannot derive ATM from existing parquet (too few matched pairs at 10:00 ET).")
            print(f"  Need a full re-download with wider band — see notes below.")
            continue

        print(f"  Derived ATM via parity: {atm}")

        leg_syms = [
            osi(day, "C", atm),
            osi(day, "P", atm),
            osi(day, "C", atm + WING_WIDTH),
            osi(day, "P", atm - WING_WIDTH),
        ]
        print(f"  Leg symbols: {leg_syms}")

        t_start, t_end = window_utc(day)

        # --- Phase 1 patch: cbbo-1m for the 4 legs ---
        try:
            cost_1m = client.metadata.get_cost(
                dataset="OPRA.PILLAR",
                symbols=leg_syms,
                schema="cbbo-1m",
                start=t_start,
                end=t_end,
                stype_in="raw_symbol",
            )
        except Exception as e:
            print(f"  cbbo-1m cost-check error: {e}")
            cost_1m = 0.0

        total_cost += cost_1m
        print(f"  cbbo-1m patch cost: ${cost_1m:.4f}")

        if args.confirm:
            try:
                store = client.timeseries.get_range(
                    dataset="OPRA.PILLAR",
                    symbols=leg_syms,
                    schema="cbbo-1m",
                    start=t_start,
                    end=t_end,
                    stype_in="raw_symbol",
                )
                new_df = df_from_store(store, day, "cbbo-1m")
                if new_df.empty:
                    print(f"  cbbo-1m returned no data for these symbols.")
                else:
                    merge_into_parquet(new_df, p1_path)
                    print(f"  Merged {len(new_df)} rows into {p1_path.name}")
            except Exception as e:
                print(f"  cbbo-1m download error: {e}")

        # --- Phase 2: cbbo-1s for the 4 legs (only available from 2025-02-20) ---
        if day >= CBBO_1S_START:
            legs_path = DATA_DIR / str(day.year) / f"{day}_legs_1s.parquet"
            t2_start, t2_end = window_utc(day, extra_exit_mins=5)
            try:
                cost_1s = client.metadata.get_cost(
                    dataset="OPRA.PILLAR",
                    symbols=leg_syms,
                    schema="cbbo-1s",
                    start=t2_start,
                    end=t2_end,
                    stype_in="raw_symbol",
                )
            except Exception as e:
                print(f"  cbbo-1s cost-check error: {e}")
                cost_1s = 0.0

            total_cost += cost_1s
            print(f"  cbbo-1s patch cost: ${cost_1s:.4f}")

            if args.confirm:
                try:
                    store = client.timeseries.get_range(
                        dataset="OPRA.PILLAR",
                        symbols=leg_syms,
                        schema="cbbo-1s",
                        start=t2_start,
                        end=t2_end,
                        stype_in="raw_symbol",
                    )
                    new_df = df_from_store(store, day, "cbbo-1s")
                    if new_df.empty:
                        print(f"  cbbo-1s returned no data.")
                    else:
                        new_df["atm"] = atm
                        new_df.to_parquet(legs_path, index=False)
                        print(f"  Saved {len(new_df)} rows → {legs_path.name}")
                except Exception as e:
                    print(f"  cbbo-1s download error: {e}")

    print(f"\nTotal estimated cost: ${total_cost:.4f}")
    if not args.confirm:
        print("Add --confirm to execute downloads.")
    else:
        print("\nPatch complete. Re-run backtest:")
        print("  venv/bin/python tools/backtest_iron_fly_v1.py --start 2022-05-23 --end 2026-06-18")


if __name__ == "__main__":
    main()
