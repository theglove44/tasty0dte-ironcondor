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

## Patterns & Conventions

- Bot is cron-based: start/stop at scheduled times
- All trades tracked in `paper_trades.csv`
- Credit-only strategies (no debit spreads)
- Market hours: 14:30-21:00 UK time
- PDT rule: max 3 day trades per 5 days
