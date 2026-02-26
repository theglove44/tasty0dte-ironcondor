#!/usr/bin/env python3
"""Gap Checker - Run at 2:45pm to validate overnight gap filter"""

import os
import asyncio
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from tastytrade import Session
import strategy

load_dotenv()


async def main():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    
    if not refresh_token or not client_secret:
        print("⚠️ Missing TastyTrade credentials")
        return
    
    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    
    gap_data = await strategy.get_overnight_gap(session)
    
    if gap_data:
        should_trade, reason = strategy.should_trade_overnight_filter(gap_data)
        gap_pct = gap_data['gap_pct']
        classification = gap_data['gap_classification']
        
        print(f"📊 Gap Checker — Today")
        print(f"")
        print(f"→ Gap: {gap_pct:+.2f}% ({classification})")
        print(f"")
        if should_trade:
            print(f"✅ {reason}")
        else:
            print(f"⏸️ {reason}")
    else:
        print("⚠️ No gap data available")


if __name__ == "__main__":
    asyncio.run(main())
