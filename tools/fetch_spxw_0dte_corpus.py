"""Build a general-purpose, full-session SPXW 0DTE minute-NBBO corpus.

The selected strikes cover the day's SPX low through high, plus ten 5-point
strikes on either side. Daily files make downloads restartable; --consolidate
creates one portable Parquet after the daily corpus is complete.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import local
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
STRIKE_STEP = 5
ATM_PADDING_STRIKES = 10
TUESDAY_FIRST_EXPIRY = date(2022, 4, 26)
THURSDAY_FIRST_EXPIRY = date(2022, 5, 19)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import GENERAL_0DTE_DIR  # noqa: E402

DATA_DIR = GENERAL_0DTE_DIR
MANIFEST = DATA_DIR / "_manifest.csv"
_thread_state = local()


def is_spxw_expiry_day(day: date) -> bool:
    """Return whether SPXW had a regular expiry on this weekday in May 2022+."""
    if day.weekday() >= 5:
        return False
    if day.weekday() == 1 and day < TUESDAY_FIRST_EXPIRY:
        return False
    if day.weekday() == 3 and day < THURSDAY_FIRST_EXPIRY:
        return False
    return True


def osi(expiry: date, side: str, strike: int) -> str:
    return f"SPXW  {expiry.strftime('%y%m%d')}{side.upper()}{strike * 1000:08d}"


def strike_bounds(day_low: float, day_high: float) -> tuple[int, int]:
    """Five-point bounds covering the day's range plus ATM +/-10 strikes."""
    padding = ATM_PADDING_STRIKES * STRIKE_STEP
    low = math.floor(day_low / STRIKE_STEP) * STRIKE_STEP - padding
    high = math.ceil(day_high / STRIKE_STEP) * STRIKE_STEP + padding
    return low, high


def symbols_for_day(day: date, day_low: float, day_high: float) -> list[str]:
    low, high = strike_bounds(day_low, day_high)
    return [osi(day, side, strike)
            for strike in range(low, high + STRIKE_STEP, STRIKE_STEP)
            for side in ("C", "P")]


def session_window(day: date) -> tuple[datetime, datetime]:
    return (datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET),
            datetime(day.year, day.month, day.day, 16, 0, tzinfo=ET))


def load_spx_ranges(start: date, end: date) -> dict[date, tuple[float, float]]:
    import yfinance as yf

    raw = yf.download("^SPX", start=str(start), end=str(end + timedelta(days=1)),
                      progress=False, auto_adjust=True)
    ranges: dict[date, tuple[float, float]] = {}
    for ts in raw.index:
        day = ts.date()
        if not is_spxw_expiry_day(day):
            continue
        low = raw.loc[ts, "Low"]
        high = raw.loc[ts, "High"]
        low_value = float(low.item() if hasattr(low, "item") else low)
        high_value = float(high.item() if hasattr(high, "item") else high)
        ranges[day] = (low_value, high_value)
    return ranges


def _client():
    import databento as db

    client = getattr(_thread_state, "client", None)
    if client is None:
        client = db.Historical(os.environ["DATABENTO_API_KEY"])
        _thread_state.client = client
    return client


def _day_path(day: date) -> Path:
    return DATA_DIR / str(day.year) / f"{day}.parquet"


def get_day_cost(day: date, low: float, high: float) -> tuple[date, float, int]:
    symbols = symbols_for_day(day, low, high)
    start, end = session_window(day)
    cost = _client().metadata.get_cost(
        dataset="OPRA.PILLAR", symbols=symbols, schema="cbbo-1m",
        start=start, end=end, stype_in="raw_symbol")
    return day, float(cost), len(symbols)


def save_day(day: date, low: float, high: float, expected_cost: float) -> tuple[date, int, int, float]:
    import pandas as pd

    symbols = symbols_for_day(day, low, high)
    start, end = session_window(day)
    store = _client().timeseries.get_range(
        dataset="OPRA.PILLAR", symbols=symbols, schema="cbbo-1m",
        start=start, end=end, stype_in="raw_symbol")
    frame = store.to_df().reset_index()
    if frame.empty:
        return day, 0, len(symbols), expected_cost

    timestamp_column = "ts_recv" if "ts_recv" in frame.columns else "ts_event"
    frame = frame.rename(columns={timestamp_column: "ts_et"})
    frame["ts_et"] = pd.to_datetime(frame["ts_et"], utc=True).dt.tz_convert(ET)
    frame["trade_date"] = day
    frame["expiry"] = day
    frame["option_type"] = frame["symbol"].str[12].str.upper()
    frame["strike"] = frame["symbol"].str[-8:].astype(int) / 1000.0

    path = _day_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)
    return day, len(frame), len(symbols), expected_cost


def write_manifest(results: list[tuple[date, int, int, float | None]], ranges) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "spx_low", "spx_high", "symbols", "rows", "cost_usd"])
        for day, rows, symbols, cost in sorted(results):
            low, high = ranges[day]
            cost_text = "" if cost is None else f"{cost:.6f}"
            writer.writerow([day, f"{low:.2f}", f"{high:.2f}", symbols, rows, cost_text])


def consolidate(start: date, end: date) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    files = sorted(p for p in DATA_DIR.glob("*/*.parquet")
                   if start <= date.fromisoformat(p.stem) <= end)
    if not files:
        raise SystemExit("No daily corpus files to consolidate.")
    output = DATA_DIR / f"spxw_0dte_cbbo_1m_{start}_{end}.parquet"
    temporary = output.with_suffix(".parquet.tmp")
    if output.exists() or temporary.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {output}")

    first = pq.read_table(files[0])
    metadata = dict(first.schema.metadata or {})
    metadata.update({b"dataset": b"OPRA.PILLAR", b"schema": b"cbbo-1m",
                     b"scope": b"SPXW 0DTE; full session; daily SPX high/low plus 10 strikes"})
    schema = first.schema.with_metadata(metadata)
    writer = pq.ParquetWriter(temporary, schema, compression="zstd")
    rows = 0
    try:
        for path in files:
            table = pq.read_table(path).cast(schema)
            writer.write_table(table)
            rows += table.num_rows
    finally:
        writer.close()
    os.replace(temporary, output)
    print(f"Consolidated {len(files)} files / {rows:,} rows -> {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-05-01")
    parser.add_argument("--end", default=str(date.today() - timedelta(days=1)))
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--consolidate", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-cost", type=float, default=7.0)
    args = parser.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if args.consolidate:
        consolidate(start, end)
        return
    if not args.preview and not args.confirm:
        parser.error("Pass --preview or --confirm.")
    if not os.environ.get("DATABENTO_API_KEY"):
        raise SystemExit("DATABENTO_API_KEY is not set.")

    ranges = load_spx_ranges(start, end)
    pending = [(day, *values) for day, values in sorted(ranges.items())
               if not (args.skip_existing and _day_path(day).exists())]
    print(f"Eligible sessions: {len(ranges)}; pending: {len(pending)}")

    costs: list[tuple[date, float, int]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(get_day_cost, *item) for item in pending]
        for future in as_completed(futures):
            day, cost, symbols = future.result()
            costs.append((day, cost, symbols))
    total = sum(item[1] for item in costs)
    print(f"Exact Databento estimate: ${total:.4f} for {len(costs)} pending sessions")
    if args.preview:
        return
    if total > args.max_cost:
        raise SystemExit(f"Cost ${total:.4f} exceeds --max-cost ${args.max_cost:.2f}; no download started.")

    cost_by_day = {day: cost for day, cost, _ in costs}
    results: list[tuple[date, int, int, float]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(save_day, day, low, high, cost_by_day[day])
                   for day, low, high in pending]
        for completed, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            if completed % 25 == 0 or completed == len(futures):
                print(f"Downloaded {completed}/{len(futures)} sessions")

    # Include existing daily files in the manifest on resumed runs.
    for day in sorted(ranges):
        if day in cost_by_day:
            continue
        path = _day_path(day)
        if path.exists():
            import pyarrow.parquet as pq
            low, high = ranges[day]
            results.append((day, pq.ParquetFile(path).metadata.num_rows,
                            len(symbols_for_day(day, low, high)), None))
    write_manifest(results, ranges)
    print(f"Saved daily corpus under {DATA_DIR}")


if __name__ == "__main__":
    main()
