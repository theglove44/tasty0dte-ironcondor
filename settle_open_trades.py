#!/usr/bin/env python3
"""Manually settle open 0DTE trades using cached SPX price."""
import asyncio
import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("/Users/office/Projects/tasty0dte-ironcondor/.env")

from tastytrade import Session
import strategy

CSV_PATH = "paper_trades.csv"

def parse_strike(symbol: str) -> float | None:
    """Extract strike from option symbol like .SPXW260217C6880"""
    import re
    match = re.search(r'[CP](\d+)$', symbol)
    return float(match.group(1)) if match else None

async def settle_trades():
    print("Creating session...")
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    print("Session created.")
    
    # Get SPX close
    print("\nFetching SPX close price...")
    spx_close = await strategy.get_spx_close(session)
    
    if not spx_close:
        print("ERROR: Could not get SPX close price!")
        return
    
    print(f"SPX Close: {spx_close}")
    
    # Load trades
    df = pd.read_csv(CSV_PATH)
    open_trades = df[df['Status'] == 'OPEN']
    
    if open_trades.empty:
        print("\nNo open trades to settle.")
        return
    
    print(f"\nFound {len(open_trades)} open trade(s) to settle:")
    
    trades_settled = 0
    for idx, row in open_trades.iterrows():
        print(f"\n--- Trade {idx} ({row['Strategy']}) ---")
        
        sc = parse_strike(row['Short Call'])
        lc = parse_strike(row['Long Call'])
        sp = parse_strike(row['Short Put'])
        lp = parse_strike(row['Long Put'])
        
        if not all([sc, lc, sp, lp]):
            print(f"  Could not parse strikes, skipping")
            continue
        
        print(f"  Short Call: {sc}, Long Call: {lc}")
        print(f"  Short Put: {sp}, Long Put: {lp}")
        print(f"  Credit: ${row['Credit Collected']}")
        
        # Calculate expiration value
        call_debit = max(0, spx_close - sc) - max(0, spx_close - lc)
        put_debit = max(0, sp - spx_close) - max(0, lp - spx_close)
        total_debit = call_debit + put_debit
        
        credit = row['Credit Collected']
        pnl = credit - total_debit
        
        print(f"  Call Debit: ${call_debit:.2f}, Put Debit: ${put_debit:.2f}")
        print(f"  Total Debit: ${total_debit:.2f}")
        print(f"  P/L: ${pnl:.2f}")
        
        # Update the trade
        df.at[idx, 'Status'] = 'EXPIRED'
        df.at[idx, 'Exit Time'] = datetime.now().strftime("%H:%M:%S")
        df.at[idx, 'Exit P/L'] = round(pnl, 2)
        
        # Update notes
        current_notes = df.at[idx, 'Notes'] if pd.notna(df.at[idx, 'Notes']) else ""
        df.at[idx, 'Notes'] = f"{current_notes} | Settled at {spx_close:.2f} (manual)"
        
        trades_settled += 1
        result = "WINNER ✓" if pnl > 0 else "LOSER ✗" if pnl < 0 else "SCRATCH"
        print(f"  Result: {result}")
    
    # Save
    df.to_csv(CSV_PATH, index=False)
    print(f"\n{'='*50}")
    print(f"Settled {trades_settled} trade(s). CSV updated.")

if __name__ == "__main__":
    asyncio.run(settle_trades())
