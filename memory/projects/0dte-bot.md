# 0DTE Iron Condor Bot — Lessons & Knowledge

## Bugs & Fixes

### EOD Settlement — SPX Close Price (2025)
- **Problem**: EOD settlement couldn't get SPX closing price reliably from DXFeed API
- **Fix**: Added `.spx_cache.json` as fallback; use Summary event for closing price
- **Prevention**: Always cache last-known price before settlement logic runs

## API Quirks

_(Document DXFeed/Tastytrade API issues, timeouts, rate limits here)_

## Strategy Performance

_(Track win rate, P/L by strategy ID after live/paper runs)_

### Removed Strategies
- **IC-20D-1500**: 88% win rate but negative P/L — removed

### Active Strategies
- **GF-20D**: Overnight gap filter strategy — added for filtering entries

## Process Lessons

### Documentation/Test Drift (2026-03-03)
- **Problem**: README and dashboard strategy config drifted from `main.py`; EOD unit tests mocked `get_spx_spot` while production code uses `get_spx_close`.
- **Fix**: Updated README strategy matrix, updated dashboard strategy config, and corrected EOD tests to mock `get_spx_close`.
- **Prevention**: Treat `main.py` `STRATEGY_CONFIGS` as source-of-truth and verify docs/tests whenever strategy timing/exit logic changes.

### Dynamic SPX Spot Fallback (2026-03-03)
- **Problem**: Dynamic strategy could skip if SPX quote had only bid or only ask; logic handled ask-only but not bid-only.
- **Fix**: Updated `strategy.get_spx_spot()` to use bid-only fallback when ask is missing.
- **Prevention**: Keep quote parsing tolerant to partial market data (mid → ask-only → bid-only) for decision-critical signals.

## Patterns & Conventions

- Bot is cron-based: start/stop at scheduled times
- All trades tracked in `paper_trades.csv`
- Credit-only strategies (no debit spreads)
- Market hours: 14:30-21:00 UK time
- PDT rule: max 3 day trades per 5 days
