import pandas as pd
import os
import sys

def view_trades():
    file_path = 'paper_trades.csv'
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    try:
        df = pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        print(f"File {file_path} is empty.")
        return
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    if df.empty:
        print("No trades found in log.")
        return

    # Set pandas display options for better visibility
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.max_rows', None)
    pd.set_option('display.colheader_justify', 'left')

    # Filter for Closed Trades
    # Assuming 'Status' column exists. If not, show all.
    if 'Status' in df.columns:
        closed_trades = df[df['Status'] != 'OPEN'].copy()
    else:
        closed_trades = df.copy()

    if closed_trades.empty:
        print("No closed trades found.")
    else:
        print("\n=== Closed Trades Log ===\n")
        
        # Select columns to display
        # We want: Date, Entry Time, Symbol, Short Call, Long Call, Short Put, Long Put, Credit Collected, Exit P/L, Notes
        # Adjust based on what is available
        cols_to_show = ['Date', 'Entry Time', 'Symbol', 'Exit P/L', 'Notes']
        
        # Add Strikes context if possible, but keep it clean.
        # Maybe just show the main columns requested.
        
        # Check if columns exist before selecting
        available_cols = [c for c in cols_to_show if c in df.columns]
        
        print(closed_trades[available_cols])
        print("\n=========================")

        # Summary Stats for Closed Trades
        total_closed = len(closed_trades)
        total_pl = closed_trades['Exit P/L'].sum() if 'Exit P/L' in closed_trades.columns else 0.0
        
        print(f"\nSummary (Closed Trades):")
        print(f"Count: {total_closed}")
        print(f"Total P/L: ${total_pl:.2f}")

    # Optionally show Open trades separately if desired, but user asked for "closed trades with their results"
    if 'Status' in df.columns:
        open_trades = df[df['Status'] == 'OPEN']
        if not open_trades.empty:
            print(f"\n[Note: {len(open_trades)} Open Trade(s) hidden]")

if __name__ == "__main__":
    view_trades()
