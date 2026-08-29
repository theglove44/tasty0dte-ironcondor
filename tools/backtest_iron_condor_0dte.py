#!/usr/bin/env python3
"""
Iron Condor 0DTE Backtest

Entry   : 10:00 ET (open + 30 min)
Strikes : Short call/put at ±expected_move from ATM (~20 delta); long wings $5 wider
Width   : $5 per side
Exit    : 25% profit target OR PM settlement (whichever comes first within intraday data)
Fills   : Both mid-price (paper) and real bid/ask tracked side-by-side

Expected move = spot × σ_atm × √T  (T = 6hr to close, same formula as JL/tastytrade)
Rounds to nearest 5-pt grid.

Usage
-----
    venv/bin/python tools/backtest_iron_condor_0dte.py
    venv/bin/python tools/backtest_iron_condor_0dte.py --start 2024-01-01
"""

from __future__ import annotations

import argparse
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

ET       = ZoneInfo("America/New_York")
ROOT     = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from project_paths import BACKTEST_DATA_DIR  # noqa: E402
DATA_DIR = BACKTEST_DATA_DIR

ENTRY_HOUR_ET   = 10
TP_PCT          = 25          # close when debit ≤ (1 - 0.25) × credit
WING_WIDTH      = 5           # pts from short strike to long strike (overridden by --width)
T_TO_CLOSE_YRS  = 6.0 / (365 * 24)   # 10:00→16:00 ET in years


# ---------------------------------------------------------------------------
# BS helpers
# ---------------------------------------------------------------------------

def implied_vol_atm(price: float, S: float, T: float) -> float:
    """Invert BS for ATM put price → IV. Correct ATM formula: P = S*(2N(d1)-1)."""
    if price <= 0 or S <= 0 or T <= 0:
        return 0.0
    low, high = 0.01, 5.0
    for _ in range(60):
        sigma = (low + high) / 2
        d1 = 0.5 * sigma * T ** 0.5
        p = S * (2 * norm.cdf(d1) - 1)
        if p < price:
            low = sigma
        else:
            high = sigma
    return (low + high) / 2


def expected_move(spot: float, sigma: float, T: float) -> float:
    """1-sigma expected move = spot × sigma × √T."""
    return spot * sigma * T ** 0.5


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    date: date
    spot: float
    short_call: int
    long_call: int
    short_put: int
    long_put: int
    sigma: float

    entry_credit_mid:  float
    entry_credit_real: float

    exit_debit_mid:  float
    exit_debit_real: float
    exit_reason_mid:  str   # "TP" / "WORTHLESS" / "PARTIAL_PUT" / "PARTIAL_CALL" / "MAX_LOSS"
    exit_reason_real: str

    @property
    def pl_mid(self)  -> float: return round(self.entry_credit_mid  - self.exit_debit_mid,  4)
    @property
    def pl_real(self) -> float: return round(self.entry_credit_real - self.exit_debit_real, 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_symbol(sym: str):
    s = sym.strip()
    for i, c in enumerate(s):
        if c in ("P", "C") and i > 4:
            return c, int(s[i + 1:]) / 1000
    return None, None


def settlement_pl(credit: float, spx_close: float,
                  sc: int, lc: int, sp: int, lp: int) -> tuple[float, str]:
    """Compute P/L and reason at PM settlement."""
    put_intrinsic  = max(sp - spx_close, 0.0)
    call_intrinsic = max(spx_close - sc, 0.0)
    # Intrinsic capped at spread width (long wing absorbs remainder)
    put_loss  = min(put_intrinsic,  WING_WIDTH)
    call_loss = min(call_intrinsic, WING_WIDTH)
    pl = round(credit - put_loss - call_loss, 4)

    if put_loss == 0 and call_loss == 0:
        reason = "WORTHLESS"
    elif put_loss > 0 and call_loss > 0:
        reason = "BOTH_ITM"
    elif put_loss > 0:
        reason = "PUT_ITM"
    else:
        reason = "CALL_ITM"
    return pl, reason


# ---------------------------------------------------------------------------
# Per-day simulation
# ---------------------------------------------------------------------------

def process_day(parquet_path: Path, spx_close: float) -> Trade | None:
    df = pd.read_parquet(parquet_path)

    day_str = parquet_path.stem[:10]
    entry_ts = pd.Timestamp(day_str, tz=ET).replace(hour=ENTRY_HOUR_ET, minute=0, second=0)

    snap = df[df["ts_et"] == entry_ts].copy()
    if snap.empty:
        candidates = df[df["ts_et"].dt.hour >= ENTRY_HOUR_ET]
        if candidates.empty:
            return None
        entry_ts = candidates["ts_et"].min()
        snap = df[df["ts_et"] == entry_ts].copy()

    parsed = snap["symbol"].apply(parse_symbol)
    snap = snap.copy()
    snap["side"]   = parsed.apply(lambda x: x[0])
    snap["strike"] = parsed.apply(lambda x: x[1])
    snap = snap.dropna(subset=["side", "strike"])

    calls = snap[snap["side"] == "C"].set_index("strike")
    puts  = snap[snap["side"] == "P"].set_index("strike")
    calls = calls[~calls.index.duplicated(keep="last")]
    puts  = puts[~puts.index.duplicated(keep="last")]

    if puts.empty or calls.empty:
        return None

    # Spot via put-call parity
    common = calls.index.intersection(puts.index)
    if len(common) < 3:
        return None
    parity_spot = float(
        pd.Series([k + calls.loc[k, "mid"] - puts.loc[k, "mid"] for k in common]).median()
    )
    spot = round(parity_spot, 1)

    # ATM IV
    atm5 = round(parity_spot / 5) * 5
    atm_row = puts.loc[atm5] if atm5 in puts.index else None
    if atm_row is None or float(atm_row["mid"]) <= 0:
        nearby = puts.index[abs(puts.index - parity_spot) < 15]
        if nearby.empty:
            return None
        atm_row = puts.loc[nearby[0]]
    sigma = implied_vol_atm(float(atm_row["mid"]), parity_spot, T_TO_CLOSE_YRS)
    if sigma <= 0:
        return None

    em = expected_move(parity_spot, sigma, T_TO_CLOSE_YRS)
    em5 = round(em / 5) * 5   # snap to 5-pt grid

    sc = int(round((parity_spot + em5) / 5) * 5)   # short call
    lc = sc + WING_WIDTH                             # long call
    sp = int(round((parity_spot - em5) / 5) * 5)   # short put
    lp = sp - WING_WIDTH                             # long put

    # Verify all 4 legs exist with positive quotes
    def get(frame, strike, col) -> float | None:
        s = int(strike)
        if s not in frame.index:
            return None
        v = float(frame.loc[s, col])
        return v if v > 0 else None

    sc_mid = get(calls, sc, "mid");  lc_mid = get(calls, lc, "mid")
    sp_mid = get(puts,  sp, "mid");  lp_mid = get(puts,  lp, "mid")
    if None in (sc_mid, sp_mid):
        return None
    lc_mid = lc_mid or 0.0
    lp_mid = lp_mid or 0.0

    ec_mid = round(sc_mid + sp_mid - lc_mid - lp_mid, 4)
    if ec_mid <= 0 or ec_mid >= WING_WIDTH:   # sanity: credit can't exceed spread width
        return None

    # Real entry: sell shorts at bid, buy longs at ask
    sc_bid = get(calls, sc, "bid") or sc_mid
    sp_bid = get(puts,  sp, "bid") or sp_mid
    lc_ask = get(calls, lc, "ask") or lc_mid
    lp_ask = get(puts,  lp, "ask") or lp_mid
    ec_real = round(sc_bid + sp_bid - lc_ask - lp_ask, 4)

    tp_threshold = ec_mid * (1 - TP_PCT / 100)   # mid TP target
    tp_real_threshold = ec_real * (1 - TP_PCT / 100)  # real TP target

    # ---- Intraday scan: look for 25% TP ----
    later = df[df["ts_et"] > entry_ts].copy()

    mid_exit_debit  = None
    mid_exit_reason = None
    real_exit_debit  = None
    real_exit_reason = None

    if not later.empty:
        parsed2 = later["symbol"].apply(parse_symbol)
        later = later.copy()
        later["side"]   = parsed2.apply(lambda x: x[0])
        later["strike"] = parsed2.apply(lambda x: x[1])
        later = later.dropna(subset=["side", "strike"])

        wanted = {sc, lc, sp, lp}
        filtered = later[later["strike"].isin(wanted)].copy()

        for ts, grp in filtered.groupby("ts_et", sort=True):
            gi = grp.set_index("strike")
            gi = gi[~gi.index.duplicated(keep="last")]
            c_g = gi[gi["side"] == "C"]
            p_g = gi[gi["side"] == "P"]

            def gmid(frame, k): return float(frame.loc[k, "mid"]) if k in frame.index and float(frame.loc[k, "mid"]) > 0 else 0.0
            def gask(frame, k): return float(frame.loc[k, "ask"]) if k in frame.index and float(frame.loc[k, "ask"]) > 0 else 0.0
            def gbid(frame, k): return float(frame.loc[k, "bid"]) if k in frame.index and float(frame.loc[k, "bid"]) > 0 else 0.0

            sc_m = gmid(c_g, sc);  sp_m = gmid(p_g, sp)
            if sc_m <= 0 or sp_m <= 0:
                continue
            lc_m = gmid(c_g, lc);  lp_m = gmid(p_g, lp)
            mid_debit = sc_m + sp_m - lc_m - lp_m

            sc_a = gask(c_g, sc) or sc_m + 0.10
            sp_a = gask(p_g, sp) or sp_m + 0.10
            lc_b = gbid(c_g, lc) or max(lc_m - 0.05, 0.0)
            lp_b = gbid(p_g, lp) or max(lp_m - 0.05, 0.0)
            real_debit = sc_a + sp_a - lc_b - lp_b

            if mid_exit_debit is None and mid_debit <= tp_threshold:
                mid_exit_debit  = mid_debit
                mid_exit_reason = "TP"

            if real_exit_debit is None and real_debit <= tp_real_threshold:
                real_exit_debit  = real_debit
                real_exit_reason = "TP"

            if mid_exit_debit is not None and real_exit_debit is not None:
                break

    # Settlement fallback for whichever fill mode didn't exit intraday
    settle_pl, settle_reason = settlement_pl(ec_mid, spx_close, sc, lc, sp, lp)

    if mid_exit_debit is None:
        mid_exit_debit  = round(ec_mid - settle_pl, 4)
        mid_exit_reason = settle_reason

    settle_pl_r, settle_reason_r = settlement_pl(ec_real, spx_close, sc, lc, sp, lp)
    if real_exit_debit is None:
        real_exit_debit  = round(ec_real - settle_pl_r, 4)
        real_exit_reason = settle_reason_r

    return Trade(
        date=date.fromisoformat(day_str),
        spot=spot,
        short_call=sc, long_call=lc,
        short_put=sp,  long_put=lp,
        sigma=round(sigma, 4),
        entry_credit_mid=ec_mid,
        entry_credit_real=ec_real,
        exit_debit_mid=round(mid_exit_debit, 4),
        exit_debit_real=round(real_exit_debit, 4),
        exit_reason_mid=mid_exit_reason,
        exit_reason_real=real_exit_reason,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(trades: list[Trade]) -> None:
    if not trades:
        print("No trades.")
        return

    from collections import defaultdict

    def stats(pls, reasons):
        wins   = [p for p in pls if p > 0]
        losses = [p for p in pls if p <= 0]
        total  = sum(pls)
        avg    = total / len(pls)
        wr     = len(wins) / len(pls) * 100
        aw     = sum(wins) / max(len(wins), 1)
        al     = sum(losses) / max(len(losses), 1)
        pf     = abs(aw / al) if al and aw else 0.0
        tp_n   = sum(1 for r in reasons if r == "TP")
        return total, avg, wr, aw, al, pf, tp_n

    pls_m  = [t.pl_mid  for t in trades]
    pls_r  = [t.pl_real for t in trades]
    rm     = [t.exit_reason_mid  for t in trades]
    rr     = [t.exit_reason_real for t in trades]

    tm, am, wrm, awm, alm, pfm, tp_m = stats(pls_m, rm)
    tr, ar, wrr, awr, alr, pfr, tp_r = stats(pls_r, rr)

    avg_credit_mid  = sum(t.entry_credit_mid  for t in trades) / len(trades)
    avg_credit_real = sum(t.entry_credit_real for t in trades) / len(trades)

    print(f"\n{'='*65}")
    print(f"IRON CONDOR 0DTE  ({len(trades)} sessions)  "
          f"TP={TP_PCT}%  wings={WING_WIDTH}pt  entry=10:00ET")
    print(f"{'='*65}")
    print(f"  {'':26s}  {'MID (paper)':>12}  {'REAL (bid/ask)':>14}")
    print(f"  {'-'*54}")
    print(f"  {'Avg entry credit':26s}  ${avg_credit_mid:>+10.2f}  ${avg_credit_real:>+12.2f}")
    print(f"  {'Total P/L':26s}  ${tm:>+10.2f}  ${tr:>+12.2f}")
    print(f"  {'Avg P/L / trade':26s}  ${am:>+10.4f}  ${ar:>+12.4f}")
    print(f"  {'Win rate':26s}  {wrm:>10.1f}%  {wrr:>12.1f}%")
    print(f"  {'Avg win':26s}  ${awm:>+10.2f}  ${awr:>+12.2f}")
    print(f"  {'Avg loss':26s}  ${alm:>+10.2f}  ${alr:>+12.2f}")
    print(f"  {'Payoff ratio':26s}  {pfm:>10.2f}x  {pfr:>12.2f}x")
    print(f"  {'Round-trip slippage':26s}  {'':12s}  ${(tm-tr)/len(trades):>+12.4f}/trade")
    print(f"  {'-'*54}")
    print(f"  TP exits (mid trigger)   : {tp_m}  ({tp_m/len(trades)*100:.1f}%)")
    print(f"  TP exits (real trigger)  : {tp_r}  ({tp_r/len(trades)*100:.1f}%)")

    by_month = defaultdict(list)
    for t in trades:
        by_month[t.date.strftime("%Y-%m")].append(t)

    print(f"\n  {'Month':<8}  {'N':>4}  {'Mid P/L':>9}  {'Real P/L':>9}  {'WR(mid)':>8}")
    for month in sorted(by_month):
        mt   = by_month[month]
        mpl  = sum(t.pl_mid  for t in mt)
        rpl  = sum(t.pl_real for t in mt)
        mwr  = sum(1 for t in mt if t.pl_mid > 0) / len(mt) * 100
        print(f"  {month:<8}  {len(mt):>4}  {mpl:>+9.2f}  {rpl:>+9.2f}  {mwr:>7.1f}%")

    print(f"{'='*65}")

    credits = sorted(t.entry_credit_mid for t in trades)
    n = len(credits)
    print(f"\n  Entry credit (mid) — avg={sum(credits)/n:.2f}  "
          f"p25={credits[n//4]:.2f}  p50={credits[n//2]:.2f}  p75={credits[3*n//4]:.2f}")
    print(f"  min={credits[0]:.2f}  max={credits[-1]:.2f}")

    avg_em = sum(t.short_call - t.spot for t in trades) / len(trades)
    print(f"  Avg expected move (call side): ±{avg_em:.1f} pts from spot")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global WING_WIDTH
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2022-05-23")
    parser.add_argument("--end",   default=str(date.today() - timedelta(days=1)))
    parser.add_argument("--width", type=int, default=WING_WIDTH,
                        help="Wing width in pts (default 5)")
    args = parser.parse_args()
    WING_WIDTH = args.width

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    # Collect all parquet files in range
    files: list[Path] = []
    for year_dir in sorted(DATA_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        for f in sorted(year_dir.glob("*.parquet")):
            d = date.fromisoformat(f.stem[:10])
            if start <= d <= end:
                files.append(f)

    if not files:
        print(f"No parquet files found in {DATA_DIR} for {start}→{end}")
        return

    # Fetch SPX close prices once
    print(f"Fetching SPX daily closes {start} → {end} …")
    ticker = yf.Ticker("^GSPC")
    hist = ticker.history(start=str(start), end=str(end + timedelta(days=3)))
    spx_map: dict[date, float] = {
        d.date(): float(row["Close"])
        for d, row in hist.iterrows()
    }

    print(f"Processing {len(files)} sessions …")
    trades: list[Trade] = []
    skipped = 0
    for f in files:
        d = date.fromisoformat(f.stem[:10])
        spx_close = spx_map.get(d)
        if spx_close is None:
            skipped += 1
            continue
        t = process_day(f, spx_close)
        if t is None:
            skipped += 1
        else:
            trades.append(t)

    print(f"  {skipped} sessions skipped (holiday / missing data / no entry)")
    print_report(trades)


if __name__ == "__main__":
    main()
