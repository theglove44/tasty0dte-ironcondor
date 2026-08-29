"""Capture SPX (SPXW) option-chain NBBO quotes for a backtesting corpus.

Daily Databento (OPRA.PILLAR, cbbo-1m) pull across the expirations the current
strategies trade — Tier A scope:

    * 0DTE                          (iron fly / iron condor)
    * 5 / 7 / 10 DTE target expiries (Jade Lizard variants)

For each capture day it enumerates every C+P strike in a spot-centred band
(±3% for 0-2 DTE, ±8% for 3-14 DTE) across those expiries, pulls 1-minute NBBO
for the full regular session (09:30-16:00 ET), and writes one parquet per day:

    data/chain_capture/{YYYY}/{YYYY-MM-DD}.parquet
        columns: symbol, expiry, dte, side, strike, bid, ask, mid, ts_et

Greeks/IV are NOT captured here — derive them later from these quotes
(see the enrichment pass in the spec). Every pull is cost-gated: --preview
reads metadata.get_cost without charging; --confirm downloads.

Usage
-----
    # Preview one recent day's cost (no charge):
    venv/bin/python tools/capture_spx_chain.py --date 2026-06-26 --preview

    # Download that day:
    venv/bin/python tools/capture_spx_chain.py --date 2026-06-26 --confirm

    # Daily cron: pull the prior trading day, skip if already on disk:
    venv/bin/python tools/capture_spx_chain.py --confirm --skip-existing

    # Backfill a range:
    venv/bin/python tools/capture_spx_chain.py --start 2026-06-01 --end 2026-06-26 --confirm --skip-existing

Environment
-----------
    DATABENTO_API_KEY  — https://app.databento.com/portal/keys
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# ── Capture window: full regular session ────────────────────────────────────
SESSION_OPEN_ET = (9, 30)
SESSION_CLOSE_ET = (16, 0)

# ── Strike grid & band ──────────────────────────────────────────────────────
STRIKE_STEP = 5
BAND_PCT_NEAR = 0.03   # 0-2 DTE half-band
BAND_PCT_FAR = 0.08    # 3-14 DTE half-band
NEAR_DTE_MAX = 2

# ── Tier A target DTEs (0DTE handled separately) ────────────────────────────
JL_TARGET_DTES = (5, 7, 10)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import CHAIN_CAPTURE_DIR  # noqa: E402
DATA_DIR = CHAIN_CAPTURE_DIR
MANIFEST = DATA_DIR / "_manifest.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require(pkg: str) -> None:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"Missing package — install with: venv/bin/pip install {pkg}")


def nearest5(x: float) -> int:
    return int(round(x / STRIKE_STEP) * STRIKE_STEP)


def osi(expiry: date, side: str, strike: int) -> str:
    """OCC symbol: 'SPXW  YYMMDD{C|P}NNNNNNNN' (two spaces, strike×1000, 8 digits)."""
    return f"SPXW  {expiry.strftime('%y%m%d')}{side.upper()}{strike * 1000:08d}"


def trading_days(start: date, end: date) -> list[date]:
    """Mon–Fri in [start, end]; holidays return empty pulls and are skipped naturally."""
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def next_weekday_on_or_after(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def tier_a_expiries(capture_day: date) -> list[date]:
    """0DTE + the 5/7/10-DTE target expiries, deduped & sorted.

    Mirrors the Jade Lizard rule: target = earliest SPXW expiry >= T + DTE.
    """
    exps: set[date] = set()
    if capture_day.weekday() < 5:
        exps.add(capture_day)                          # 0DTE
    for dte in JL_TARGET_DTES:
        exps.add(next_weekday_on_or_after(capture_day + timedelta(days=dte)))
    return sorted(exps)


def half_band_pct(dte: int) -> float:
    return BAND_PCT_NEAR if dte <= NEAR_DTE_MAX else BAND_PCT_FAR


def symbols_for_expiry(expiry: date, spot: float, capture_day: date) -> list[str]:
    """All C+P symbols in the DTE-tiered band around spot for one expiry."""
    dte = (expiry - capture_day).days
    half = spot * half_band_pct(dte)
    base = nearest5(spot)
    lo = nearest5(base - half)
    hi = nearest5(base + half)
    syms = []
    for k in range(lo, hi + STRIKE_STEP, STRIKE_STEP):
        if k <= 0:
            continue
        syms.append(osi(expiry, "C", k))
        syms.append(osi(expiry, "P", k))
    return syms


def symbols_for_day(capture_day: date, spot: float) -> tuple[list[str], list[date]]:
    """Union of symbols across all Tier-A expiries for the day."""
    expiries = tier_a_expiries(capture_day)
    syms: list[str] = []
    for exp in expiries:
        syms.extend(symbols_for_expiry(exp, spot, capture_day))
    return syms, expiries


def session_window_utc(day: date) -> tuple[str, str]:
    """[09:30 ET, 16:00 ET] on `day`, as UTC ISO strings."""
    o = datetime(day.year, day.month, day.day, *SESSION_OPEN_ET, tzinfo=ET)
    c = datetime(day.year, day.month, day.day, *SESSION_CLOSE_ET, tzinfo=ET)
    return (o.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            c.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))


def get_spx_close(day: date) -> float | None:
    """SPX close on `day` from yfinance — centres the strike band."""
    import yfinance as yf
    raw = yf.download(
        "^SPX",
        start=str(day - timedelta(days=5)),
        end=str(day + timedelta(days=1)),
        progress=False,
        auto_adjust=True,
    )
    if raw.empty:
        return None
    for ts in sorted(raw.index, reverse=True):
        if ts.date() <= day:
            v = raw.loc[ts, "Close"]
            return float(v.item() if hasattr(v, "item") else v)
    return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_day(df, capture_day: date) -> tuple[Path, int]:
    """Normalise the cbbo-1m frame and write one parquet for the day."""
    import pandas as pd

    out_dir = DATA_DIR / str(capture_day.year)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{capture_day}.parquet"

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

    # Fixed-point integers → dollars (some schemas return int64 × 1e9)
    for col in ("bid", "ask"):
        if col in df.columns and df[col].dtype.kind in ("i", "u"):
            df[col] = df[col] / 1_000_000_000.0

    df["mid"] = (df["bid"] + df["ask"]) / 2.0

    # Parse expiry / dte / side / strike from the OSI symbol
    df["expiry"] = pd.to_datetime(df["symbol"].str[6:12], format="%y%m%d").dt.date
    df["side"] = df["symbol"].str[12].str.upper()
    df["strike"] = (df["symbol"].str[-8:].astype(int) // 1000).astype(int)
    df["dte"] = (pd.to_datetime(df["expiry"]) - pd.Timestamp(capture_day)).dt.days

    if "ts_recv" in df.columns:
        df["ts_et"] = pd.to_datetime(df["ts_recv"], utc=True).dt.tz_convert(ET)
        df = df.drop(columns=["ts_recv"])

    df = df[["symbol", "expiry", "dte", "side", "strike", "bid", "ask", "mid", "ts_et"]]
    df.to_parquet(path, index=False)
    return path, len(df)


def append_manifest(capture_day: date, expiries: list[date], rows: int, cost: float) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "expiries", "rows", "cost_usd", "pulled_at"])
        w.writerow([
            capture_day,
            "|".join(str(e) for e in expiries),
            rows,
            f"{cost:.4f}",
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", help="Single capture day (YYYY-MM-DD)")
    p.add_argument("--start", help="Range start (YYYY-MM-DD)")
    p.add_argument("--end", help="Range end inclusive (YYYY-MM-DD)")
    p.add_argument("--preview", action="store_true", help="Cost estimate only — no charge")
    p.add_argument("--confirm", action="store_true", help="Download (charges your account)")
    p.add_argument("--skip-existing", action="store_true", help="Skip days already on disk")
    args = p.parse_args()

    if not args.preview and not args.confirm:
        p.error("Pass --preview to check cost, or --confirm to download.")

    # Resolve the day list
    if args.date:
        days = [date.fromisoformat(args.date)]
    elif args.start or args.end:
        start = date.fromisoformat(args.start) if args.start else date.today() - timedelta(days=1)
        end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
        days = trading_days(start, end)
    else:
        # Default cron behaviour: the prior trading day
        d = date.today() - timedelta(days=1)
        d = d if d.weekday() < 5 else next_weekday_on_or_after(d - timedelta(days=2))
        days = [d]

    if not days:
        sys.exit("No trading days in range.")

    _require("databento")
    _require("pyarrow")
    _require("yfinance")
    import databento as db
    import pandas as pd  # noqa: F401  (used in save_day)

    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        sys.exit("Set DATABENTO_API_KEY in your environment first.")
    client = db.Historical(key=api_key)

    total_cost = 0.0
    downloaded = 0
    skipped = 0

    print(f"SPX chain capture (Tier A: 0DTE + 5/7/10 DTE)  [{days[0]} → {days[-1]}]\n")

    for day in days:
        out_path = DATA_DIR / str(day.year) / f"{day}.parquet"
        if args.skip_existing and out_path.exists():
            skipped += 1
            continue

        spot = get_spx_close(day)
        if spot is None:
            print(f"  {day}  SKIP — no SPX close (holiday?)")
            continue

        syms, expiries = symbols_for_day(day, spot)
        t_start, t_end = session_window_utc(day)

        try:
            cost = client.metadata.get_cost(
                dataset="OPRA.PILLAR", symbols=syms, schema="cbbo-1m",
                start=t_start, end=t_end, stype_in="raw_symbol",
            )
        except Exception as e:
            print(f"  {day}  cost-check error: {type(e).__name__}: {e}")
            continue

        total_cost += cost
        exp_str = ", ".join(f"{e}(+{(e - day).days})" for e in expiries)
        print(f"  {day}  spot≈{nearest5(spot)}  expiries=[{exp_str}]  "
              f"symbols={len(syms)}  cost=${cost:.4f}")

        if args.confirm:
            try:
                store = client.timeseries.get_range(
                    dataset="OPRA.PILLAR", symbols=syms, schema="cbbo-1m",
                    start=t_start, end=t_end, stype_in="raw_symbol",
                )
                df = store.to_df()
                if df.empty:
                    print(f"    → no data returned (market closed / holiday)")
                    continue
                path, rows = save_day(df, day)
                append_manifest(day, expiries, rows, cost)
                print(f"    → saved {rows:,} rows → {path.relative_to(ROOT)}")
                downloaded += 1
            except Exception as e:
                print(f"    → ERROR: {type(e).__name__}: {e}")

    print()
    print(f"Total estimated cost : ${total_cost:.4f}")
    if args.skip_existing and skipped:
        print(f"Skipped (existing)   : {skipped} days")
    if args.confirm:
        print(f"Downloaded           : {downloaded} days → {DATA_DIR.relative_to(ROOT)}/")
    else:
        print("\nAdd --confirm to download (charges your Databento account).")


if __name__ == "__main__":
    main()
