"""Download Databento cbbo-1m option data for Iron Fly V1 backtesting.

Fetches intraday NBBO quotes for the SPXW 0DTE strikes needed to simulate V1
(short straddle at ATM ± 10-point wings) over a date range. Saves one parquet
file per trading day under data/v1_backtest/.

Usage
-----
    # Preview cost — no charge:
    venv/bin/python tools/fetch_v1_backtest_data.py --preview

    # Default range = 2022-05-23 to yesterday:
    venv/bin/python tools/fetch_v1_backtest_data.py --confirm

    # Custom range:
    venv/bin/python tools/fetch_v1_backtest_data.py --start 2024-01-01 --end 2025-12-31 --confirm

    # Skip days already downloaded:
    venv/bin/python tools/fetch_v1_backtest_data.py --confirm --skip-existing

Requirements
------------
    venv/bin/pip install databento yfinance pyarrow

Environment
-----------
    DATABENTO_API_KEY  — get from https://app.databento.com/portal/keys
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# V1 mechanics
ENTRY_HOUR_ET, ENTRY_MIN_ET = 10, 0
EXIT_HOUR_ET, EXIT_MIN_ET = 13, 0
ENTRY_BUFFER_MINS = 5   # fetch from 9:55 ET
EXIT_BUFFER_MINS = 10   # fetch to 13:10 ET

# Strike sampling — ±60pt around estimated ATM covers any realistic overnight gap
STRIKE_STEP = 5
STRIKE_BAND = 150  # total half-width in dollars — covers ~2% gap at SPX 7500 (weekend gaps)
WING_WIDTH  = 10   # iron fly wing width in dollars (must match backtest_iron_fly_v1.py)

# SPXW 0DTE went fully daily (M/W/F + T/Th) from 2022-05-23
BACKTEST_START_DEFAULT = date(2022, 5, 23)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import BACKTEST_DATA_DIR  # noqa: E402
DATA_DIR = BACKTEST_DATA_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require(pkg: str) -> None:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"Missing package — install with: venv/bin/pip install {pkg}")


def trading_days(start: date, end: date) -> list[date]:
    """Mon–Fri in [start, end] — no holiday filter (holidays are sparse, skip them naturally)."""
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def nearest5(x: float) -> int:
    return int(round(x / STRIKE_STEP) * STRIKE_STEP)


def osi(expiry: date, side: str, strike: int) -> str:
    """OCC symbol: SPXW  YYMMDD{C|P}NNNNNNNN  (strike × 1000, 8 digits)."""
    return f"SPXW  {expiry.strftime('%y%m%d')}{side.upper()}{strike * 1000:08d}"


def symbols_for_day(expiry: date, atm_est: float) -> list[str]:
    """All C+P symbols in ±STRIKE_BAND around estimated ATM."""
    base = nearest5(atm_est)
    syms = []
    for k in range(base - STRIKE_BAND, base + STRIKE_BAND + STRIKE_STEP, STRIKE_STEP):
        syms.append(osi(expiry, "C", k))
        syms.append(osi(expiry, "P", k))
    return syms


def window_utc(day: date) -> tuple[str, str]:
    """[9:55 ET − 13:10 ET] in UTC ISO strings for the given date."""
    entry = datetime(day.year, day.month, day.day, ENTRY_HOUR_ET, ENTRY_MIN_ET, tzinfo=ET)
    exit_ = datetime(day.year, day.month, day.day, EXIT_HOUR_ET, EXIT_MIN_ET, tzinfo=ET)
    start = (entry - timedelta(minutes=ENTRY_BUFFER_MINS)).astimezone(UTC)
    end = (exit_ + timedelta(minutes=EXIT_BUFFER_MINS)).astimezone(UTC)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_spx_closes(start: date, end: date) -> dict[date, float]:
    """SPX daily closes from yfinance (free) — used only to estimate ATM per day."""
    import yfinance as yf
    raw = yf.download(
        "^SPX",
        start=str(start - timedelta(days=7)),
        end=str(end + timedelta(days=1)),
        progress=False,
        auto_adjust=True,
    )
    if raw.empty:
        sys.exit("yfinance returned no SPX data — check date range or internet connection.")
    # Build {date: close} using previous-day close as ATM estimate for the next day
    closes: dict[date, float] = {}
    dates_sorted = sorted(raw.index)
    for i, ts in enumerate(dates_sorted):
        if i + 1 < len(dates_sorted):
            next_date = dates_sorted[i + 1].date()
            closes[next_date] = float(raw.loc[ts, "Close"].item() if hasattr(raw.loc[ts, "Close"], "item") else raw.loc[ts, "Close"])
    return closes


def save_day(df, day: date) -> Path:
    """Persist a day's quotes as parquet."""
    import pandas as pd
    out_dir = DATA_DIR / str(day.year)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}.parquet"

    # Databento SDK puts ts_recv as the DatetimeIndex — pull it into columns first
    if df.index.name in ("ts_recv", "ts_event") or hasattr(df.index, "tz"):
        df = df.reset_index()

    # Normalise columns from cbbo-1m schema
    rename = {}
    for col in df.columns:
        lc = col.lower()
        if lc in ("bid_px_00", "bid_px"):
            rename[col] = "bid"
        elif lc in ("ask_px_00", "ask_px"):
            rename[col] = "ask"
    df = df.rename(columns=rename)

    # Keep only the columns we need
    keep = [c for c in ("ts_recv", "symbol", "bid", "ask") if c in df.columns]
    df = df[keep].copy()

    # Convert prices from fixed-point integers if needed (Databento returns int64 / 1e9 in some schemas)
    for col in ("bid", "ask"):
        if col in df.columns and df[col].dtype.kind in ("i", "u"):
            df[col] = df[col] / 1_000_000_000.0

    df["mid"] = (df["bid"] + df["ask"]) / 2.0

    # Localise timestamp to ET
    if "ts_recv" in df.columns:
        if hasattr(df["ts_recv"], "dt"):
            df["ts_et"] = df["ts_recv"].dt.tz_convert(ET)
        else:
            df["ts_et"] = pd.to_datetime(df["ts_recv"], utc=True).dt.tz_convert(ET)
        df = df.drop(columns=["ts_recv"])

    df.to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# ATM via put-call parity (inlined to avoid cross-module import issues)
# ---------------------------------------------------------------------------

def _find_atm(df_minute) -> int | None:
    """Forward price from put-call parity → nearest 5-pt grid strike."""
    calls = df_minute[df_minute["side"] == "C"][["strike", "mid"]].set_index("strike")
    puts  = df_minute[df_minute["side"] == "P"][["strike", "mid"]].set_index("strike")
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


# ---------------------------------------------------------------------------
# Phase 2 — 1-second leg data for precise exit monitoring
# ---------------------------------------------------------------------------

def legs_window_utc(day: date) -> tuple[str, str]:
    """[10:00 ET − 13:05 ET] in UTC for the exit-monitoring window."""
    entry = datetime(day.year, day.month, day.day, ENTRY_HOUR_ET, ENTRY_MIN_ET, tzinfo=ET)
    exit_ = datetime(day.year, day.month, day.day, EXIT_HOUR_ET, EXIT_MIN_ET, tzinfo=ET)
    start = entry.astimezone(UTC)
    end = (exit_ + timedelta(minutes=5)).astimezone(UTC)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def save_legs(df, day: date, atm: int) -> Path:
    """Persist 1-second leg quotes."""
    import pandas as pd
    out_dir = DATA_DIR / str(day.year)
    path = out_dir / f"{day}_legs_1s.parquet"

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

    keep = [c for c in ("ts_recv", "symbol", "bid", "ask") if c in df.columns]
    df = df[keep].copy()

    for col in ("bid", "ask"):
        if col in df.columns and df[col].dtype.kind in ("i", "u"):
            df[col] = df[col] / 1_000_000_000.0

    df["mid"] = (df["bid"] + df["ask"]) / 2.0

    if "ts_recv" in df.columns:
        df["ts_et"] = pd.to_datetime(df["ts_recv"], utc=True).dt.tz_convert(ET)
        df = df.drop(columns=["ts_recv"])

    df["atm"] = atm
    df.to_parquet(path, index=False)
    return path


def fetch_legs_for_day(client, day: date, df_1m) -> Path | None:
    """
    Phase 2: determine ATM from existing 1m data, then download cbbo-1s
    for just the 4 leg symbols over the exit-monitoring window.
    """
    import pandas as pd

    df = df_1m.copy()
    df["ts_et"] = pd.to_datetime(df["ts_et"])
    df["side"] = df["symbol"].str[12].str.upper()
    df["strike"] = (df["symbol"].str[-8:].astype(int) // 1000).astype(int)

    # Filter to 0DTE for this day
    day_str = day.strftime("%y%m%d")
    df = df[df["symbol"].str[6:12] == day_str]

    entry_rows = df[df["ts_et"].dt.floor("min").dt.strftime("%H:%M") == "10:00"]
    if entry_rows.empty:
        return None

    atm = _find_atm(entry_rows)
    if atm is None:
        return None

    lc_strike = atm + WING_WIDTH
    lp_strike = atm - WING_WIDTH
    syms = [
        osi(day, "C", atm),
        osi(day, "P", atm),
        osi(day, "C", lc_strike),
        osi(day, "P", lp_strike),
    ]

    t_start, t_end = legs_window_utc(day)

    store = client.timeseries.get_range(
        dataset="OPRA.PILLAR",
        symbols=syms,
        schema="cbbo-1s",
        start=t_start,
        end=t_end,
        stype_in="raw_symbol",
    )
    df_out = store.to_df()
    if df_out.empty:
        return None

    return save_legs(df_out, day, atm)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default=str(BACKTEST_START_DEFAULT), help="First date (YYYY-MM-DD)")
    parser.add_argument("--end", default=str(date.today() - timedelta(days=1)), help="Last date inclusive (YYYY-MM-DD)")
    parser.add_argument("--preview", action="store_true", help="Show cost estimate without downloading")
    parser.add_argument("--confirm", action="store_true", help="Actually download (charges your account)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip days with an existing parquet file")
    parser.add_argument("--legs", action="store_true",
                        help="Phase 2: download cbbo-1s for the 4 leg symbols using ATM from existing 1m data")
    args = parser.parse_args()

    if not args.preview and not args.confirm:
        parser.error("Pass --preview to check cost, or --confirm to download.")

    _require("databento")
    _require("pyarrow")
    if not args.legs:
        _require("yfinance")

    import databento as db
    import pandas as pd

    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        sys.exit("Set DATABENTO_API_KEY in your environment first.")

    client = db.Historical(key=api_key)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = trading_days(start, end)
    if not days:
        sys.exit(f"No trading days in {start} → {end}")

    # ---- Phase 2: 1-second leg data ----
    if args.legs:
        print(f"Phase 2 — cbbo-1s for 4 leg symbols  [{start} → {end}]")
        total_cost = 0.0
        downloaded = 0
        skipped = 0
        for day in days:
            legs_path = DATA_DIR / str(day.year) / f"{day}_legs_1s.parquet"
            if args.skip_existing and legs_path.exists():
                skipped += 1
                continue
            phase1_path = DATA_DIR / str(day.year) / f"{day}.parquet"
            if not phase1_path.exists():
                print(f"  {day}  SKIP — Phase 1 file missing (run without --legs first)")
                continue
            df_1m = pd.read_parquet(phase1_path)
            df_1m["ts_et"] = pd.to_datetime(df_1m["ts_et"])

            # Determine ATM and build 4 symbols for cost check
            df_1m["side"] = df_1m["symbol"].str[12].str.upper()
            df_1m["strike"] = (df_1m["symbol"].str[-8:].astype(int) // 1000).astype(int)
            day_str = day.strftime("%y%m%d")
            entry_rows = df_1m[
                (df_1m["symbol"].str[6:12] == day_str) &
                (df_1m["ts_et"].dt.floor("min").dt.strftime("%H:%M") == "10:00")
            ]
            if entry_rows.empty:
                print(f"  {day}  SKIP — no 10:00 row in Phase 1 data")
                continue

            atm = _find_atm(entry_rows)
            if atm is None:
                print(f"  {day}  SKIP — ATM not determinable from Phase 1 data")
                continue

            syms = [
                osi(day, "C", atm), osi(day, "P", atm),
                osi(day, "C", atm + WING_WIDTH), osi(day, "P", atm - WING_WIDTH),
            ]
            t_start, t_end = legs_window_utc(day)

            try:
                cost = client.metadata.get_cost(
                    dataset="OPRA.PILLAR", symbols=syms, schema="cbbo-1s",
                    start=t_start, end=t_end, stype_in="raw_symbol",
                )
            except Exception as e:
                print(f"  {day}  cost-check error: {e}")
                continue

            total_cost += cost
            print(f"  {day}  ATM={atm}  symbols={syms[0][-14:]}…  cost=${cost:.4f}")

            if args.confirm:
                try:
                    store = client.timeseries.get_range(
                        dataset="OPRA.PILLAR", symbols=syms, schema="cbbo-1s",
                        start=t_start, end=t_end, stype_in="raw_symbol",
                    )
                    df_out = store.to_df()
                    if df_out.empty:
                        print(f"    → no data returned")
                        continue
                    path = save_legs(df_out, day, atm)
                    print(f"    → saved {len(df_out):,} rows → {path}")
                    downloaded += 1
                except Exception as e:
                    print(f"    → ERROR: {e}")

        print()
        print(f"Total estimated cost : ${total_cost:.4f}")
        if args.skip_existing and skipped:
            print(f"Skipped (existing)   : {skipped} days")
        if args.confirm:
            print(f"Downloaded           : {downloaded} days")
        else:
            print("Add --confirm to download.")
        return

    # ---- Phase 1: 1-minute full chain ----
    print(f"Fetching SPX closing prices from yfinance to estimate ATM per day …")
    closes = get_spx_closes(start, end)

    total_cost = 0.0
    skipped = 0
    downloaded = 0

    for day in days:
        parquet_path = DATA_DIR / str(day.year) / f"{day}.parquet"
        if args.skip_existing and parquet_path.exists():
            skipped += 1
            continue

        atm_est = closes.get(day)
        if atm_est is None:
            print(f"  {day}  SKIP — no SPX close for prior day (holiday?)")
            continue

        syms = symbols_for_day(day, atm_est)
        t_start, t_end = window_utc(day)

        try:
            cost = client.metadata.get_cost(
                dataset="OPRA.PILLAR",
                symbols=syms,
                schema="cbbo-1m",
                start=t_start,
                end=t_end,
                stype_in="raw_symbol",
            )
        except Exception as e:
            print(f"  {day}  cost-check error: {e}")
            continue

        total_cost += cost
        print(f"  {day}  ATM≈{nearest5(atm_est)}  symbols={len(syms)}  cost=${cost:.4f}")

        if args.confirm:
            try:
                store = client.timeseries.get_range(
                    dataset="OPRA.PILLAR",
                    symbols=syms,
                    schema="cbbo-1m",
                    start=t_start,
                    end=t_end,
                    stype_in="raw_symbol",
                )
                df = store.to_df()
                if df.empty:
                    print(f"    → no data returned (market closed / holiday)")
                    continue
                path = save_day(df, day)
                print(f"    → saved {len(df):,} rows → {path}")
                downloaded += 1
            except Exception as e:
                print(f"    → ERROR: {e}")

    print()
    print(f"Total estimated cost : ${total_cost:.4f}")
    if args.skip_existing and skipped:
        print(f"Skipped (existing)   : {skipped} days")
    if args.confirm:
        print(f"Downloaded           : {downloaded} days → {DATA_DIR}/")
        print()
        print("Next (Phase 2): venv/bin/python tools/fetch_v1_backtest_data.py --legs --confirm --skip-existing")
    else:
        print()
        print("Add --confirm to download (charges your Databento account).")


if __name__ == "__main__":
    main()
