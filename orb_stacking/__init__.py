"""ORB Stacking — Opening Range Breakout stacking strategy, under construction.

Isolated from the live bot. Strategy implementation proceeds via sliced builds
(roadmap in `ROADMAP.md`). ORB Stacking is driven by 21 years of 5-min SPX
research and targets 70%+ win rate on stacked opening-range breakouts.
See `SOURCE_OF_TRUTH.md` for the complete spec.

Public modules:
  - time_utils: timezone conversions (to_et, to_uk, to_utc) and ORB lock-time helpers
  - bar_fetcher: DXLink 5m candle fetching with history warmup
  - indicators: ATR(14) indicator
"""

from . import time_utils
