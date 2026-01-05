import os
import asyncio
import logging
from dotenv import load_dotenv
from tastytrade import Session
import monitor

# Configure logging to suppress misc logs but show major info
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.NullHandler() # We rely on monitor.py's console output
    ]
)

# Suppress chatty libraries
logging.getLogger("tastytrade").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

load_dotenv()

async def list_live():
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN")
    client_secret = os.getenv("TASTY_CLIENT_SECRET")
    
    if not refresh_token or not client_secret:
        print("Error: Missing credentials in .env")
        return

    print("Authenticating with Tastytrade (Monitor Only)...")
    try:
        session = Session(refresh_token=refresh_token, provider_secret=client_secret)
    except Exception as e:
        print(f"Authentication failed: {e}")
        return
    
    print("Starting Live Monitor. Press Ctrl+C to exit.")
    
    try:
        while True:
            # Connection Keep-Alive
            if not session.validate():
                # print("Refreshing session...")
                session = Session(refresh_token=refresh_token, provider_secret=client_secret)

            # Check open positions in READ-ONLY mode
            await monitor.check_open_positions(session, read_only=True)
            
            # Note: We do NOT check EOD expiration here because that modifies state.
            
            await asyncio.sleep(10) # check every 10 seconds

    except KeyboardInterrupt:
        print("\nStopping Monitor...")

if __name__ == "__main__":
    try:
        asyncio.run(list_live())
    except KeyboardInterrupt:
        pass
