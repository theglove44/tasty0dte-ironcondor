# 0DTE Iron Condor Bot — Lessons & Knowledge

## Bugs & Fixes

### ATR(14) was 5m-granular, not daily (2026-04-17)
- **Problem**: Quality badge (A+/A/B/C) from grader.py was meaningless since ORB Stacking launched. Thresholds (<20% / 20–30% / 30–40% / >40%) assumed DAILY ATR (~50–80 SPX points) but the engine was computing ATR from 5m bars (~8–15 pts).
- **Root cause**: `engine.py` called `self._atr.update(bar)` on every 5m bar; `live_runner.warmup_engine` fed prior-day 5m bars to the same path. Per Doc1 §7 line 59, ATR(14) must use DAILY ranges of the 14 preceding sessions. Invisible in the backtest gate because the gate measures stacking-tier progression only, not grader output.
- **Fix**: Added `fetch_daily_bars()` to `bar_fetcher.py` (with broad try/except so setup failures degrade to `atr_not_ready` instead of crashing startup); wired daily-seed into `run_orb_stacking`, demo `run_live`, and demo `run_replay` (replay aggregates fetched 5m bars into daily OHLC for dates before target_date); removed `_atr.update` from `on_closed_bar`; renamed skip reason from `api_error` to `atr_not_ready` for this specific case. Backtest now aggregates 5m sessions into daily OHLC; first 14 sessions excluded from results (disclosed in report). Pine indicator switched to `request.security(syminfo.tickerid, "D", ta.atr(14)[1], lookahead=barmerge.lookahead_off)` so chart visuals match engine semantics.
- **Prevention**: For each indicator, write a sanity test that feeds ONE realistic warmup window and asserts the output is in the expected order-of-magnitude range. ATR(14) on SPX should be 30–150 points; if < 20, something is wrong. Backtest gates should exercise grader output, not only stacking-tier classification.
- **Gate impact**: PLUS/DOUBLE rates effectively unchanged (PLUS=80.2%, DOUBLE 92.8% → 92.7%; 0.1% drift explained by first-14-session exclusion). Tier progression is ATR-independent; only the post-hoc quality grade is affected.

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
- **Problem**: Dynamic strategy skipped because SPX `Quote` stream returned no usable events in-session.
- **Fix**: Updated `strategy.get_spx_spot()` fallback chain to use `Trade` price when `Quote` mark is unavailable (mid → ask-only → bid-only → trade).
- **Prevention**: For SPX decision signals, support multiple data event types and avoid single-feed dependence.

### Spot Fetch Timeout Trap (2026-03-03)
- **Problem**: Quote wait wrapper timed out and returned early before attempting trade fallback.
- **Fix**: Split timeout handling per source so trade fallback always runs after quote timeout.
- **Prevention**: Apply timeout/fallback per stage, not around the whole multi-stage fetch flow.

### Temporary Trigger Cleanup (2026-03-03)
- **Problem**: Added a one-off 16:00 Dynamic trigger for live verification.
- **Fix**: Reverted scheduler back to default trigger times and restored Dynamic allowed time to 15:00 only.
- **Prevention**: Use temporary verification windows only with explicit same-day rollback and record purge.

## Patterns & Conventions

- Bot is cron-based: start/stop at scheduled times
- All trades tracked in `paper_trades.csv`
- Credit-only strategies (no debit spreads)
- Market hours: 14:30-21:00 UK time
- PDT rule: max 3 day trades per 5 days
