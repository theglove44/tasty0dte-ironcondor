import asyncio
import os
import logging
from dotenv import load_dotenv
from tastytrade import Session
from tastytrade.instruments import get_future_option_chain

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("probe-es")

async def probe_es():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    
    if not refresh_token or not client_secret:
        logger.error("TASTY_REFRESH_TOKEN or TASTY_CLIENT_SECRET not found.")
        return

    try:
        session = Session(refresh_token=refresh_token, provider_secret=client_secret)
        logger.info("Session created.")
        
        # Try fetching /ES Futures Option Chain
        symbol = "/ES"
        logger.info(f"Fetching option chain for {symbol}...")
        
        # Use get_future_option_chain for futures
        # Provide the root symbol
        chain = get_future_option_chain(session, symbol)
        
        if chain:
            logger.info("Chain fetched successfully.")
            # chain is likely a dict of expiration_date -> list of Strike objects (or similar)
            # Or dict of expiration_date -> nested structure
            
            if isinstance(chain, dict):
                keys = list(chain.keys())
                keys.sort()
                logger.info(f"Found {len(keys)} expirations.")
                for k in keys[:5]:
                    logger.info(f"Expiration: {k}")
                
                # Inspect first value
                first_exp = keys[0]
                first_chain = chain[first_exp]
                logger.info(f"Value for {first_exp}: type={type(first_chain)}")
                # Check for strikes attribute or if it is a list
                if isinstance(first_chain, list):
                    logger.info(f"First item: {first_chain[0]}")
                else:
                    logger.info(f"Attributes: {dir(first_chain)}")
            else:
                 # It might be an object or list
                 logger.info(f"Chain type: {type(chain)}")
                 if hasattr(chain, 'keys'):
                      logger.info(f"Keys: {list(chain.keys())[:5]}")
        else:
            logger.warning("Chain was empty or None.")
            
    except Exception as e:
        logger.error(f"Error probing /ES: {e}")

if __name__ == "__main__":
    asyncio.run(probe_es())
