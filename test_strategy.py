import asyncio
import os
import logging
from dotenv import load_dotenv
from tastytrade import Session
import main

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-strategy")

load_dotenv()

async def run_now():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    account_id = os.getenv("TASTY_ACCOUNT_ID")
    
    if not refresh_token or not client_secret:
        logger.error("Missing credentials.")
        return
        
    session = Session(refresh_token=refresh_token, provider_secret=client_secret)
    logger.info("Session created. Running trade cycle now...")
    
    await main.execute_trade_cycle(session)

if __name__ == "__main__":
    asyncio.run(run_now())
