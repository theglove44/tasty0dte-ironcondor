import tastytrade
print("tastytrade dir:", dir(tastytrade))

try:
    import tastytrade.metrics
    print("tastytrade.metrics dir:", dir(tastytrade.metrics))
except ImportError:
    print("No tastytrade.metrics module")

try:
    from tastytrade.metrics import get_market_metrics
    print("Found get_market_metrics")
except ImportError:
    print("Could not import get_market_metrics from tastytrade.metrics")

# Check imports in strategy.py
from tastytrade.instruments import NestedOptionChain, Option
# maybe it is in instruments?
import tastytrade.instruments
print("tastytrade.instruments dir:", dir(tastytrade.instruments))
