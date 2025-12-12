import asyncio
import os
import logger as trade_logger
from dotenv import load_dotenv
from tastytrade import Session
import strategy
import pandas as pd

load_dotenv()

async def verify():
    print("--- 1. Authenticating ---")
    token = os.getenv("TASTY_REFRESH_TOKEN")
    secret = os.getenv("TASTY_CLIENT_SECRET")
    session = Session(refresh_token=token, provider_secret=secret)
    print("Authenticated.")

    print("\n--- 2. Testing IV Rank Fetch ---")
    iv_rank = await strategy.fetch_spx_iv_rank(session)
    print(f"Fetched IV Rank: {iv_rank}")
    
    if iv_rank == 0.0:
        print("WARNING: IV Rank is 0.0 (might be expected if market closed or error, but checking if function ran)")
    else:
        print("PASS: Fetched non-zero IV Rank.")

    print("\n--- 3. Testing Logger Migration & Entry ---")
    # Create dummy legs
    legs = {
        'short_call': {'symbol': 'TEST_SC', 'strike': 100},
        'long_call': {'symbol': 'TEST_LC', 'strike': 105},
        'short_put': {'symbol': 'TEST_SP', 'strike': 90},
        'long_put': {'symbol': 'TEST_LP', 'strike': 85}
    }
    
    trade_logger.log_trade_entry(legs, 1.0, 100.0, 0.25, iv_rank)
    print("Logged test trade.")
    
    print("\n--- 4. Verifying CSV Content ---")
    df = pd.read_csv("paper_trades.csv")
    print("Columns:", df.columns.tolist())
    
    if "IV Rank" not in df.columns:
        print("FAIL: 'IV Rank' column missing.")
    else:
        print("PASS: 'IV Rank' column exists.")
        
    last_row = df.iloc[-1]
    print("Last Row IV Rank:", last_row["IV Rank"])
    
    if float(last_row["IV Rank"]) == iv_rank:
        print("PASS: Logged IV Rank matches fetched value.")
    else:
        print(f"FAIL: Value mismatch. Logged: {last_row['IV Rank']}, Expected: {iv_rank}")

if __name__ == "__main__":
    asyncio.run(verify())
