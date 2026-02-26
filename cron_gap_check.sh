#!/bin/bash
# Gap Checker Cron - Run at 2:45pm to validate overnight gap filter

cd ~/Projects/tasty0dte-ironcondor

# Activate venv and run gap check with gtimeout (or use python timeout)
source venv/bin/activate

python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
from tastytrade import Session
import strategy
import os

load_dotenv()

async def main():
    try:
        refresh_token = os.getenv('TASTY_REFRESH_TOKEN')
        client_secret = os.getenv('TASTY_CLIENT_SECRET')
        
        if not refresh_token or not client_secret:
            print('⚠️ Missing credentials')
            return
        
        session = Session(provider_secret=client_secret, refresh_token=refresh_token)
        
        gap_data = await strategy.get_overnight_gap(session)
        
        if gap_data:
            should_trade, reason = strategy.should_trade_overnight_filter(gap_data)
            gap_pct = gap_data['gap_pct']
            classification = gap_data['gap_classification']
            
            print(f'Gap: {gap_pct:+.2f}% ({classification})')
            print('')
            if should_trade:
                print(f'✅ {reason}')
            else:
                print(f'⏸️ {reason}')
        else:
            print('⚠️ No gap data available')
    except Exception as e:
        print(f'⚠️ Error: {e}')

asyncio.run(main())
" 2>&1
