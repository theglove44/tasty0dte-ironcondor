#!/usr/bin/env python3
"""
Iron Fly V1 — Strategy enrichment analysis.
Runs all 5 research tracks from research_plan_v1_enrichment.md.

Usage:
    venv/bin/python analysis/strategy_enrichment.py
    venv/bin/python analysis/strategy_enrichment.py --rebuild   # force re-fetch market data
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from project_paths import DATA_DIR  # noqa: E402

BT_CACHE = DATA_DIR / "v1_bt_cache.json"
MKT_CACHE = DATA_DIR / "market_data_cache.json"
ENRICHED_OUT = DATA_DIR / "v1_enriched.json"

DISCOVERY_END = date(2024, 12, 31)
MIN_N = 30  # minimum bin size for reporting

# ── Calendar data (FOMC/OpEx/Triple-witching 2022-2026) ──────────────────────

_FOMC_ALL: frozenset[date] = frozenset({
    # 2022
    date(2022, 1, 26), date(2022, 3, 16), date(2022, 5, 4), date(2022, 6, 15),
    date(2022, 7, 27), date(2022, 9, 21), date(2022, 11, 2), date(2022, 12, 14),
    # 2023
    date(2023, 2, 1), date(2023, 3, 22), date(2023, 5, 3), date(2023, 6, 14),
    date(2023, 7, 26), date(2023, 9, 20), date(2023, 11, 1), date(2023, 12, 13),
    # 2024
    date(2024, 1, 31), date(2024, 3, 20), date(2024, 5, 1), date(2024, 6, 12),
    date(2024, 7, 31), date(2024, 9, 18), date(2024, 11, 7), date(2024, 12, 18),
    # 2025
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7), date(2025, 6, 18),
    date(2025, 7, 30), date(2025, 9, 17), date(2025, 10, 29), date(2025, 12, 10),
    # 2026
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
})

_TRIPLE_WITCHING: frozenset[date] = frozenset({
    date(2022, 3, 18), date(2022, 6, 17), date(2022, 9, 16), date(2022, 12, 16),
    date(2023, 3, 17), date(2023, 6, 16), date(2023, 9, 15), date(2023, 12, 15),
    date(2024, 3, 15), date(2024, 6, 21), date(2024, 9, 20), date(2024, 12, 20),
    date(2025, 3, 21), date(2025, 6, 20), date(2025, 9, 19), date(2025, 12, 19),
    date(2026, 3, 20), date(2026, 6, 19), date(2026, 9, 18), date(2026, 12, 18),
})

_OPEX_FRIDAYS: frozenset[date] = frozenset({
    date(2022, 1, 21), date(2022, 2, 18), date(2022, 3, 18), date(2022, 4, 14),
    date(2022, 5, 20), date(2022, 6, 17), date(2022, 7, 15), date(2022, 8, 19),
    date(2022, 9, 16), date(2022, 10, 21), date(2022, 11, 18), date(2022, 12, 16),
    date(2023, 1, 20), date(2023, 2, 17), date(2023, 3, 17), date(2023, 4, 21),
    date(2023, 5, 19), date(2023, 6, 16), date(2023, 7, 21), date(2023, 8, 18),
    date(2023, 9, 15), date(2023, 10, 20), date(2023, 11, 17), date(2023, 12, 15),
    date(2024, 1, 19), date(2024, 2, 16), date(2024, 3, 15), date(2024, 4, 19),
    date(2024, 5, 17), date(2024, 6, 21), date(2024, 7, 19), date(2024, 8, 16),
    date(2024, 9, 20), date(2024, 10, 18), date(2024, 11, 15), date(2024, 12, 20),
    date(2025, 1, 17), date(2025, 2, 21), date(2025, 3, 21), date(2025, 4, 18),
    date(2025, 5, 16), date(2025, 6, 20), date(2025, 7, 18), date(2025, 8, 15),
    date(2025, 9, 19), date(2025, 10, 17), date(2025, 11, 21), date(2025, 12, 19),
    date(2026, 1, 16), date(2026, 2, 20), date(2026, 3, 20), date(2026, 4, 17),
    date(2026, 5, 15), date(2026, 6, 19), date(2026, 7, 17), date(2026, 8, 21),
    date(2026, 9, 18), date(2026, 10, 16), date(2026, 11, 20), date(2026, 12, 18),
})

# NYSE holidays that create 3-day weekends (Mon or Fri closures only)
_US_HOLIDAYS: frozenset[date] = frozenset({
    date(2022, 1, 17), date(2022, 2, 21), date(2022, 4, 15), date(2022, 5, 30),
    date(2022, 6, 20), date(2022, 7, 4), date(2022, 9, 5), date(2022, 11, 25),
    date(2022, 12, 26),
    date(2023, 1, 2), date(2023, 1, 16), date(2023, 2, 20), date(2023, 4, 7),
    date(2023, 5, 29), date(2023, 6, 19), date(2023, 7, 4), date(2023, 9, 4),
    date(2023, 11, 23), date(2023, 12, 25),
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4),
    date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
})


# ── Stats helpers ─────────────────────────────────────────────────────────────

def t_stat_1s(values: list[float]) -> tuple[float, str]:
    """One-sample t-stat vs H0: mean=0. Returns (t, sig_stars)."""
    n = len(values)
    if n < 4:
        return float("nan"), ""
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        t = float("inf") if mean > 0 else float("-inf")
    else:
        t = mean / (std / math.sqrt(n))
    at = abs(t)
    if at >= 3.29:
        sig = "***"
    elif at >= 2.576:
        sig = "**"
    elif at >= 1.96:
        sig = "*"
    else:
        sig = ""
    return t, sig


def bin_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Per-bin stats table (n, WR%, avg P/L, t-stat, sig, small-n flag)."""
    rows = []
    for lbl, grp in df.groupby(group_col, observed=True, sort=False):
        pl = grp["pl"].tolist()
        n = len(pl)
        wins = sum(1 for v in pl if v > 0)
        t, sig = t_stat_1s(pl)
        rows.append({
            "bin": lbl,
            "n": n,
            "wr_pct": 100.0 * wins / n if n else float("nan"),
            "avg_pl": sum(pl) / n if n else float("nan"),
            "total_pl": sum(pl),
            "t_stat": t,
            "sig": sig,
            "small_n": n < MIN_N,
        })
    return pd.DataFrame(rows).set_index("bin")


def print_table(stats: pd.DataFrame, split_label: str = "") -> None:
    label = f"  [{split_label}]" if split_label else ""
    hdr = f"  {'Bin':<22} {'n':>5} {'WR%':>7} {'Avg P/L':>9} {'Total':>8} {'t-stat':>8} {'sig':>4}"
    print(f"\n{label}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for lbl, row in stats.iterrows():
        flag = " !" if row["small_n"] else "  "
        t_str = f"{row['t_stat']:>8.2f}" if not math.isnan(row["t_stat"]) else "     n/a"
        print(
            f"{flag} {str(lbl):<22} {row['n']:>5} {row['wr_pct']:>6.1f}% "
            f"{row['avg_pl']:>+8.3f} {row['total_pl']:>+7.2f} {t_str} {row['sig']:>3}"
        )


def section(title: str) -> None:
    print(f"\n{'═'*65}")
    print(f"  {title}")
    print(f"{'═'*65}")


def subsection(title: str) -> None:
    print(f"\n  ── {title}")


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bt_sessions() -> list[dict]:
    with open(BT_CACHE) as f:
        return json.load(f)["trades"]


def fetch_market_data(rebuild: bool = False) -> pd.DataFrame:
    """Fetch or load VIX + GSPC daily OHLC. Cached to data/market_data_cache.json."""
    if not rebuild and MKT_CACHE.exists():
        print("  Using cached market data (--rebuild to refresh).")
        raw = json.loads(MKT_CACHE.read_text())
        df = pd.DataFrame(raw)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df.set_index("date").sort_index()

    print("  Fetching VIX + GSPC from yfinance...")
    import yfinance as yf

    start, end = "2021-05-01", "2026-06-30"
    vix = yf.download("^VIX", start=start, end=end, progress=False)
    gspc = yf.download("^GSPC", start=start, end=end, progress=False)

    # Flatten MultiIndex (yfinance 1.4 returns (Price, Ticker) columns)
    vix.columns = vix.columns.get_level_values(0)
    gspc.columns = gspc.columns.get_level_values(0)

    df = pd.DataFrame({
        "vix_close": vix["Close"],
        "spx_open": gspc["Open"],
        "spx_high": gspc["High"],
        "spx_low": gspc["Low"],
        "spx_close": gspc["Close"],
    }).dropna()

    df.index = pd.to_datetime(df.index).date
    df.index.name = "date"
    df = df.sort_index()

    cache_rows = df.reset_index()
    cache_rows["date"] = cache_rows["date"].astype(str)
    MKT_CACHE.write_text(json.dumps(cache_rows.to_dict(orient="records"), indent=2))
    print(f"  Cached {len(df)} trading days → {MKT_CACHE.name}")
    return df


def enrich_sessions(sessions: list[dict], mkt: pd.DataFrame) -> pd.DataFrame:
    """Merge BT sessions with VIX, GSPC, and calendar signals."""
    date_list = list(mkt.index)  # sorted
    date_to_idx = {d: i for i, d in enumerate(date_list)}
    vix_arr = mkt["vix_close"].to_numpy()
    spx_open_arr = mkt["spx_open"].to_numpy()
    spx_high_arr = mkt["spx_high"].to_numpy()
    spx_low_arr = mkt["spx_low"].to_numpy()
    spx_close_arr = mkt["spx_close"].to_numpy()

    rows = []
    skipped = 0
    for s in sessions:
        d = date.fromisoformat(s["date"])
        idx = date_to_idx.get(d)
        if idx is None:
            skipped += 1
            continue

        vix_today = float(vix_arr[idx])

        # VIX IVR 52w: (today - min_past252) / (max_past252 - min_past252)
        lk_start = max(0, idx - 252)
        lk_vix = vix_arr[lk_start:idx]
        if len(lk_vix) > 0:
            vmin, vmax = float(lk_vix.min()), float(lk_vix.max())
            ivr_52w = (vix_today - vmin) / (vmax - vmin) if vmax > vmin else 0.5
        else:
            ivr_52w = 0.5

        # VIX bin
        if vix_today < 15:
            vix_bin = "1. VIX<15"
        elif vix_today < 20:
            vix_bin = "2. VIX 15-20"
        elif vix_today < 25:
            vix_bin = "3. VIX 20-25"
        elif vix_today < 30:
            vix_bin = "4. VIX 25-30"
        else:
            vix_bin = "5. VIX>30"

        # IVR bin
        if ivr_52w < 0.20:
            ivr_bin = "1. IVR<20%"
        elif ivr_52w < 0.35:
            ivr_bin = "2. IVR 20-35%"
        elif ivr_52w < 0.50:
            ivr_bin = "3. IVR 35-50%"
        else:
            ivr_bin = "4. IVR>50%"

        # Previous-day OHLC signals (requires at least one prior row)
        if idx > 0:
            prev_high = float(spx_high_arr[idx - 1])
            prev_low = float(spx_low_arr[idx - 1])
            prev_close = float(spx_close_arr[idx - 1])
            prev_open_p = float(spx_open_arr[idx - 1])
            today_open = float(spx_open_arr[idx])

            prev_range = prev_high - prev_low
            prev_return_pct = (prev_close / prev_open_p - 1) * 100 if prev_open_p > 0 else 0.0
            gap_pct = (today_open / prev_close - 1) * 100 if prev_close > 0 else 0.0

            # Open vs prev range
            if today_open > prev_high:
                open_vs_range = "gap_up"
            elif today_open < prev_low:
                open_vs_range = "gap_down"
            else:
                open_vs_range = "inside"

            # Prev range ratio vs 20-day avg
            rng_lk = max(0, idx - 20)
            rng_window = spx_high_arr[rng_lk:idx] - spx_low_arr[rng_lk:idx]
            avg_range_20d = float(rng_window.mean()) if len(rng_window) > 0 else prev_range
            prev_range_ratio = prev_range / avg_range_20d if avg_range_20d > 0 else 1.0

            # Range ratio bin
            if prev_range_ratio < 0.75:
                range_bin = "1. Small (<0.75x avg)"
            elif prev_range_ratio < 1.25:
                range_bin = "2. Normal (0.75-1.25x)"
            elif prev_range_ratio < 2.0:
                range_bin = "3. Large (1.25-2.0x)"
            else:
                range_bin = "4. Very Large (>2.0x)"

            # Gap size bin
            ag = abs(gap_pct)
            if ag < 0.2:
                gap_bin = "1. Micro (<0.2%)"
            elif ag < 0.5:
                gap_bin = "2. Small (0.2-0.5%)"
            elif ag < 1.0:
                gap_bin = "3. Medium (0.5-1.0%)"
            else:
                gap_bin = "4. Large (>1.0%)"

            # Prev return sanity-check bin (directional)
            if prev_return_pct < -0.5:
                prev_ret_bin = "1. Down (< -0.5%)"
            elif prev_return_pct < 0.5:
                prev_ret_bin = "2. Flat (-0.5% to +0.5%)"
            else:
                prev_ret_bin = "3. Up (> +0.5%)"
        else:
            prev_range = prev_return_pct = gap_pct = prev_range_ratio = None
            open_vs_range = range_bin = gap_bin = prev_ret_bin = None

        # Calendar flags
        is_fomc = d in _FOMC_ALL
        is_triple = d in _TRIPLE_WITCHING
        is_opex = (d in _OPEX_FRIDAYS) and not is_triple

        # Day of week
        dow = d.strftime("%A")
        dow_bin = f"{d.weekday() + 1}. {dow}"

        # Post-3-day-weekend (Monday after a Friday or Monday holiday)
        is_post_long = False
        if d.weekday() == 0:  # Monday
            prior_fri = d - timedelta(days=3)
            prior_mon = d - timedelta(days=7)
            if prior_fri in _US_HOLIDAYS or prior_mon in _US_HOLIDAYS:
                is_post_long = True

        rows.append({
            **s,
            "date": d,
            "vix": vix_today,
            "ivr_52w": ivr_52w,
            "vix_bin": vix_bin,
            "ivr_bin": ivr_bin,
            "open_vs_range": open_vs_range,
            "gap_pct": gap_pct,
            "gap_bin": gap_bin,
            "prev_range_ratio": prev_range_ratio,
            "range_bin": range_bin,
            "prev_return_pct": prev_return_pct,
            "prev_ret_bin": prev_ret_bin,
            "is_fomc": is_fomc,
            "is_triple_witching": is_triple,
            "is_opex": is_opex,
            "dow": dow,
            "dow_bin": dow_bin,
            "is_post_long_wknd": is_post_long,
        })

    if skipped:
        print(f"  Warning: {skipped} BT sessions had no market data match.")

    df = pd.DataFrame(rows)
    df["split"] = df["date"].apply(
        lambda d: "discovery" if d <= DISCOVERY_END else "validation"
    )
    return df.sort_values("date").reset_index(drop=True)


# ── Research 1: VIX Regime ────────────────────────────────────────────────────

def research_1_vix(df: pd.DataFrame) -> dict:
    section("RESEARCH 1: VIX Regime")
    print("""
  Hypothesis: P/L peaks in mid-VIX (20-25). Very low VIX (<15) → less
  credit → lower returns. Very high VIX (>30) → elevated realized vol eats
  through the buffer despite larger credits.
  Secondary: after controlling for credit size, does VIX still explain residual variance?""")

    results: dict[str, Any] = {}

    subsection("VIX Bins — Full period (1,020 sessions)")
    vix_all = bin_stats(df, "vix_bin")
    print_table(vix_all, "All sessions")
    results["vix_full"] = vix_all.reset_index().to_dict(orient="records")

    disc = df[df["split"] == "discovery"]
    val = df[df["split"] == "validation"]
    vix_disc = bin_stats(disc, "vix_bin")
    vix_val = bin_stats(val, "vix_bin")
    print_table(vix_disc, f"Discovery 2022-2024 (n={len(disc)})")
    print_table(vix_val, f"Validation 2025-2026 (n={len(val)})")
    results["vix_discovery"] = vix_disc.reset_index().to_dict(orient="records")
    results["vix_validation"] = vix_val.reset_index().to_dict(orient="records")

    subsection("IVR 52-week Bins — Full period")
    ivr_all = bin_stats(df, "ivr_bin")
    print_table(ivr_all, "All sessions")
    ivr_disc = bin_stats(disc, "ivr_bin")
    ivr_val = bin_stats(val, "ivr_bin")
    print_table(ivr_disc, f"Discovery (n={len(disc)})")
    print_table(ivr_val, f"Validation (n={len(val)})")
    results["ivr_full"] = ivr_all.reset_index().to_dict(orient="records")
    results["ivr_discovery"] = ivr_disc.reset_index().to_dict(orient="records")
    results["ivr_validation"] = ivr_val.reset_index().to_dict(orient="records")

    subsection("Credit-controlled residual: P/L normalized by credit")
    df2 = df[df["credit"] > 0].copy()
    df2["pl_per_credit"] = df2["pl"] / df2["credit"]
    rows_cc = []
    for lbl, grp in df2.groupby("vix_bin", observed=True, sort=False):
        pl_norm = grp["pl_per_credit"].tolist()
        n = len(pl_norm)
        t, sig = t_stat_1s(pl_norm)
        rows_cc.append({
            "bin": lbl, "n": n,
            "avg_pl_per_credit": sum(pl_norm) / n if n else float("nan"),
            "t_stat": t, "sig": sig, "small_n": n < MIN_N,
        })
    cc_df = pd.DataFrame(rows_cc).set_index("bin")
    hdr2 = f"  {'Bin':<22} {'n':>5} {'P/L per Credit':>16} {'t-stat':>8} {'sig':>4}"
    print(f"\n  [Credit-normalized P/L (shows structural edge, not just credit-size effect)]")
    print(hdr2)
    print("  " + "-" * (len(hdr2) - 2))
    for lbl, row in cc_df.iterrows():
        flag = " !" if row["small_n"] else "  "
        t_str = f"{row['t_stat']:>8.2f}" if not math.isnan(row["t_stat"]) else "     n/a"
        print(
            f"{flag} {str(lbl):<22} {row['n']:>5} "
            f"{row['avg_pl_per_credit']:>+14.4f} {t_str} {row['sig']:>3}"
        )
    results["vix_credit_normalized"] = cc_df.reset_index().to_dict(orient="records")

    return results


# ── Research 2: Previous Day OHLC ─────────────────────────────────────────────

def research_2_ohlc(df: pd.DataFrame) -> dict:
    section("RESEARCH 2: Previous Day OHLC Signals")
    print("""
  Hypothesis: Iron fly profits when SPX stays rangebound. An inside-range
  open signals consolidation → higher containment probability. Large gap
  openings signal momentum/volatility spillover → IF underperforms.
  Note: 2c (prev direction) is a sanity check — should show NO predictive
  power for delta-neutral IF; if it does, that's a data-mining red flag.""")

    df_ohlc = df.dropna(subset=["open_vs_range"]).copy()
    disc = df_ohlc[df_ohlc["split"] == "discovery"]
    val = df_ohlc[df_ohlc["split"] == "validation"]
    results: dict[str, Any] = {}

    subsection("2a: Open position vs yesterday's range")
    s = bin_stats(df_ohlc, "open_vs_range")
    print_table(s, f"All (n={len(df_ohlc)})")
    print_table(bin_stats(disc, "open_vs_range"), f"Discovery (n={len(disc)})")
    print_table(bin_stats(val, "open_vs_range"), f"Validation (n={len(val)})")
    results["open_vs_range_full"] = s.reset_index().to_dict(orient="records")

    subsection("2b: Yesterday's range size (vs 20-day avg)")
    df_rb = df_ohlc.dropna(subset=["range_bin"])
    s2 = bin_stats(df_rb, "range_bin")
    print_table(s2, f"All (n={len(df_rb)})")
    print_table(bin_stats(df_rb[df_rb["split"] == "discovery"], "range_bin"),
                f"Discovery (n={len(df_rb[df_rb['split']=='discovery'])})")
    print_table(bin_stats(df_rb[df_rb["split"] == "validation"], "range_bin"),
                f"Validation (n={len(df_rb[df_rb['split']=='validation'])})")
    results["range_bin_full"] = s2.reset_index().to_dict(orient="records")

    subsection("2c: Yesterday's directional return (sanity check — expect no signal)")
    df_pret = df_ohlc.dropna(subset=["prev_ret_bin"])
    s3 = bin_stats(df_pret, "prev_ret_bin")
    print_table(s3, f"All (n={len(df_pret)})")
    results["prev_ret_full"] = s3.reset_index().to_dict(orient="records")
    # Flag if direction matters more than it should
    pls_by_dir = {lbl: grp["pl"].mean() for lbl, grp in df_pret.groupby("prev_ret_bin", observed=True)}
    direction_range = max(pls_by_dir.values()) - min(pls_by_dir.values()) if pls_by_dir else 0
    if direction_range > 0.15:
        print(f"\n  ⚠ WARNING: avg P/L spread by prev direction = ${direction_range:.3f}/trade "
              f"(>{0.15:.2f} threshold). Possible data-mining artefact — investigate before trading.")
    else:
        print(f"\n  ✓ Prev direction range ${direction_range:.3f}/trade — no meaningful predictive power (as expected).")

    subsection("2d: Overnight gap size")
    df_gap = df_ohlc.dropna(subset=["gap_bin"])
    s4 = bin_stats(df_gap, "gap_bin")
    print_table(s4, f"All (n={len(df_gap)})")
    print_table(bin_stats(df_gap[df_gap["split"] == "discovery"], "gap_bin"),
                f"Discovery (n={len(df_gap[df_gap['split']=='discovery'])})")
    print_table(bin_stats(df_gap[df_gap["split"] == "validation"], "gap_bin"),
                f"Validation (n={len(df_gap[df_gap['split']=='validation'])})")
    results["gap_bin_full"] = s4.reset_index().to_dict(orient="records")

    return results


# ── Research 3: Calendar / News Days ──────────────────────────────────────────

def research_3_calendar(df: pd.DataFrame) -> dict:
    section("RESEARCH 3: Calendar / News Day Effects")
    print("""
  Competing effects: pre-announcement IV inflation (more credit, good) vs
  post-announcement binary move through wings (bad). FOMC announces at
  2:00pm ET — after our 10:00am entry, but before the 1:00pm time-stop.
  Key question: does the vol premium compensate for the binary move risk?""")

    results: dict[str, Any] = {}
    disc = df[df["split"] == "discovery"]
    val = df[df["split"] == "validation"]

    def _compare(mask_col: str, label: str, note: str = "") -> dict:
        subsection(f"{label}{' — ' + note if note else ''}")
        df["_grp"] = df[mask_col].map({True: f"1. {label}", False: "2. Non-{label}"})
        disc["_grp"] = disc[mask_col].map({True: f"1. {label}", False: f"2. Non-{label}"})
        val["_grp"] = val[mask_col].map({True: f"1. {label}", False: f"2. Non-{label}"})
        s = bin_stats(df, "_grp")
        print_table(s, f"All")
        print_table(bin_stats(disc, "_grp"), f"Discovery")
        print_table(bin_stats(val, "_grp"), f"Validation")
        return s.reset_index().to_dict(orient="records")

    # FOMC
    df = df.copy(); disc = disc.copy(); val = val.copy()
    df["_grp_fomc"] = df["is_fomc"].map({True: "1. FOMC day", False: "2. Non-FOMC"})
    disc["_grp_fomc"] = disc["is_fomc"].map({True: "1. FOMC day", False: "2. Non-FOMC"})
    val["_grp_fomc"] = val["is_fomc"].map({True: "1. FOMC day", False: "2. Non-FOMC"})

    subsection("3a: FOMC announcement days (2pm ET, within hold window)")
    s_fomc = bin_stats(df, "_grp_fomc")
    n_fomc = df["is_fomc"].sum()
    print(f"  ({n_fomc} FOMC sessions in BT period)")
    print_table(s_fomc, "All")
    print_table(bin_stats(disc, "_grp_fomc"), f"Discovery")
    print_table(bin_stats(val, "_grp_fomc"), f"Validation")
    results["fomc"] = s_fomc.reset_index().to_dict(orient="records")

    # Triple witching
    df["_grp_tw"] = df["is_triple_witching"].map({True: "1. Triple Witching", False: "2. Normal"})
    disc["_grp_tw"] = disc["is_triple_witching"].map({True: "1. Triple Witching", False: "2. Normal"})
    val["_grp_tw"] = val["is_triple_witching"].map({True: "1. Triple Witching", False: "2. Normal"})
    subsection("3b: Triple Witching (quarterly — Mar/Jun/Sep/Dec 3rd Friday)")
    n_tw = df["is_triple_witching"].sum()
    print(f"  ({n_tw} triple witching sessions in BT period)")
    s_tw = bin_stats(df, "_grp_tw")
    print_table(s_tw, "All")
    print_table(bin_stats(disc, "_grp_tw"), "Discovery")
    print_table(bin_stats(val, "_grp_tw"), "Validation")
    results["triple_witching"] = s_tw.reset_index().to_dict(orient="records")

    # Monthly OpEx (non-triple)
    df["_grp_opex"] = df["is_opex"].map({True: "1. OpEx Friday", False: "2. Normal"})
    disc["_grp_opex"] = disc["is_opex"].map({True: "1. OpEx Friday", False: "2. Normal"})
    val["_grp_opex"] = val["is_opex"].map({True: "1. OpEx Friday", False: "2. Normal"})
    subsection("3c: Monthly OpEx Fridays (3rd Friday, not triple-witching)")
    n_opex = df["is_opex"].sum()
    print(f"  ({n_opex} regular OpEx sessions in BT period)")
    s_opex = bin_stats(df, "_grp_opex")
    print_table(s_opex, "All")
    print_table(bin_stats(disc, "_grp_opex"), "Discovery")
    print_table(bin_stats(val, "_grp_opex"), "Validation")
    results["opex"] = s_opex.reset_index().to_dict(orient="records")

    return results


# ── Research 4: Day of Week ────────────────────────────────────────────────────

def research_4_dow(df: pd.DataFrame) -> dict:
    section("RESEARCH 4: Day of Week Effects")
    print("""
  Hypothesis: Mon post-3-day-weekend may gap more (3 days of news). Friday
  PM settlement gamma is higher → amplifies directional moves either way.
  Note: SPXW 0DTE cash-settles at close — no pin risk, but gamma spikes
  significantly in the last hour on any expiry Friday.""")

    results: dict[str, Any] = {}
    disc = df[df["split"] == "discovery"]
    val = df[df["split"] == "validation"]

    subsection("4a: All trading days by day of week")
    s = bin_stats(df, "dow_bin")
    print_table(s, f"All (n={len(df)})")
    print_table(bin_stats(disc, "dow_bin"), f"Discovery (n={len(disc)})")
    print_table(bin_stats(val, "dow_bin"), f"Validation (n={len(val)})")
    results["dow_full"] = s.reset_index().to_dict(orient="records")

    subsection("4b: Post-3-day-weekend Mondays vs regular Mondays vs other days")
    mondays = df[df["dow"] == "Monday"].copy()
    mondays["_mon_type"] = mondays["is_post_long_wknd"].map(
        {True: "1. Post-long-wknd Mon", False: "2. Regular Monday"}
    )
    n_long = mondays["is_post_long_wknd"].sum()
    print(f"  ({n_long} post-long-weekend Mondays in BT period)")
    if n_long >= 4:
        s_mon = bin_stats(mondays, "_mon_type")
        print_table(s_mon, f"Mondays only (n={len(mondays)})")
        results["monday_type"] = s_mon.reset_index().to_dict(orient="records")
    else:
        print("  Insufficient post-long-weekend Monday samples.")
        results["monday_type"] = []

    subsection("4c: Fridays — regular vs OpEx vs triple-witching")
    fridays = df[df["dow"] == "Friday"].copy()
    def _fri_type(row):
        if row["is_triple_witching"]:
            return "1. Triple Witching Fri"
        if row["is_opex"]:
            return "2. OpEx Friday"
        return "3. Regular Friday"
    fridays["_fri_type"] = fridays.apply(_fri_type, axis=1)
    s_fri = bin_stats(fridays, "_fri_type")
    print_table(s_fri, f"Fridays only (n={len(fridays)})")
    results["friday_type"] = s_fri.reset_index().to_dict(orient="records")

    return results


# ── Research 5: Volatility Regime Persistence ─────────────────────────────────

def research_5_autocorr(df: pd.DataFrame) -> dict:
    section("RESEARCH 5: Volatility Regime Persistence / Autocorrelation")
    print("""
  Hypothesis: If outcomes cluster (consecutive wins or losses), position sizing
  could exploit momentum; if they alternate, sizing is irrelevant.
  Key metrics: lag-1 autocorrelation, runs test z-stat, conditional win rate.""")

    pl_all = df["pl"].to_numpy()
    pl_disc = df[df["split"] == "discovery"]["pl"].to_numpy()
    pl_val = df[df["split"] == "validation"]["pl"].to_numpy()
    results: dict[str, Any] = {}

    def _analyze(pl: np.ndarray, label: str) -> dict:
        n = len(pl)
        if n < 10:
            print(f"  {label}: insufficient data (n={n})")
            return {}

        # Lag-1 autocorrelation
        lag1 = float(np.corrcoef(pl[:-1], pl[1:])[0, 1])

        # Runs test
        wins_mask = (pl > 0)
        n1 = int(wins_mask.sum())
        n2 = n - n1
        runs = 1
        for i in range(1, n):
            if wins_mask[i] != wins_mask[i - 1]:
                runs += 1
        if n1 > 0 and n2 > 0:
            exp_runs = (2 * n1 * n2) / n + 1
            var_runs = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n ** 2 * (n - 1))
            z_runs = (runs - exp_runs) / math.sqrt(var_runs) if var_runs > 0 else float("nan")
        else:
            z_runs = float("nan")

        # Conditional WR
        prev_win = wins_mask[:-1]
        this_win = wins_mask[1:]
        wr_after_win = float(this_win[prev_win].mean()) * 100 if prev_win.sum() > 0 else float("nan")
        wr_after_loss = float(this_win[~prev_win].mean()) * 100 if (~prev_win).sum() > 0 else float("nan")

        # Max consecutive wins/losses
        max_w = max_l = cur_w = cur_l = 0
        for v in pl:
            if v > 0:
                cur_w += 1; cur_l = 0
                max_w = max(max_w, cur_w)
            else:
                cur_l += 1; cur_w = 0
                max_l = max(max_l, cur_l)

        print(f"\n  [{label}] n={n}")
        print(f"    Lag-1 autocorrelation : {lag1:+.4f}  "
              f"({'positive cluster' if lag1 > 0.05 else 'negative cluster (mean-reversion)' if lag1 < -0.05 else 'near-zero (independent)'})")
        print(f"    Runs test z-stat       : {z_runs:+.3f}  "
              f"({'clustering z<-1.96 ⚠' if not math.isnan(z_runs) and z_runs < -1.96 else 'alternating z>+1.96' if not math.isnan(z_runs) and z_runs > 1.96 else 'random (no structure)'})")
        print(f"    WR after win           : {wr_after_win:.1f}%  (vs overall {100*n1/n:.1f}%)")
        print(f"    WR after loss          : {wr_after_loss:.1f}%")
        print(f"    Max consecutive wins   : {max_w}")
        print(f"    Max consecutive losses : {max_l}")

        return {
            "n": n, "lag1_autocorr": lag1, "runs_z": z_runs,
            "wr_after_win": wr_after_win, "wr_after_loss": wr_after_loss,
            "max_win_streak": max_w, "max_loss_streak": max_l,
        }

    results["all"] = _analyze(pl_all, "Full period")
    results["discovery"] = _analyze(pl_disc, "Discovery 2022-2024")
    results["validation"] = _analyze(pl_val, "Validation 2025-2026")

    # Monthly autocorrelation — do winning months predict losing months?
    subsection("Monthly P/L autocorrelation (regime persistence at monthly scale)")
    df2 = df.copy()
    df2["ym"] = df2["date"].apply(lambda d: d.strftime("%Y-%m"))
    monthly = df2.groupby("ym")["pl"].sum().to_numpy()
    if len(monthly) >= 6:
        lag1_m = float(np.corrcoef(monthly[:-1], monthly[1:])[0, 1])
        print(f"  Monthly lag-1 autocorr: {lag1_m:+.4f}  "
              f"({'positive — good months beget good months' if lag1_m > 0.15 else 'negative — reverting' if lag1_m < -0.15 else 'near-zero'})")
        results["monthly_lag1"] = lag1_m

    return results


# ── JSON export ───────────────────────────────────────────────────────────────

def export_json(df: pd.DataFrame, research: dict) -> None:
    out = {
        "generated": str(date.today()),
        "total_sessions": len(df),
        "discovery_sessions": int((df["split"] == "discovery").sum()),
        "validation_sessions": int((df["split"] == "validation").sum()),
        "discovery_end": str(DISCOVERY_END),
        "research": research,
    }
    # Add summary stats
    out["overall"] = {
        "total_pl": float(df["pl"].sum()),
        "avg_pl": float(df["pl"].mean()),
        "wr_pct": float((df["pl"] > 0).mean() * 100),
        "n": len(df),
    }

    # Serializable versions of any date objects in enriched df
    def _serial(o):
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, float) and math.isnan(o):
            return None
        if hasattr(o, "item"):
            return o.item()
        raise TypeError(f"Not serializable: {type(o)}")

    ENRICHED_OUT.write_text(json.dumps(out, indent=2, default=_serial))
    print(f"\n  Enriched data saved → {ENRICHED_OUT.relative_to(ROOT)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="V1 enrichment analysis")
    parser.add_argument("--rebuild", action="store_true", help="Re-fetch market data from yfinance")
    parser.add_argument("--track", type=int, choices=[1, 2, 3, 4, 5],
                        help="Run only a specific research track (1-5)")
    args = parser.parse_args()

    print(f"\n{'═'*65}")
    print("  Iron Fly V1 — Enrichment Research Analysis")
    print(f"{'═'*65}")

    print("\nLoading BT sessions...")
    sessions = load_bt_sessions()
    print(f"  {len(sessions)} sessions from {sessions[0]['date']} to {sessions[-1]['date']}")

    print("\nFetching market data...")
    mkt = fetch_market_data(rebuild=args.rebuild)
    print(f"  Market data: {len(mkt)} trading days")

    print("\nEnriching sessions with signals...")
    df = enrich_sessions(sessions, mkt)
    disc_n = (df["split"] == "discovery").sum()
    val_n = (df["split"] == "validation").sum()
    print(f"  {len(df)} enriched sessions  |  Discovery: {disc_n}  |  Validation: {val_n}")

    overall_t, overall_sig = t_stat_1s(df["pl"].tolist())
    print(f"\n  Overall: avg P/L=${df['pl'].mean():+.4f}  WR={100*(df['pl']>0).mean():.1f}%  "
          f"t={overall_t:.2f}{overall_sig}  total=${df['pl'].sum():+.2f}")

    research: dict[str, Any] = {}

    tracks = [args.track] if args.track else [1, 2, 3, 4, 5]

    if 1 in tracks:
        research["r1_vix"] = research_1_vix(df)
    if 2 in tracks:
        research["r2_ohlc"] = research_2_ohlc(df)
    if 3 in tracks:
        research["r3_calendar"] = research_3_calendar(df)
    if 4 in tracks:
        research["r4_dow"] = research_4_dow(df)
    if 5 in tracks:
        research["r5_autocorr"] = research_5_autocorr(df)

    section("FINDINGS SUMMARY")
    print("""
  Key to read:
    * p<0.05  ** p<0.01  *** p<0.001  (large-sample approximation, two-tailed)
    !  bin has n < 30 — treat as directional indicator only, not a trading rule

  Anti-overfitting check: a finding is actionable only if:
    1. It held directionally in BOTH discovery AND validation
    2. t-stat >= 1.96 in at least one period with n >= 30
    3. There is a stated causal mechanism (see research plan)
    4. The signal was not cherry-picked post-hoc
    """)

    export_json(df, research)

    print(f"\n{'═'*65}\n")


if __name__ == "__main__":
    main()
