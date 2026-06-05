# 0DTE Iron Condor Bot — Lessons & Knowledge

## Bugs & Fixes

### Silent 0DTE entry skips — parity guard + timeout cascade (2026-06-05) [FIXED — implemented, commit pending]
- **Problem**: Iron Fly V1 missed 3 of 4 entries the week of Jun 1 (only Tue logged). User spotted the gaps in the V1 dashboard. The bot was NOT down — V3/V4/ORB traded every day; cron ran it 14:30–21:15.
- **Root cause**: (1) The put-call parity guard in `validate_credit_sanity` (`strategy.py:642`, `PARITY_TOLERANCE=$2.00`) rejected V1 on Mon/Wed/Thu with drift $2.06/$2.18/$2.15 — marginally over — and there is **NO retry**: `main.py:206-208` just `continue`s, so one stale REST mark abandons the day's entry. V1 is **first in `STRATEGY_CONFIGS`** (`main.py:54`), so it executes right at the 15:00 open spike and systematically catches the stalest marks; V2 (~15s later) passes the same check. 21 lifetime parity rejections across all 0DTE strats (V4×7, V1×6, V2×4, V3×2, Dynamic×2); V1 took 3 of its 6 this one week (SPX≈7600 makes a flat $2 tolerance relatively tighter). (2) Thu Jun 4 also had a `ReadTimeout` in V2's execution that propagated to the single call-site `try/except` (`main.py:316-318` "Trade cycle failed"), aborting the rest of the cycle → **Dynamic never executed**. One strategy's failure cascades to all later strategies (the `return`-vs-`continue` pitfall). (3) Skips are silent — `logger.warning` in `trade.log` only, no alert.
- **Status**: FIXED 2026-06-05 via build-qa pipeline (Opus plan → Haiku build → Sonnet review → Opus approve → Codex independent review). `main.py` now has `_build_validated_trade` (retry validation with fresh marks, ≤3×), `_fetch_chain_with_retry`, per-strategy `try/except` isolation in the JL + 0DTE loops, and `_notify_skip`/`_notify_0dte_cycle_skip` alerts. **Design**: `validate_credit_sanity` kept its 2-tuple (every is_valid=False is a retryable stale-mark artifact, so the caller retries on any False) → zero churn to jade_lizard.py + the 14 credit/JL tests. **Codex caught** two gaps the plan-aware reviewers missed: chain-level cycle skips were silent (now alerted) and the per-strategy `try` started after the config reads (now wraps `strat['type']`/`strat['profit_target_pct']` in both loops). 21 new tests in `tests/test_entry_reliability.py`; full suite 117 green. Applies on next 14:30 cron start; **not yet committed**.
- **Prevention**: Entry guards that reject on transient/stale data must RE-FETCH and retry before abandoning, never give up on the first reading. Isolate each strategy in the cycle loop (`try/except`+`continue`) so one failure can't skip the rest. Surface every entry skip via notification — these were invisible for weeks until the dashboard exposed them. **"Missing trades" ≠ bot down**: always grep `trade.log` for `REJECTED`/`Skipping`/`Trade cycle failed` before assuming an outage.

### IV Rank column logged on two scales (2026-06-04)
- **Problem**: `IV Rank` in `paper_trades.csv` was a mix of 0-1 ratio (rows ≤2026-01-16) and 0-100 percentage (rows ≥2026-01-20). 653 of 846 rows were percentages, so `analysis/common.iv_bin` (which assumes a 0-1 ratio: <0.20/0.20-0.35/0.35-0.50/>=0.50) misclassified every percentage row into ">=0.50" — the IV-regime breakdown in `strategy_metrics.py` and `regenerate_site_data.py` was meaningless.
- **Root cause**: A guard added to `logger.py` (~mid-Jan 2026) did `if 0 < ivr_val <= 1.0: ivr_val *= 100.0`, normalising *up* to percentage and contradicting `iv_bin` + the MEMORY.md convention ("IV Rank comes as ratio (0-1) — multiply by 100 for display"). The SDK's `implied_volatility_index_rank` returns the ratio natively. Older rows (written before the guard) kept the raw ratio; the scale split is purely temporal.
- **Fix**: Flipped the guard to normalise to the canonical 0-1 ratio (`if ivr_val > 1.5: ivr_val /= 100.0` — a true ratio never exceeds 1.0). Backfilled history with `analysis/normalize_iv_rank.py --apply` (653 rows ÷100, timestamped backup, idempotent, report-by-default like `dedup_trades.py`). Fixed `dashboard/templates/partials/open_positions.html` to ×100 for display. Added `tests/test_logger.py` (8 cases). Re-ran `regenerate_site_data.py`. Verified backup-vs-new: exactly 653 IV cells changed, 0 collateral edits; bins now distribute (V1: 16/18/48/3 Very Low/Low/Mid/High).
- **Prevention**: One canonical storage scale, normalised at the single write point; never `iv_bin`/aggregate a raw column without first asserting its scale. Caveat: CSV precision is 2-dp (`monitor.py` writes with `float_format='%.2f'`), so a value within ~0.005 of a bin boundary (0.20/0.35/0.50) can land one bin off — fundamental to 2-dp storage, not the backfill. The monitor live display and `tools/check_monitor_display.py` were already written for the ratio (`IVR=0.26` for 0.255), so reverting to ratio realigned them automatically; only the dashboard template needed the ×100.

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

### REST ReadTimeout bursts at the 15:00 open (2026-06-05)
- tastytrade REST (chain / Greeks / market-data) intermittently throws `ReadTimeout` during the 15:00 entry burst when many strategies fetch at once. Thu Jun 4: V2's cycle died on `ReadTimeout`, then `Error streaming quotes: ReadTimeout` repeated 15:00–15:16. Contributes to entry misses and (without per-strategy isolation) cascades to skip later strategies.
- Mitigations: per-strategy `try/except`+`continue`, retries on the shared chain fetch, and consider trimming/spacing the 15:00 roster to shrink the burst. Running the full strategy set (V1–V4 + Dynamic + 3 JL checks) all at 15:00 amplifies timeout risk; the 15:30 batch (V3/V4) rarely fails.

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
