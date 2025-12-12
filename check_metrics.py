import os
import logging
from dotenv import load_dotenv
from tastytrade import Session
from tastytrade.metrics import get_market_metrics

# load_dotenv() # It seems main does this, I should too to get env vars
# Or I can just read them manually if load_dotenv not installed? 
# It is imported in main.py, so it should be there.
load_dotenv()

token = os.getenv("TASTY_REFRESH_TOKEN")
secret = os.getenv("TASTY_CLIENT_SECRET")

if not token or not secret:
    print("Missing credentials")
    exit(1)

try:
    session = Session(refresh_token=token, provider_secret=secret)
    print("Authenticated")
    metrics = get_market_metrics(session, ["SPX"])
    if metrics:
        m = metrics[0]
        print("Metric:", m)
        # Try to print all attributes
        try:
            print("Dict:", m.dict())
        except:
             print("Dir:", dir(m))
    else:
        print("No metrics found")
except Exception as e:
    print("Error:", e)
