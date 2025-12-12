import asyncio
import os
import logging
from dotenv import load_dotenv
from tastytrade import Session, DXLinkStreamer
from tastytrade.dxfeed import Summary, Quote

logging.basicConfig(level=logging.INFO)
load_dotenv()

async def main():
    token = os.getenv("TASTY_REFRESH_TOKEN")
    secret = os.getenv("TASTY_CLIENT_SECRET")
    session = Session(refresh_token=token, provider_secret=secret)
    
    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(Summary, ["SPX"])
        # await streamer.subscribe(Quote, ["SPX"])
        
        print("Listening for Summary...")
        async for event in streamer.listen(Summary):
            print(f"Event Type: {type(event)}")
            print(f"Data: {event}")
            # Break after first event
            break

asyncio.run(main())
