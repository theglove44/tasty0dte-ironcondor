#!/usr/bin/env python3
"""
0DTE Put Credit Spread Backtest

Entry : Daily at 10:00 ET (= 15:00 UK BST)
Legs  : Short ~30-delta put (K1), Long put at K1 - 5
Credit: Actual mid prices from Databento cbbo parquet data
Exit  : Expire (default), take-profit (--tp), stop-loss (--sl), or both

Note: intraday data covers 10:00–13:09 ET only.  TP/SL hits in that window
use real mid prices; positions still open at 13:09 ET fall through to SPX PM
settlement (same as expire mode).

Usage
-----
    venv/bin/python tools/backtest_put_cs_0dte.py                # expire
    venv/bin/python tools/backtest_put_cs_0dte.py --tp 50        # 50% TP
    venv/bin/python tools/backtest_put_cs_0dte.py --sl 200       # 200% SL
    venv/bin/python tools/backtest_put_cs_0dte.py --tp 50 --sl 200
"""

from __future__ import annotations

import argparse
import sys
import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

warnings.filterwarnings("ignore")

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import BACKTEST_DATA_DIR  # noqa: E402
DATA_DIR = BACKTEST_DATA_DIR

DELTA_TARGET = 0.30     # absolute delta of short put
SPREAD_WIDTH = 5        # width of spread in points
ENTRY_HOUR_ET = 10      # 10:00 ET = 15:00 UK BST
T_ENTRY_TO_CLOSE = 6.0 / (365 * 24)  # 10am to 4pm ET in years
TP_PCT: float | None = None   # set by --tp arg; None = no TP
SL_PCT: float | None = None   # set by --sl arg; e.g. 200 = close when debit = 2× credit


# ---------------------------------------------------------------------------
# Black-Scholes helpers
# ---------------------------------------------------------------------------

def bs_put_delta(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    """Return absolute put delta (positive, range 0–1)."""
    if T <= 0 or sigma <= 0:
        return 1.0 if K > S else 0.0
    sqrt_T = T ** 0.5
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    return float(norm.cdf(-d1))  # absolute value of put delta


def implied_vol_atm(price: float, S: float, T: float, r: float = 0.0) -> float:
    """Invert BS for ATM put (K=S, r=0) to get implied vol.

    Correct ATM put price: P = S*(N(d1) - N(-d1)) = S*(2*N(d1)-1)
    where d1 = 0.5*sigma*sqrt(T) when K=S and r=0.
    """
    low, high = 0.01, 5.0
    for _ in range(60):
        sigma = (low + high) / 2
        d1 = 0.5 * sigma * (T ** 0.5)
        p = S * (2 * norm.cdf(d1) - 1)
        if p < price:
            low = sigma
        else:
            high = sigma
    return (low + high) / 2


# ---------------------------------------------------------------------------
# Symbol parsing
# ---------------------------------------------------------------------------

def parse_symbol(sym: str):
    """Return (side, strike) from OCC-style symbol like 'SPXW  240108P04545000'."""
    s = sym.strip()
    # Find P or C after the date digits
    for i, c in enumerate(s):
        if c in ("P", "C") and i > 4:
            return c, int(s[i + 1:]) / 1000
    return None, None


# ---------------------------------------------------------------------------
# Per-day logic
# ---------------------------------------------------------------------------

@dataclass
class TradeResult:
    date: date
    spot: float
    short_strike: float
    long_strike: float
    short_delta_est: float
    entry_credit: float
    spx_close: float
    pl: float
    exit_reason: str      # "TP" / "SL" / "WORTHLESS" / "PARTIAL" / "MAX_LOSS"
    exit_time_et: str = ""


def find_30d_put(puts: pd.DataFrame, spot: float, sigma: float) -> int | None:
    """
    Return the strike (integer, on 5-pt grid) whose BS delta is closest to DELTA_TARGET.
    puts: DataFrame indexed by strike, must contain 'mid' column.
    """
    best_strike = None
    best_diff = float("inf")
    for strike, row in puts.iterrows():
        if row["mid"] <= 0:
            continue
        delta = bs_put_delta(spot, strike, T_ENTRY_TO_CLOSE, sigma)
        diff = abs(delta - DELTA_TARGET)
        if diff < best_diff:
            best_diff = diff
            best_strike = strike
    return best_strike


def process_day(parquet_path: Path, spx_close: float) -> TradeResult | None:
    df = pd.read_parquet(parquet_path)

    # Snap to 10:00 ET
    entry_ts = pd.Timestamp(parquet_path.stem[:10], tz=ET).replace(
        hour=ENTRY_HOUR_ET, minute=0, second=0
    )
    snap = df[df["ts_et"] == entry_ts].copy()
    if snap.empty:
        # Try first snapshot at or after 10:00 ET
        candidates = df[df["ts_et"].dt.hour >= ENTRY_HOUR_ET]
        if candidates.empty:
            return None
        entry_ts = candidates["ts_et"].min()
        snap = df[df["ts_et"] == entry_ts].copy()

    # Parse side / strike
    parsed = snap["symbol"].apply(parse_symbol)
    snap = snap.copy()
    snap["side"] = parsed.apply(lambda x: x[0])
    snap["strike"] = parsed.apply(lambda x: x[1])
    snap = snap.dropna(subset=["side", "strike"])

    calls = snap[snap["side"] == "C"].set_index("strike")
    puts  = snap[snap["side"] == "P"].set_index("strike")
    calls = calls[~calls.index.duplicated(keep="last")]
    puts  = puts[~puts.index.duplicated(keep="last")]

    if puts.empty:
        return None

    # Infer spot from put-call parity across common strikes
    common = calls.index.intersection(puts.index)
    if len(common) < 3:
        return None
    parity = pd.DataFrame({
        "call_mid": calls.loc[common, "mid"],
        "put_mid":  puts.loc[common, "mid"],
    })
    parity["implied_spot"] = parity.index + parity["call_mid"] - parity["put_mid"]
    spot = float(parity["implied_spot"].median())

    # ATM strike (nearest 5-pt grid)
    atm_strike = round(spot / 5) * 5

    # ATM IV from the ATM put price
    if atm_strike in puts.index and puts.loc[atm_strike, "mid"] > 0:
        atm_price = float(puts.loc[atm_strike, "mid"])
    else:
        # Fall back to nearest available put
        nearest = puts.index[(puts.index - spot).abs() < 15]
        if nearest.empty:
            return None
        atm_price = float(puts.loc[nearest[0], "mid"])

    sigma = implied_vol_atm(atm_price, spot, T_ENTRY_TO_CLOSE)
    if sigma <= 0:
        return None

    # Find short put (closest to 30 delta)
    short_strike = find_30d_put(puts, spot, sigma)
    if short_strike is None:
        return None
    long_strike = short_strike - SPREAD_WIDTH

    # Check both legs exist with positive mid
    if long_strike not in puts.index:
        return None
    short_mid = float(puts.loc[short_strike, "mid"])
    long_mid  = float(puts.loc[long_strike,  "mid"])
    if short_mid <= 0 or long_mid <= 0:
        return None

    entry_credit = round(short_mid - long_mid, 4)
    if entry_credit <= 0:
        return None

    short_delta_est = bs_put_delta(spot, short_strike, T_ENTRY_TO_CLOSE, sigma)

    # ---- Intraday TP / SL scan ----
    if TP_PCT is not None or SL_PCT is not None:
        tp_debit = entry_credit * (1 - TP_PCT / 100) if TP_PCT is not None else None
        sl_debit = entry_credit * (SL_PCT / 100)     if SL_PCT is not None else None

        later = df[df["ts_et"] > entry_ts].copy()
        if not later.empty:
            parsed2 = later["symbol"].apply(parse_symbol)
            later["side"]   = parsed2.apply(lambda x: x[0])
            later["strike"] = parsed2.apply(lambda x: x[1])
            later = later.dropna(subset=["side", "strike"])
            put_rows = later[
                (later["side"] == "P") &
                (later["strike"].isin([short_strike, long_strike]))
            ].copy()
            for ts, grp in put_rows.groupby("ts_et", sort=True):
                grp_idx = grp.set_index("strike")
                grp_idx = grp_idx[~grp_idx.index.duplicated(keep="last")]
                if short_strike not in grp_idx.index or long_strike not in grp_idx.index:
                    continue
                s_mid = float(grp_idx.loc[short_strike, "mid"])
                l_mid = float(grp_idx.loc[long_strike,  "mid"])
                if s_mid <= 0 or l_mid <= 0:
                    continue
                debit = s_mid - l_mid
                # TP fires first (better price); SL fires if debit blows out
                if tp_debit is not None and debit <= tp_debit:
                    pl = round(entry_credit - debit, 4)
                    reason = "TP"
                elif sl_debit is not None and debit >= sl_debit:
                    pl = round(entry_credit - debit, 4)
                    reason = "SL"
                else:
                    continue
                return TradeResult(
                    date=date.fromisoformat(parquet_path.stem[:10]),
                    spot=round(spot, 1),
                    short_strike=short_strike,
                    long_strike=long_strike,
                    short_delta_est=round(short_delta_est, 3),
                    entry_credit=entry_credit,
                    spx_close=round(spx_close, 2),
                    pl=pl,
                    exit_reason=reason,
                    exit_time_et=str(ts),
                )

    # ---- Settlement (expire or TP not hit by data cutoff) ----
    if spx_close >= short_strike:
        pl = entry_credit
        reason = "WORTHLESS"
    elif spx_close > long_strike:
        intrinsic = short_strike - spx_close
        pl = round(entry_credit - intrinsic, 4)
        reason = "PARTIAL"
    else:
        pl = round(entry_credit - SPREAD_WIDTH, 4)
        reason = "MAX_LOSS"

    return TradeResult(
        date=date.fromisoformat(parquet_path.stem[:10]),
        spot=round(spot, 1),
        short_strike=short_strike,
        long_strike=long_strike,
        short_delta_est=round(short_delta_est, 3),
        entry_credit=entry_credit,
        spx_close=round(spx_close, 2),
        pl=pl,
        exit_reason=reason,
        exit_time_et="settle",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global SPREAD_WIDTH, TP_PCT, SL_PCT
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-05-23")
    parser.add_argument("--end",   default="2026-06-18")
    parser.add_argument("--width", type=int,   default=SPREAD_WIDTH)
    parser.add_argument("--tp",    type=float, default=None,
                        help="Take-profit: close when spread value = (1 - TP/100) × credit")
    parser.add_argument("--sl",    type=float, default=None,
                        help="Stop-loss: close when debit = (SL/100) × credit (e.g. 200 = 2× credit)")
    args = parser.parse_args()

    SPREAD_WIDTH = args.width
    TP_PCT = args.tp
    SL_PCT = args.sl

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    # Collect all parquet files in range (plain files only)
    files = sorted(
        f for f in DATA_DIR.rglob("*.parquet")
        if "_legs_1s" not in f.name
        and start <= date.fromisoformat(f.stem[:10]) <= end
    )
    if not files:
        sys.exit("No parquet files found in range.")

    print(f"Found {len(files)} trading days ({files[0].stem[:10]} → {files[-1].stem[:10]})")

    # Fetch SPX closing prices from yfinance
    print("Fetching SPX daily closes from yfinance…")
    raw = yf.download(
        "^GSPC",
        start=args.start,
        end=(end + timedelta(days=1)).isoformat(),
        progress=False,
        auto_adjust=True,
    )
    if raw.empty:
        sys.exit("yfinance returned no data — check your internet connection.")

    # Handle MultiIndex columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)
    spx_closes = raw["Close"].to_dict()
    # Normalise keys to date objects
    spx_closes = {
        k.date() if hasattr(k, "date") else k: float(v)
        for k, v in spx_closes.items()
    }

    # Run backtest
    results: list[TradeResult] = []
    skipped = 0
    for path in files:
        d = date.fromisoformat(path.stem[:10])
        close = spx_closes.get(d)
        if close is None:
            skipped += 1
            continue
        r = process_day(path, close)
        if r is None:
            skipped += 1
            continue
        results.append(r)

    if not results:
        sys.exit("No trades generated.")

    print(f"Processed {len(results)} trades, skipped {skipped} days\n")

    # Build output DataFrame
    rows = [
        {
            "Date":          r.date,
            "Spot":          r.spot,
            "Short Strike":  r.short_strike,
            "Long Strike":   r.long_strike,
            "Short Delta":   r.short_delta_est,
            "Credit":        r.entry_credit,
            "SPX Close":     r.spx_close,
            "P/L":           r.pl,
            "Exit":          r.exit_reason,
            "Exit Time ET":  r.exit_time_et,
        }
        for r in results
    ]
    df = pd.DataFrame(rows)

    parts = []
    if TP_PCT: parts.append(f"{int(TP_PCT)}% TP")
    if SL_PCT: parts.append(f"{int(SL_PCT)}% SL")
    mode_label = " + ".join(parts) + " (data to 13:09; fallback=settle)" if parts else "EXPIRE AT CLOSE"

    # ---- Summary stats ----
    total_pl  = df["P/L"].sum()
    avg_pl    = df["P/L"].mean()
    avg_credit= df["Credit"].mean()
    wins      = (df["P/L"] > 0).sum()
    losses    = (df["P/L"] < 0).sum()
    flat      = (df["P/L"] == 0).sum()
    wr        = wins / len(df) * 100
    tp_hits   = (df["Exit"] == "TP").sum()
    sl_hits   = (df["Exit"] == "SL").sum()
    worthless = (df["Exit"] == "WORTHLESS").sum()
    partial   = (df["Exit"] == "PARTIAL").sum()
    max_loss  = (df["Exit"] == "MAX_LOSS").sum()
    avg_win   = df.loc[df["P/L"] > 0, "P/L"].mean() if wins else 0
    avg_loss  = df.loc[df["P/L"] < 0, "P/L"].mean() if losses else 0
    payoff    = abs(avg_win / avg_loss) if avg_loss else float("inf")
    max_dd    = (df["P/L"].cumsum() - df["P/L"].cumsum().cummax()).min()

    # Year-by-year breakdown
    df["Year"] = pd.to_datetime(df["Date"]).dt.year
    by_year = df.groupby("Year").agg(
        Trades=("P/L", "count"),
        Total_PL=("P/L", "sum"),
        Avg_PL=("P/L", "mean"),
        WR=("P/L", lambda x: (x > 0).mean() * 100),
        MaxLoss=("Exit", lambda x: (x == "MAX_LOSS").sum()),
    ).round(2)

    print("=" * 60)
    print(f"  0DTE PUT CREDIT SPREAD — {mode_label}")
    print(f"  Entry: 10:00 ET | Short ~30Δ put | {SPREAD_WIDTH}-pt wide")
    print("=" * 60)
    print(f"  Trades      : {len(df)}")
    print(f"  Win Rate    : {wr:.1f}%  ({wins}W / {losses}L / {flat} flat)")
    print(f"  Avg Credit  : ${avg_credit:.2f}")
    print(f"  Avg P/L     : ${avg_pl:.2f}")
    print(f"  Total P/L   : ${total_pl:.2f}")
    print(f"  Avg Win     : ${avg_win:.2f}")
    print(f"  Avg Loss    : ${avg_loss:.2f}")
    print(f"  Payoff Ratio: {payoff:.2f}")
    print(f"  Max Drawdown: ${max_dd:.2f}")
    exit_parts = []
    if tp_hits:   exit_parts.append(f"{tp_hits} TP")
    if sl_hits:   exit_parts.append(f"{sl_hits} SL")
    if worthless: exit_parts.append(f"{worthless} worthless")
    if partial:   exit_parts.append(f"{partial} partial")
    if max_loss:  exit_parts.append(f"{max_loss} max-loss")
    print(f"  Exits: {' / '.join(exit_parts)}")
    if sl_hits:
        sl_pl = df.loc[df["Exit"] == "SL", "P/L"]
        print(f"  Avg SL P/L: ${sl_pl.mean():.2f}  (max: ${sl_pl.min():.2f})")
    print()

    print("  Year-by-Year:")
    print(by_year.to_string())
    print()

    # Worst 10 days
    print("  Worst 10 days:")
    worst = df.nsmallest(10, "P/L")[["Date","Spot","Short Strike","SPX Close","Credit","P/L","Exit"]]
    print(worst.to_string(index=False))
    print()

    # Delta distribution sanity check
    print(f"  Avg short delta at entry: {df['Short Delta'].mean():.3f}  "
          f"(target: {DELTA_TARGET:.2f})")

    # Save CSV
    suffix_parts = []
    if TP_PCT: suffix_parts.append(f"tp{int(TP_PCT)}")
    if SL_PCT: suffix_parts.append(f"sl{int(SL_PCT)}")
    suffix = "_" + "_".join(suffix_parts) if suffix_parts else "_expire"
    out_path = ROOT / "data" / f"put_cs_0dte_backtest{suffix}.csv"
    df.to_csv(out_path, index=False)
    print(f"\n  Saved to {out_path}")


if __name__ == "__main__":
    main()
