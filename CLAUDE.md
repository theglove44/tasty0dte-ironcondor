# CLAUDE.md - Project Context for AI Assistants

## Project Overview

Tasty0DTE is an automated 0DTE (Zero Days to Expiration) options trading bot for SPX using the Tastytrade API. It runs in paper trading mode by default, logging simulated trades to CSV.

## Architecture

```
main.py          - Entry point, async event loop, session management, trade scheduling
strategy.py      - Option chain fetching, Greeks streaming, leg selection (IC + Iron Fly)
monitor.py       - Position P/L monitoring, profit target exits, time exits, EOD expiration, stale trade cleanup
logger.py        - CSV trade logging with schema migration support
local/discord_notify.py - Discord webhook notifications (trade open/close) [gitignored]
local/x_notify.py       - X (Twitter) trade posting [gitignored]
```

### Execution Flow

1. `main.py` authenticates via OAuth (refresh token + provider secret)
2. Main loop runs continuously, checking UK time against target entry times (14:45, 15:00, 15:30)
3. At entry time: fetches SPX option chain, filters 0DTE, runs 6 strategy variants
4. Every 10s: `monitor.check_open_positions()` auto-expires stale prior-day trades, streams quotes, calculates P/L, triggers exits
5. At 21:00 UK: `monitor.check_eod_expiration()` settles remaining open positions

### External Lifecycle

`market_session_guard.sh` manages the bot lifecycle based on tastytrade market session API. It starts/stops the bot within a [open-15m, close+15m] window. Run via cron or launchd.

### Support Scripts
- `run_autotrader.sh` - Activates venv and launches main.py under caffeinate
- `setup_service.sh` - Service installation helper
- `monitor_logs.sh` - Log tailing utility

## Key Dependencies

- **tastytrade SDK v12.0.0** - Typed async SDK with auto token refresh
- **pandas** - CSV I/O and DataFrame operations
- **pytz** - UK timezone handling
- **DXLinkStreamer** - Real-time quote/Greeks streaming via WebSocket

## Tastytrade SDK Patterns

### Session Management
```python
from tastytrade import Session
session = Session(provider_secret=client_secret, refresh_token=refresh_token)
# SDK v12+ auto-refreshes tokens (15-min expiry) on every request
```

### Streaming Quotes
```python
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Quote, Greeks, Summary

async with DXLinkStreamer(session) as streamer:
    await streamer.subscribe(Quote, ["SPX", ".SPXW..."])
    async for event in streamer.listen(Quote):
        # event can be a single Quote or list of Quotes
        events = event if isinstance(event, list) else [event]
```

**Important**: Streamer connections should be long-lived. Avoid creating new streamers per request in hot paths. The monitoring loop (every 10s) currently creates a new streamer each cycle.

### Option Chain
```python
from tastytrade.instruments import get_option_chain, OptionType
chain = get_option_chain(session, "SPX")  # Returns Dict[date, List[Option]]
```

### Market Metrics
```python
from tastytrade.metrics import get_market_metrics
# May return an awaitable in some SDK versions - use _unwrap_awaitable()
metrics = await _unwrap_awaitable(get_market_metrics(session, ["SPX"]))
iv_rank = float(metrics[0].implied_volatility_index_rank)
```

**Important**: Always use `getattr(obj, 'attr_name', None)` with string attribute names. Bare names like `getattr(obj, attr_name, None)` cause `NameError`.

## CSV Data Schema

File: `paper_trades.csv`

| Column | Type | Description |
|--------|------|-------------|
| Date | date | Trade date |
| Entry Time | HH:MM:SS | Entry timestamp |
| Symbol | str | Always "SPX" |
| Strategy | str | "20 Delta", "30 Delta", "Iron Fly V1-V4" |
| StrategyId | str | e.g. "IC-20D-1445", "IF-V2-1500" |
| Short Call / Long Call / Short Put / Long Put | str | Tasty symbols e.g. ".SPXW251210C6875" |
| Credit Collected | float | Initial credit received |
| Buying Power | float | Capital at risk * 100 |
| Profit Target | float | Dollar target (credit * pct) |
| Status | str | OPEN -> CLOSED or EXPIRED |
| Exit Time | HH:MM:SS | When exited |
| Exit P/L | float | Realized P/L |
| Notes | str | Exit details |
| IV Rank | float | SPX IV Rank at entry (0-100 scale) |

### Trade Lifecycle States

- **OPEN** - Active, being monitored every 10s
- **CLOSED** - Exited via profit target or time exit rule
- **EXPIRED** - Settled at EOD based on SPX spot price

## Strategies

| Strategy | Type | Target Delta | Wings | Profit Target | Special Rules |
|----------|------|-------------|-------|--------------|---------------|
| 20 Delta | iron_condor | 0.20 | $20 | 25% | EOD expiry |
| 30 Delta | iron_condor | 0.30 | $20 | 25% | Time exit 18:00 UK |
| Iron Fly V1 | iron_fly | 0.50 (ATM) | $10 | 10% | 15:00 only |
| Iron Fly V2 | iron_fly | 0.50 (ATM) | $10 | 20% | 15:00 only |
| Iron Fly V3 | iron_fly | 0.50 (ATM) | $10 | 10% | 15:30 only |
| Iron Fly V4 | iron_fly | 0.50 (ATM) | $10 | 20% | 15:30 only |

## Testing

```bash
source venv/bin/activate
python -m unittest test_monitor test_fly_legs test_entry_logic -v
```

Tests use `unittest` (not pytest). Key test files:
- `test_monitor.py` - P/L calculation, profit target exit, EOD settlement
- `test_fly_legs.py` - Iron Fly leg selection algorithm
- `test_entry_logic.py` - Scheduler trigger timing

## Common Gotchas

1. **SPX symbols**: Format is `.SPXW{YYMMDD}{C|P}{strike}` (e.g. `.SPXW251210C6875`). Strike is the raw number, not multiplied.
2. **IV Rank normalization**: Tastytrade API returns IV Rank as a ratio (0-1) or percentage (0-100) inconsistently. The logger normalizes values <= 1.0 by multiplying by 100.
3. **UK timezone**: All entry/exit times are in Europe/London timezone. Market close is 21:00 UK.
4. **Paper mode**: No actual orders are placed. The bot logs to CSV and sends Discord notifications. There is no `PAPER_TRADING_MODE` flag - the code simply never calls the order API.
5. **Guard script**: Requires `.guard_enabled` marker file to take action. Without it, the guard operates in observe-only mode.
6. **CSV concurrency**: The CSV file is read and written by both the main loop and monitoring functions. No file locking is implemented.
7. **Stale trades**: If the bot crashes before EOD settlement, 0DTE trades can remain OPEN overnight. `monitor.check_open_positions()` now auto-expires these on the next day (assumes max loss since expired option prices are unavailable).
8. **SDK async/sync ambiguity**: `get_option_chain()` and `get_market_metrics()` may be sync or async depending on SDK version. Always wrap with `_unwrap_awaitable()` from strategy.py.
9. **Streamer failures on expired symbols**: Subscribing to expired option symbols (e.g. yesterday's 0DTE) causes silent DXLink errors. The stale trade cleanup prevents this.
10. **discord_notify can be None**: The `local/` directory is gitignored. Always guard `discord_notify` and `x_notify` before calling.
11. **Error logging**: All exception handlers should log `{type(e).__name__}: {e}` - some SDK exceptions have empty string messages.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TASTY_REFRESH_TOKEN` | Yes | OAuth refresh token |
| `TASTY_CLIENT_SECRET` | Yes | OAuth provider secret |
| `TASTY_ACCOUNT_ID` | Yes | Account number |
| `DISCORD_WEBHOOK_URL_0DTE` | No | Discord webhook for notifications |
| `TWEET_SCRIPT_PATH` | No | Path to X posting script |
