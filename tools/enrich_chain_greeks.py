"""Derive IV and Greeks for the captured SPX chain corpus.

Reads a day's NBBO parquet from data/chain_capture/ and writes a sibling
{date}_greeks.parquet with implied vol and Black-76 Greeks, computed purely
from the stored quotes — no extra data pull. Kept separate from capture so the
raw corpus stays pure NBBO and Greeks can be re-derived / improved any time.

Method
------
1. Forward per (expiry, minute) via put-call parity:  F = median(K + C_mid - P_mid)
   over strikes where both legs quote. Parity baked-in carry+dividends.
2. Implied vol per option by inverting Black-76 (vectorised bisection) against mid.
3. Greeks (Black-76) analytically from the solved vol.

Units: vega per 1 vol-point (i.e. per 0.01), theta per calendar day.
Rows where IV is undefined (T<=0, mid<=0, mid<=intrinsic, missing quote) get NaN.

Output columns:
    symbol, ts_et, expiry, dte, side, strike, forward, t_years,
    iv, delta, gamma, theta, vega

Usage
-----
    venv/bin/python tools/enrich_chain_greeks.py --date 2026-06-26
    venv/bin/python tools/enrich_chain_greeks.py --start 2026-06-01 --end 2026-06-26 --skip-existing
    venv/bin/python tools/enrich_chain_greeks.py            # all un-enriched days
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
YEAR_SECONDS = 365.0 * 24 * 3600.0
SETTLE_TIME = time(16, 0)          # SPXW PM settlement, 16:00 ET
DEFAULT_RATE = 0.045               # risk-free; effect is tiny at 0-14 DTE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import CHAIN_CAPTURE_DIR  # noqa: E402
DATA_DIR = CHAIN_CAPTURE_DIR


def _require(pkg: str) -> None:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"Missing package — install with: venv/bin/pip install {pkg}")


# ---------------------------------------------------------------------------
# Black-76 (forward) pricing & Greeks — vectorised over numpy arrays
# ---------------------------------------------------------------------------

def _black76_price(F, K, T, sigma, cp, DF):
    """Undiscounted-forward Black-76 price × DF. cp: +1 call, -1 put."""
    import numpy as np
    from scipy.stats import norm
    sqT = np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT
    return DF * cp * (F * norm.cdf(cp * d1) - K * norm.cdf(cp * d2))


def _solve_iv(market, F, K, T, cp, DF, iters: int = 80):
    """Vectorised bisection for implied vol. Returns NaN where undefined."""
    import numpy as np

    lo = np.full_like(market, 1e-4)
    hi = np.full_like(market, 5.0)

    # Validity mask: positive time, positive price, price above discounted intrinsic
    intrinsic = DF * np.maximum(cp * (F - K), 0.0)
    valid = (T > 0) & (market > 0) & np.isfinite(market) & (market > intrinsic + 1e-6) \
        & (F > 0) & (K > 0)

    for _ in range(iters):
        midv = 0.5 * (lo + hi)
        price = _black76_price(F, K, T, midv, cp, DF)
        too_high = price > market
        # price is monotonically increasing in sigma: too high → lower the
        # ceiling, otherwise raise the floor.
        hi = np.where(too_high, midv, hi)
        lo = np.where(too_high, lo, midv)

    iv = 0.5 * (lo + hi)
    return np.where(valid, iv, np.nan)


def _greeks(F, K, T, sigma, cp, DF, r):
    """Black-76 Greeks. vega per 1 vol-point, theta per calendar day."""
    import numpy as np
    from scipy.stats import norm

    sqT = np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT
    pdf = norm.pdf(d1)

    delta = DF * cp * norm.cdf(cp * d1)
    gamma = DF * pdf / (F * sigma * sqT)
    vega = DF * F * pdf * sqT / 100.0                       # per 0.01 vol
    decay = -(F * DF * pdf * sigma) / (2.0 * sqT)
    carry = cp * r * DF * (F * norm.cdf(cp * d1) - K * norm.cdf(cp * d2))
    theta = (decay - carry) / 365.0                         # per calendar day
    return delta, gamma, vega, theta


# ---------------------------------------------------------------------------
# Per-day enrichment
# ---------------------------------------------------------------------------

def enrich_day(capture_day: date, rate: float):
    import numpy as np
    import pandas as pd

    src = DATA_DIR / str(capture_day.year) / f"{capture_day}.parquet"
    if not src.exists():
        return None, "no source parquet"
    out = DATA_DIR / str(capture_day.year) / f"{capture_day}_greeks.parquet"

    df = pd.read_parquet(src)
    df = df.dropna(subset=["mid"]).copy()
    if df.empty:
        return None, "no priced rows"

    df["expiry"] = pd.to_datetime(df["expiry"])
    df["ts_et"] = pd.to_datetime(df["ts_et"])

    # ---- Forward per (expiry, minute) via put-call parity -------------------
    calls = df[df["side"] == "C"][["expiry", "ts_et", "strike", "mid"]]
    puts = df[df["side"] == "P"][["expiry", "ts_et", "strike", "mid"]]
    merged = calls.merge(puts, on=["expiry", "ts_et", "strike"],
                         suffixes=("_c", "_p"))
    merged = merged[(merged["mid_c"] > 0) & (merged["mid_p"] > 0)]
    merged["fwd"] = merged["strike"] + merged["mid_c"] - merged["mid_p"]
    fwd = (merged.groupby(["expiry", "ts_et"])["fwd"].median()
           .rename("forward").reset_index())

    df = df.merge(fwd, on=["expiry", "ts_et"], how="inner")
    if df.empty:
        return None, "no forward (no parity pairs)"

    # ---- Time to settlement (years) -----------------------------------------
    settle = (df["expiry"].dt.tz_localize(ET) if df["expiry"].dt.tz is None
              else df["expiry"]).dt.normalize() + pd.Timedelta(hours=16)
    df["t_years"] = (settle - df["ts_et"]).dt.total_seconds() / YEAR_SECONDS

    # ---- Vectorised IV + Greeks ---------------------------------------------
    F = df["forward"].to_numpy(float)
    K = df["strike"].to_numpy(float)
    T = df["t_years"].to_numpy(float)
    mid = df["mid"].to_numpy(float)
    cp = np.where(df["side"].to_numpy() == "C", 1.0, -1.0)
    DF = np.exp(-rate * np.clip(T, 0, None))

    with np.errstate(divide="ignore", invalid="ignore"):
        iv = _solve_iv(mid, F, K, T, cp, DF)
        delta, gamma, vega, theta = _greeks(F, K, T, iv, cp, DF, rate)

    df["iv"] = iv
    df["delta"] = np.where(np.isfinite(iv), delta, np.nan)
    df["gamma"] = np.where(np.isfinite(iv), gamma, np.nan)
    df["vega"] = np.where(np.isfinite(iv), vega, np.nan)
    df["theta"] = np.where(np.isfinite(iv), theta, np.nan)

    df["expiry"] = df["expiry"].dt.date
    cols = ["symbol", "ts_et", "expiry", "dte", "side", "strike",
            "forward", "t_years", "iv", "delta", "gamma", "theta", "vega"]
    df[cols].to_parquet(out, index=False)
    return out, f"{len(df):,} rows, {int(np.isfinite(iv).sum()):,} with IV"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _captured_days() -> list[date]:
    days = []
    for p in sorted(DATA_DIR.glob("*/*.parquet")):
        if p.stem.endswith("_greeks"):
            continue
        try:
            days.append(date.fromisoformat(p.stem))
        except ValueError:
            pass
    return days


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", help="Single day (YYYY-MM-DD)")
    p.add_argument("--start", help="Range start (YYYY-MM-DD)")
    p.add_argument("--end", help="Range end inclusive (YYYY-MM-DD)")
    p.add_argument("--rate", type=float, default=DEFAULT_RATE, help="Risk-free rate")
    p.add_argument("--skip-existing", action="store_true",
                   help="Skip days that already have a _greeks sidecar")
    args = p.parse_args()

    _require("numpy"); _require("scipy"); _require("pandas"); _require("pyarrow")

    if args.date:
        days = [date.fromisoformat(args.date)]
    elif args.start or args.end:
        lo = date.fromisoformat(args.start) if args.start else date.min
        hi = date.fromisoformat(args.end) if args.end else date.max
        days = [d for d in _captured_days() if lo <= d <= hi]
    else:
        days = _captured_days()

    if not days:
        sys.exit("No captured days to enrich.")

    done = skipped = 0
    for day in days:
        out = DATA_DIR / str(day.year) / f"{day}_greeks.parquet"
        if args.skip_existing and out.exists():
            skipped += 1
            continue
        path, msg = enrich_day(day, args.rate)
        if path is None:
            print(f"  {day}  SKIP — {msg}")
        else:
            print(f"  {day}  → {path.relative_to(ROOT)}  ({msg})")
            done += 1

    print(f"\nEnriched {done} day(s)" + (f", skipped {skipped} existing" if skipped else ""))


if __name__ == "__main__":
    main()
