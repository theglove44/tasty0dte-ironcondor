#!/usr/bin/env python3
"""
7DTE Put Credit Spread Backtest

Entry: Every Monday at 10:00 ET
Legs: Short 30-delta put, Long (short_strike - 5), both 7 calendar days out
Entry credit: Black-Scholes with VIX × 1.15 skew adjustment
TP: 50% of entry credit, checked daily at 10:00 ET
Settlement: Actual put mids at last timestamp on expiry Monday if no TP
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from scipy.stats import norm
import yfinance as yf
import warnings
import sys

warnings.filterwarnings('ignore')

# --- constants ---
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_paths import BACKTEST_DATA_DIR  # noqa: E402
DATA_DIR = BACKTEST_DATA_DIR
OUTPUT_CSV = DATA_DIR.parent / 'put_cs_7dte_backtest.csv'
RISK_FREE = 0.05
VOL_SCALE = 1.15  # VIX × this for put skew adjustment
DELTA_TARGET = -0.30
SPREAD_WIDTH = 5
TP_PCT = 0.50
ENTRY_HOUR = 10
ENTRY_MIN = 0


def parse_strike(symbol: str) -> float:
    """Extract strike from OCC-style symbol string.

    Format: "SPXW  YYMMDDP/C<strike>"
    Strike is at positions 13-20 (8 digits, strike × 1000)
    """
    return int(symbol[13:21]) / 1000.0


def parse_option_type(symbol: str) -> str:
    """Extract C or P from OCC-style symbol (position 12)."""
    return symbol[12]


def get_spx_spot(df: pd.DataFrame, target_hour: int, target_min: int) -> float:
    """
    Estimate SPX spot from put-call parity at the given time.

    Filter to rows within ±1 minute of target_hour:target_min (America/New_York).
    For each strike where both a call and a put exist at that timestamp,
    compute F = K + C_mid - P_mid.
    Return the median F across all such pairs (robust to outliers).
    Return np.nan if fewer than 3 pairs found.
    """
    if df.empty:
        return np.nan

    # Convert ts_et to time and find rows within ±1 min of target
    df_work = df.copy()
    df_work['hour'] = df_work['ts_et'].dt.hour
    df_work['minute'] = df_work['ts_et'].dt.minute
    target_sec_start = target_hour * 3600 + (target_min - 1) * 60
    target_sec_end = target_hour * 3600 + (target_min + 1) * 60
    df_work['time_sec'] = df_work['hour'] * 3600 + df_work['minute'] * 60

    filtered = df_work[(df_work['time_sec'] >= target_sec_start) &
                       (df_work['time_sec'] <= target_sec_end)].copy()

    if filtered.empty:
        return np.nan

    # Parse option type and strike
    filtered['option_type'] = filtered['symbol'].apply(parse_option_type)
    filtered['strike'] = filtered['symbol'].apply(parse_strike)

    # Find matching C/P pairs at each timestamp
    for ts in filtered['ts_et'].unique():
        ts_data = filtered[filtered['ts_et'] == ts]

        calls = ts_data[ts_data['option_type'] == 'C'].set_index('strike')
        puts = ts_data[ts_data['option_type'] == 'P'].set_index('strike')

        common_strikes = calls.index.intersection(puts.index)
        if len(common_strikes) >= 3:
            # Compute F = K + C_mid - P_mid for each pair
            F_values = []
            for K in common_strikes:
                # Handle both Series and scalar returns from .loc[]
                C_val = calls.loc[K, 'mid']
                P_val = puts.loc[K, 'mid']
                # If it's a Series (multiple rows), take the first; else it's a scalar
                if hasattr(C_val, 'iloc'):
                    C_mid = float(C_val.iloc[0])
                else:
                    C_mid = float(C_val)
                if hasattr(P_val, 'iloc'):
                    P_mid = float(P_val.iloc[0])
                else:
                    P_mid = float(P_val)
                F = K + C_mid - P_mid
                F_values.append(F)

            if F_values:
                return np.median(F_values)

    return np.nan


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Standard Black-Scholes European put price.

    Returns intrinsic value if T <= 0 or sigma <= 0.
    """
    if T <= 0:
        return max(K - S, 0.0)

    if sigma <= 0:
        return max(K - S, 0.0)

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return max(put_price, 0.0)


def bs_put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """BS put delta (negative, e.g. -0.30).

    Returns -1.0 if T <= 0 and K > S, else 0.0.
    """
    if T <= 0:
        return -1.0 if K > S else 0.0

    if sigma <= 0:
        return -1.0 if K > S else 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    delta = -norm.cdf(-d1)
    return delta


def find_30delta_put(S: float, T: float, r: float, sigma: float,
                     strike_step: int = 5) -> int:
    """Scan strikes from S-200 to S (5-pt steps, on-grid) and return the
    strike whose BS put delta is closest to -0.30. Returns None if S is nan.
    """
    if np.isnan(S):
        return None

    target_delta = -0.30
    best_strike = None
    best_diff = float('inf')

    # Snap to the 5-pt grid so strikes match those in the parquet files
    grid_start = int((S - 200) // strike_step) * strike_step
    grid_end = int(S // strike_step) * strike_step + strike_step

    for strike in range(grid_start, grid_end + 1, strike_step):
        if strike <= 0:
            continue
        delta = bs_put_delta(S, float(strike), T, r, sigma)
        diff = abs(delta - target_delta)
        if diff < best_diff:
            best_diff = diff
            best_strike = strike

    return best_strike


def load_parquet(date_obj: datetime) -> pd.DataFrame:
    """Load parquet for a given date."""
    year_dir = DATA_DIR / str(date_obj.year)
    parquet_path = year_dir / f"{date_obj.strftime('%Y-%m-%d')}.parquet"

    if not parquet_path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(parquet_path)
    if 'ts_et' in df.columns:
        df['ts_et'] = pd.to_datetime(df['ts_et'])
    return df


def main():
    print("=== 7DTE Put Credit Spread Backtest ===\n")

    # --- Load VIX data ---
    print("Downloading VIX data...")
    vix_df = yf.download("^VIX", start="2022-01-01", auto_adjust=True, progress=False)
    # yfinance returns multi-level columns; extract Close for ^VIX
    vix_dict = {}
    for dt_idx, row in vix_df.iterrows():
        try:
            date_key = pd.Timestamp(dt_idx).date()
            # Handle multi-level columns from yfinance
            if ('Close', '^VIX') in vix_df.columns:
                close_val = row[('Close', '^VIX')]
            elif 'Close' in vix_df.columns:
                close_val = row['Close']
            else:
                continue
            if pd.notna(close_val):
                vix_dict[date_key] = close_val
        except (TypeError, ValueError, KeyError):
            continue
    if vix_dict:
        print(f"VIX data loaded: {min(vix_dict.keys())} to {max(vix_dict.keys())}\n")
    else:
        print("Error: no VIX data loaded\n")
        return

    # --- Find all available dates ---
    print("Scanning data directory...")
    available_dates = set()
    for year_dir in DATA_DIR.glob('*'):
        if year_dir.is_dir():
            for parquet_file in year_dir.glob('*.parquet'):
                date_str = parquet_file.stem
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    available_dates.add(date_obj)
                except ValueError:
                    pass

    available_dates_set = set(available_dates)
    available_dates = sorted(available_dates_set)
    print(f"Found {len(available_dates)} parquet files\n")

    if not available_dates:
        print("No parquet files found.")
        return

    # --- Backtest loop ---
    trades = []

    # Generate all possible Mondays in the dataset
    min_date = min(available_dates)
    max_date = max(available_dates)
    current_monday = min_date
    # Adjust to nearest Monday
    while current_monday.weekday() != 0:
        current_monday += timedelta(days=1)

    print("Running backtest...")

    while current_monday <= max_date:
        entry_monday = current_monday
        expiry_monday = entry_monday + timedelta(days=7)

        # Check if we have data for both entry and expiry
        if entry_monday not in available_dates_set or expiry_monday not in available_dates_set:
            current_monday += timedelta(days=7)
            continue

        # --- ENTRY ---
        entry_df = load_parquet(datetime.combine(entry_monday, datetime.min.time()))
        S_entry = get_spx_spot(entry_df, ENTRY_HOUR, ENTRY_MIN)
        if np.isnan(S_entry):
            current_monday += timedelta(days=7)
            continue

        # Use prior-day VIX close to avoid lookahead bias
        prior_day = entry_monday - timedelta(days=1)
        while prior_day not in vix_dict and prior_day >= min_date:
            prior_day -= timedelta(days=1)
        if prior_day not in vix_dict:
            current_monday += timedelta(days=7)
            continue

        vix_entry = vix_dict[prior_day]
        if np.isnan(vix_entry) or vix_entry <= 0:
            current_monday += timedelta(days=7)
            continue

        sigma = (vix_entry / 100.0) * VOL_SCALE
        T_entry = 7 / 365.0

        short_strike = find_30delta_put(S_entry, T_entry, RISK_FREE, sigma)
        if short_strike is None:
            current_monday += timedelta(days=7)
            continue

        long_strike = short_strike - SPREAD_WIDTH
        if long_strike <= 0:
            current_monday += timedelta(days=7)
            continue

        # Entry credit via BS
        entry_credit = (bs_put_price(S_entry, float(short_strike), T_entry, RISK_FREE, sigma)
                       - bs_put_price(S_entry, float(long_strike), T_entry, RISK_FREE, sigma))

        if entry_credit <= 0.01:
            current_monday += timedelta(days=7)
            continue

        tp_target = entry_credit * TP_PCT

        # --- MONITORING ---
        exit_type = None
        exit_date = None
        exit_debit = None
        days_held = 0

        # Build monitoring dates: entries after entry_monday through expiry_monday
        monitoring_dates = []
        check_date = entry_monday + timedelta(days=1)
        while check_date <= expiry_monday:
            if check_date in available_dates:
                monitoring_dates.append(check_date)
            check_date += timedelta(days=1)

        # Intraweek TP monitoring only (exclude expiry_monday — handled separately)
        intraweek_dates = [d for d in monitoring_dates if d < expiry_monday]
        for check_date in intraweek_dates:
            check_df = load_parquet(datetime.combine(check_date, datetime.min.time()))
            S_check = get_spx_spot(check_df, ENTRY_HOUR, ENTRY_MIN)
            if np.isnan(S_check):
                continue

            days_held = (check_date - entry_monday).days
            T_check = max((expiry_monday - check_date).days / 365.0, 1e-6)

            prior_check = check_date - timedelta(days=1)
            while prior_check not in vix_dict and prior_check >= min_date:
                prior_check -= timedelta(days=1)
            vix_check = vix_dict.get(prior_check, vix_entry)
            if np.isnan(vix_check) or vix_check <= 0:
                vix_check = vix_entry
            sigma_check = (vix_check / 100.0) * VOL_SCALE

            current_debit = (bs_put_price(S_check, float(short_strike), T_check, RISK_FREE, sigma_check)
                           - bs_put_price(S_check, float(long_strike), T_check, RISK_FREE, sigma_check))

            if current_debit <= tp_target:
                exit_type = "TP"
                exit_date = check_date
                exit_debit = current_debit
                break

        # No intraweek TP — use actual put prices at last timestamp on expiry Monday
        if exit_type is None and expiry_monday in available_dates:
            expiry_df = load_parquet(datetime.combine(expiry_monday, datetime.min.time()))

            if not expiry_df.empty:
                last_ts = expiry_df['ts_et'].max()
                last_df = expiry_df[expiry_df['ts_et'] == last_ts]

                def get_put_mid(df, strike, expiry_date):
                    """Return mid price for the given put, or None if symbol not in data."""
                    if df.empty:
                        return None
                    exp_str = expiry_date.strftime('%y%m%d')
                    sym = f"SPXW  {exp_str}P{int(strike * 1000):08d}"
                    row = df[df['symbol'] == sym]
                    return float(row['mid'].iloc[0]) if len(row) > 0 else None

                short_mid = get_put_mid(last_df, short_strike, expiry_monday)
                long_mid = get_put_mid(last_df, long_strike, expiry_monday)

                if short_mid is None or long_mid is None:
                    # Strike outside the fetched band — skip this trade
                    current_monday += timedelta(days=7)
                    continue

                exit_debit = short_mid - long_mid
                exit_type = "EXPIRY"
                exit_date = expiry_monday
                days_held = 7

        # Record trade if exit found
        if exit_type is not None:
            pnl = entry_credit - exit_debit
            trades.append({
                'entry_date': entry_monday,
                'expiry_date': expiry_monday,
                'short_strike': short_strike,
                'long_strike': long_strike,
                'spot_entry': S_entry,
                'vix_entry': vix_entry,
                'entry_credit': entry_credit,
                'exit_type': exit_type,
                'exit_date': exit_date,
                'exit_debit': exit_debit,
                'pnl': pnl,
                'days_held': days_held,
            })

        current_monday += timedelta(days=7)

    print(f"Completed {len(trades)} trades\n")

    # --- Summary stats ---
    if not trades:
        print("No trades generated.")
        return

    df_trades = pd.DataFrame(trades)

    # Basic stats
    total_trades = len(df_trades)
    win_count = (df_trades['pnl'] > 0).sum()
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

    avg_credit = df_trades['entry_credit'].mean()
    avg_pnl = df_trades['pnl'].mean()
    total_pnl = df_trades['pnl'].sum()
    avg_days_held = df_trades['days_held'].mean()

    tp_count = (df_trades['exit_type'] == 'TP').sum()
    expiry_count = (df_trades['exit_type'] == 'EXPIRY').sum()
    tp_pct = (tp_count / total_trades * 100) if total_trades > 0 else 0
    expiry_pct = (expiry_count / total_trades * 100) if total_trades > 0 else 0

    # By exit type
    tp_trades = df_trades[df_trades['exit_type'] == 'TP']
    expiry_trades = df_trades[df_trades['exit_type'] == 'EXPIRY']

    tp_pnl = tp_trades['pnl'].mean() if len(tp_trades) > 0 else 0
    tp_wr = (tp_trades['pnl'] > 0).sum() / len(tp_trades) * 100 if len(tp_trades) > 0 else 0

    expiry_pnl = expiry_trades['pnl'].mean() if len(expiry_trades) > 0 else 0
    expiry_wr = (expiry_trades['pnl'] > 0).sum() / len(expiry_trades) * 100 if len(expiry_trades) > 0 else 0

    # Worst and best trades
    worst_5 = df_trades.nsmallest(5, 'pnl')[['entry_date', 'pnl', 'short_strike', 'spot_entry', 'exit_type']]
    best_5 = df_trades.nlargest(5, 'pnl')[['entry_date', 'pnl', 'short_strike', 'spot_entry', 'exit_type']]

    # --- Print summary ---
    date_range_min = df_trades['entry_date'].min().strftime('%Y-%m-%d')
    date_range_max = df_trades['entry_date'].max().strftime('%Y-%m-%d')

    print("=== 7DTE Put Credit Spread Backtest ===")
    print(f"Date range : {date_range_min} -> {date_range_max}")
    print(f"Total trades: {total_trades}")
    print(f"Win rate    : {win_rate:.1f}%")
    print(f"Avg credit  : ${avg_credit:.2f}")
    print(f"Avg P/L     : ${avg_pnl:.2f}  (per trade)")
    print(f"Total P/L   : ${total_pnl:.2f}")
    print(f"TP exits    : {tp_count} ({tp_pct:.1f}%)")
    print(f"Expiry exits: {expiry_count} ({expiry_pct:.1f}%)")
    print(f"Avg days held: {avg_days_held:.1f}\n")

    print("By exit type:")
    print(f"  TP    : avg P/L ${tp_pnl:.2f}, win rate {tp_wr:.1f}%")
    print(f"  EXPIRY: avg P/L ${expiry_pnl:.2f}, win rate {expiry_wr:.1f}%\n")

    print("Worst 5 trades:")
    for idx, row in worst_5.iterrows():
        date_str = row['entry_date'].strftime('%Y-%m-%d')
        print(f"  {date_str}: P/L ${row['pnl']:.2f}, strike {row['short_strike']}, spot {row['spot_entry']:.0f}, {row['exit_type']}")

    print("\nBest 5 trades:")
    for idx, row in best_5.iterrows():
        date_str = row['entry_date'].strftime('%Y-%m-%d')
        print(f"  {date_str}: P/L ${row['pnl']:.2f}, strike {row['short_strike']}, spot {row['spot_entry']:.0f}, {row['exit_type']}")

    # --- Save CSV ---
    print(f"\nSaving to {OUTPUT_CSV}...")
    df_trades.to_csv(OUTPUT_CSV, index=False)
    print("Done.")


if __name__ == '__main__':
    main()
