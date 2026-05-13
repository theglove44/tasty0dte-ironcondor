import inspect
from tastytrade.metrics import get_market_metrics
import tastytrade.metrics

print("Signature:", inspect.signature(get_market_metrics))
# also help
help(get_market_metrics)
