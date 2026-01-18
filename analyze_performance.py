import pandas as pd
import os
import sys
from datetime import datetime

def analyze_performance():
    file_path = 'paper_trades.csv'
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    if df.empty:
        print("No trades found in log.")
        return

    # Filter for Completed Trades (CLOSED or EXPIRED)
    # Status column must be present.
    if 'Status' not in df.columns:
        print("Error: 'Status' column missing.")
        return

    # Filter out OPEN trades
    df = df[df['Status'] != 'OPEN'].copy()

    if df.empty:
        print("No completed trades found to analyze.")
        return

    # Ensure numeric P/L
    # Remove '$' if present and convert to float
    def clean_pl(val):
        if pd.isna(val): return 0.0
        val = str(val).replace('$', '').replace(',', '')
        try:
            return float(val)
        except:
            return 0.0

    df['Exit P/L'] = df['Exit P/L'].apply(clean_pl)

    # Normalize Strategy Name
    # We want to group by "Strategy" column.
    # Also standardize Entry Time to HH:MM (remove seconds) to group variations.
    
    def get_time_bucket(t_str):
        # Expected format HH:MM:SS or HH:MM
        s = str(t_str)
        if len(s) >= 5:
            return s[:5] # Returns HH:MM
        return s

    df['TimeBucket'] = df['Entry Time'].apply(get_time_bucket)

    # Group by Strategy and TimeBucket
    # Strategy column usually contains "20 Delta", "30 Delta", "Iron Fly V1", etc.
    if 'Strategy' not in df.columns:
         print("Error: 'Strategy' column missing.")
         return

    grouped = df.groupby(['Strategy', 'TimeBucket'])

    stats = []

    for (strat, time_bucket), group in grouped:
        total_trades = len(group)
        total_pl = group['Exit P/L'].sum()
        
        winners = group[group['Exit P/L'] > 0]
        losers = group[group['Exit P/L'] <= 0]
        
        win_count = len(winners)
        loss_count = len(losers)
        
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0.0
        
        avg_win = winners['Exit P/L'].mean() if win_count > 0 else 0.0
        avg_loss = losers['Exit P/L'].mean() if loss_count > 0 else 0.0
        
        # Expectancy = (Prob Win * Avg Win) + (Prob Loss * Avg Loss)
        # Note Avg Loss is usually negative, so it subtracts.
        prob_win = win_count / total_trades
        prob_loss = loss_count / total_trades
        expectancy = (prob_win * avg_win) + (prob_loss * avg_loss)
        
        stats.append({
            'Strategy': strat,
            'Time': time_bucket,
            'Trades': total_trades,
            'Win Rate': win_rate,
            'Total P/L': total_pl,
            'Avg Win': avg_win,
            'Avg Loss': avg_loss,
            'Expectancy': expectancy
        })
        
    # Convert to DataFrame for display
    results = pd.DataFrame(stats)
    
    # Sort by Total P/L descending
    results = results.sort_values(by='Total P/L', ascending=False)
    
    # Formatting
    pd.options.display.float_format = '{:,.2f}'.format
    
    print("\n=== Strategy Performance Analysis ===\n")
    
    # Rename columns for cleaner output
    results_display = results.rename(columns={
        'Win Rate': 'Win %',
        'Total P/L': 'Net P/L ($)',
        'Avg Win': 'Avg Win ($)',
        'Avg Loss': 'Avg Loss ($)',
        'Expectancy': 'Exp Value ($)'
    })
    
    # Print formatted
    # Using to_string for nice alignment if tabulate not available
    print(results_display.to_string(index=False, formatters={
        'Win %': '{:.1f}%'.format,
        'Net P/L ($)': '${:,.2f}'.format,
        'Avg Win ($)': '${:,.2f}'.format,
        'Avg Loss ($)': '${:,.2f}'.format,
        'Exp Value ($)': '${:,.2f}'.format
    }))
    
    print("\n=====================================")
    
    # Grand Total
    grand_total_pl = df['Exit P/L'].sum()
    grand_total_trades = len(df)
    grand_win_rate = (len(df[df['Exit P/L'] > 0]) / grand_total_trades * 100) if grand_total_trades > 0 else 0.0
    
    print(f"\nOverall Stats:")
    print(f"Total Trades: {grand_total_trades}")
    print(f"Overall Win Rate: {grand_win_rate:.1f}%")
    print(f"Total P/L: ${grand_total_pl:.2f}")

if __name__ == "__main__":
    analyze_performance()
