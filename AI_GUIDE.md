# AI_GUIDE.md — Tasty0DTE Iron Condor Bot

This document is for AI agents working on this codebase. It captures all context needed to understand, modify, and reason about the project without relying on tribal knowledge or prior conversation history.

---

## 1. What this project is

An automated **paper-trading bot** for SPX 0DTE (zero-days-to-expiration) option strategies. It connects to the Tastytrade API, enters credit-selling structures at scheduled times during the US cash session, monitors positions for profit targets, and exits by time-stop or at EOD settlement. All trades are logged to `data/paper_trades.csv` — this is a simulation system; no live orders are placed.

Key facts:
- Python 3.13, `async/await` throughout
- Tastytrade SDK v12.0.0
- UK timezone (`Europe/London`) for all scheduling
- macOS host (LaunchAgent + `caffeinate` in helper scripts)
- Paper trading only — `data/paper_trades.csv` is the source of truth

---

## 2. Repository layout

```
tasty0dte/              # packaged bot runtime (canonical code)
  main.py               # scheduler, trade-cycle runner, entry-reliability retry logic
  strategy.py           # chain fetch, Greeks, SPX data, leg selection, credit validation
  monitor.py            # quote streaming, profit exits, time exits, EOD expiration
  logger.py             # CSV logging and schema migration
  jade_lizard.py        # multi-day short put + bear call spread strategy
  premium_popper.py     # legacy ORB strategy (disabled, retained as rollback artifact)

main.py                 # root compatibility wrapper — delegates to tasty0dte.main
strategy.py             # root compatibility wrapper
monitor.py              # root compatibility wrapper
project_paths.py        # all filesystem paths in one place (read this before hardcoding paths)

tests/                  # unit tests (unittest, not pytest)
analysis/               # performance review scripts
  common.py             # shared filters, DST normalisation, stat helpers — import from here
  performance_report.py # cross-strategy leaderboard
  strategy_metrics.py   # deep per-strategy metrics
  exit_analysis.py      # exit-reason breakdown
  strategy_dashboard.py # per-strategy HTML dashboard
  overview_dashboard.py # full roster HTML dashboard
  dedup_trades.py       # find/remove duplicate trade rows
  regenerate_site_data.py # rebuild public_site/data.js
  generate_bt_dashboard.py # backtest vs live dashboard generator

data/
  paper_trades.csv      # trade ledger — never truncate, only append or correct
  live_trades.csv       # manual live trade entries for comparison
  skip_events.csv       # ORB skip-event log

runtime/
  logs/trade.log        # authoritative bot log
  logs/stdout.log       # live monitor loop output (updates every 10s)
  logs/stderr.log       # noisy, partially unstamped — prefer trade.log
  logs/cron.log         # cron start/stop events
  state/.spx_cache.json # SPX price cache for EOD settlement fallback

orb_stacking/           # ORB Stacking package (disabled, net-negative, all 15 slices built)
tools/                  # manual probes, backtest runners, live tracker
dashboard/              # Flask read-only monitoring dashboard (port 5050)
docs/                   # proposals and design notes
local/                  # Discord + X notifiers (gitignored; can be None)
```

---

## 3. Setup

```bash
git clone <repo>
cd tasty0dte-ironcondor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env:
# TASTY_REFRESH_TOKEN=...
# TASTY_CLIENT_SECRET=...
# TASTY_ACCOUNT_ID=...
# DISCORD_WEBHOOK_URL_0DTE=...  (optional)
```

All paths resolve through `project_paths.py`. Check it before hardcoding any path. Env vars (`TASTY_PAPER_TRADES_CSV`, `TASTY_TRADE_LOG`, etc.) override defaults.

---

## 4. Running the bot

### Foreground (development/debug)
```bash
./run_autotrader.sh          # activates venv + caffeinate
# or directly:
venv/bin/python main.py
```

### Background (production)
```bash
./start.sh     # starts in background, writes PID to runtime/state/bot.pid
./status.sh    # shows process status
./stop.sh      # sends SIGTERM
```

### Verify the bot is live
```bash
ps aux | grep "main.py" | grep -v grep          # PID = alive
tail -f runtime/logs/stdout.log                 # live monitor output, updates ~every 10s
tail -f runtime/logs/trade.log                  # trade events, entries, exits
```

---

## 5. Architecture and execution flow

### Session lifecycle
```
main() → Session(provider_secret=..., refresh_token=...)
       → single persistent session, never recreated
       → while True loop, checks UK time every 10s
         → on trigger time (15:00 or 15:30 UK): execute_trade_cycle()
         → always: monitor.check_open_positions() + monitor.check_eod_expiration()
```

### Trade cycle (execute_trade_cycle in tasty0dte/main.py)
1. Run each Jade Lizard strategy (JL5/JL7/JL10) in isolation — per-strategy try/except
2. Fetch 0DTE SPX option chain (retry up to 3× with 3s delay)
3. Filter for today's expiration
4. For each 0DTE strategy (Iron Fly V1–V4):
   - Select legs (`find_iron_fly_legs` in strategy.py)
   - Fetch leg prices via REST (not DXLink)
   - Run `validate_credit_sanity` (see Section 6)
   - Retry up to 3× (6s delay) on validation failure — stale marks normalize
   - If valid: log to CSV, notify Discord
   - If rejected: Discord skip alert, continue to next strategy

### Monitor loop (monitor.py:check_open_positions)
- Runs every 10s
- Streams DXLink Quote events for all open leg symbols
- Calculates debit-to-close and P/L
- Closes on: profit target, stop loss, time exit, or ORB60 force-close signal
- Multi-day strategies (Jade Lizard): require 4h minimum hold + fresh quotes before closing

### EOD expiration (monitor.py:check_eod_expiration)
- Triggers when UK time ≥ 21:00
- Fetches SPX close via: REST API → DXLink Summary → cached price
- Calculates intrinsic settlement value per leg, writes EXPIRED + Exit P/L

---

## 6. Active strategy set

All times are **UK (Europe/London)** — adjust for DST (see Section 11).

| Strategy | Code | Structure | Entry (UK) | Profit Target | Wing | Status |
|---|---|---|---|---|---|---|
| Iron Fly V1 | IF-V1 | ATM fly | 15:00 | 10% | 10pt | **ACTIVE — best** |
| Iron Fly V2 | IF-V2 | ATM fly | 15:00 | 20% | 10pt | **ACTIVE** |
| Iron Fly V3 | IF-V3 | ATM fly | 15:30 | 10% | 10pt | **ACTIVE** |
| Iron Fly V4 | IF-V4 | ATM fly | 15:30 | 20% | 10pt | **ACTIVE** |
| JadeLizard_5DTE | JL5 | short put + call spread | 15:00 | 25% | — | **ACTIVE** |
| JadeLizard_7DTE | JL7 | short put + call spread | 15:00 | 25% | — | **ACTIVE** |
| JadeLizard_10DTE | JL10 | short put + call spread | 15:00 | 25% | — | **ACTIVE** |
| Dynamic 0DTE | DY-0D | adaptive IC/IF | 15:00 | 20% | — | DISABLED 2026-06-05 |
| ORB Stacking | — | ORB credit spreads | background | 50% | — | DISABLED 2026-06-05 |
| Premium Popper | PP-ORB | ORB credit spread | — | 50% | — | Retired ~2026-04-09 |

**Performance summary (CSV-derived, 2026-06-18 snapshot):**
- Iron Fly V1: +$62.37 / 94 trades / 74.5% WR — **most statistically significant** (t=5.06)
- Iron Fly V2: +$47.16 / 93 / 55.9% WR — significant (t=2.88)
- Iron Fly V3: +$32.07 / 87 / 67.8% WR — not significant (t=1.35)
- Iron Fly V4: +$9.40 / 83 / 53.0% WR — not significant
- Best entry window: Open+0:30 (15:00 UK) > Open+1:00 (15:30 UK). 10% PT > 20% PT.

**Removed strategies (2026-03-22) — do not re-enable:**
- 20 Delta IC: -$54.68 / 146 trades despite 89.7% WR (payoff 0.09 — pennies in front of steamroller)
- 30 Delta IC: -$45.88 / 171 trades
- Gap Filter 20D: -$60.56 / 18 trades (catastrophic tail losses, avg loss -$27.52)

To re-enable a disabled strategy, uncomment its dict in `STRATEGY_CONFIGS` in `tasty0dte/main.py`.

---

## 7. Key files and their purposes

### `tasty0dte/main.py`
- `STRATEGY_CONFIGS` — list of dicts defining all strategies. **This is where strategies are enabled/disabled.**
- `PARITY_RETRY_ATTEMPTS = 3` — retries on stale-mark rejection before skipping
- `execute_trade_cycle()` — runs JL loop then 0DTE loop, fully isolated per-strategy
- `_build_validated_trade()` — retries leg selection + validation with fresh marks
- `_fetch_chain_with_retry()` — retries chain fetch 3× before conceding
- `_notify_skip()` / `_notify_0dte_cycle_skip()` — Discord alerts on every skip

### `tasty0dte/strategy.py`
- `validate_credit_sanity()` — two guards: max-credit (no-arb) + put-call parity
- `PARITY_TOLERANCE = 4.00` — dollars; raised from $2 on 2026-06-24 for opening put skew
- `find_iron_fly_legs()` — ATM selection via delta closest to 0.50, wing by width
- `find_iron_condor_legs()` — short legs by target delta, 20pt wings
- `_fetch_leg_prices()` — REST API (`get_market_data_by_type`) for leg prices, NOT DXLink
- `get_spx_spot()` — DXLink Quote → Trade fallback, 2 retries
- `get_spx_close()` — REST → dxFeed Summary → cache (for EOD settlement)
- `save_spx_price()` / `get_cached_spx_price()` — SPX price cache in `runtime/state/.spx_cache.json`
- `_unwrap_awaitable()` — handles SDK version differences (sync vs async return)

### `tasty0dte/monitor.py`
- `check_open_positions()` — main monitor loop: streaming, P/L calc, profit-target/stop/time exits
- `check_eod_expiration()` — settlement at 21:00 UK
- `FORCE_CLOSE_REASONS` — dict written by ORB Stacking to signal forced closes
- `is_market_closed()` — returns True when UK time ≥ 21:00
- `MULTI_DAY_MIN_HOLD_HOURS = 4.0` — minimum hold for Jade Lizard before closing

### `tasty0dte/logger.py`
- `HEADER` — canonical CSV column order (20 columns); auto-migrates old files on startup
- `log_trade_entry()` — appends one row; normalises IV Rank to 0-1 ratio
- `log_skip_event()` — appends to `data/skip_events.csv`

### `tasty0dte/jade_lizard.py`
- `execute_jade_lizard()` — fetches implied volatility, places expected-move strikes on 5pt grid
- Expected move formula: `spot × IV × √(DTE/365) × 0.68` (tastytrade's ±0.68σ interval)
- Strikes: `SP = round5(spot - EM)`, `LP = SP - 20`, `SC = round5(spot + EM)`, `LC = SC + 5`
- Credit floor: $4.50 (do not raise to $5.00 — user accepts thin upside risk)
- Notes field stores: `target_expiry=YYYY-MM-DD;dte=N;em=NN.NN` for multi-day tracking

### `project_paths.py`
- All runtime paths centralised here. **Always import from this file, never hardcode paths.**
- `PAPER_TRADES_CSV`, `TRADE_LOG`, `SPX_CACHE_JSON`, `BOT_PID`, etc.
- Env vars override defaults (e.g. `TASTY_PAPER_TRADES_CSV`)

### `analysis/common.py`
- `load_trades()` — load CSV with standard filters applied (closed-only, private excluded, outliers dropped)
- `streaks()`, `drawdown_episodes()` — stat helpers
- `iv_bin()`, `move_bin()`, `exit_window_bin()` — categorisation
- **Always import from here in analysis scripts; never re-implement filters inline.**

---

## 8. Guard and validation logic

### Two-layer credit sanity guard (`strategy.py:validate_credit_sanity`)

Called before every 0DTE trade. Returns `(is_valid: bool, reason: str)`.

**Guard 1 — No-arbitrage / max-credit:**
```python
if credit >= wing_width - 0.25:
    return False, "arbitrage territory"
```
A 10pt fly cannot credit $9.75+ — that's impossible to fill and indicates corrupt marks.

**Guard 2 — Put-call parity (ATM iron flies only):**
```python
observed = call_price - put_price
expected = spx_spot - strike          # by put-call parity at ATM
drift = abs(observed - expected)
if drift > PARITY_TOLERANCE (=$4.00):
    return False, "parity violation"
```
Opening put skew on SPX ATM options can legitimately reach $3–4 at the 15:00 ET open — that's why the tolerance is $4.00, not $2.00. Only reject if drift exceeds this. Guard 1 independently catches truly impossible marks.

**Retry logic (tasty0dte/main.py:_build_validated_trade):**
On validation failure, re-fetch fresh marks and re-validate up to 3 times (6s delay). Stale REST marks at the open typically normalize within 6–12 seconds. If still invalid after 3 attempts, skip and send Discord alert.

### Quote sanity guard (monitor.py:check_open_positions)
```python
if debit_to_close < -0.01 or current_profit > initial_credit + 0.01:
    # skip close — corrupt/stale quotes
```
Prevents phantom profit-target hits from dropped/reconnected streams.

### Multi-day close guards (Jade Lizard)
1. Minimum hold: 4 hours after entry before any profit-target close
2. Quote freshness: all 4 leg quotes must have `bid_time` within 60s
3. Target expiry: EOD settlement only fires on the day `target_expiry` in Notes matches `today`

---

## 9. CSV schema

`data/paper_trades.csv` columns (order matters for migration):
```
Date, Entry Time, Symbol, Strategy, StrategyId,
Short Call, Long Call, Short Put, Long Put,
Credit Collected, Buying Power, Profit Target, Stop Loss,
Status, Exit Time, Exit P/L, Notes, IV Rank,
Short Delta, SPX Spot
```

- `Status`: `OPEN` | `CLOSED` | `EXPIRED`
- `IV Rank`: stored as 0–1 ratio (multiply by 100 for display only)
- `Notes` for Jade Lizard: `target_expiry=YYYY-MM-DD;dte=N;em=NN.NN`
- `StrategyId` format: `{CODE}-{HHMM}` e.g. `IF-V1-1500`
- Leg symbols: DXLink streamer format for `Short Call` / `Long Call` / `Short Put` / `Long Put`
- OCC symbols stored in legs dict as `occ_symbol` for REST price fetches — format: `SPX YYMMDD{C|P}{strike}`

**Data quality notes:**
- IV Rank was mixed-scale (0-1 ratio vs 0-100 pct) before 2026-06-04; backfilled by `analysis/normalize_iv_rank.py`
- Worst V1 trade (-$4.25, 2026-02-20) is a stale-auto-expire artifact, not a real loss
- 5 anomalous-credit rows (2026-03-20, credit 7-8× normal) are excluded by `common.load_trades()` default filter

---

## 10. Testing

Framework: `unittest` (not pytest). Test files named `test_*.py`.

```bash
# Run all tests
venv/bin/python -m unittest discover -v

# Run specific test files
venv/bin/python -m unittest tests/test_strategy tests/test_monitor -v

# ORB Stacking tests (separate discover root)
venv/bin/python -m unittest discover -s orb_stacking/tests -t . -v

# Syntax check all Python files
venv/bin/python -m py_compile main.py strategy.py monitor.py logger.py tasty0dte/*.py tools/*.py analysis/*.py
```

Test files in `tests/`:
- `test_strategy.py` — leg selection, chain filtering, SPX spot fetch
- `test_fly_legs.py` — iron fly wing selection, tie-break logic
- `test_credit_sanity.py` — both validation guards, edge cases
- `test_monitor.py` — P/L calculation, time exits, EOD expiration
- `test_jade_lizard.py` — expected-move formula, strike grid, credit floor
- `test_monitor_jade_lizard.py` — multi-day hold, quote freshness, target expiry
- `test_entry_reliability.py` — retry logic, chain fetch retries, per-strategy isolation
- `test_logger.py` — IV Rank normalisation, CSV migration
- `test_project_paths.py` — path resolution
- `test_module_wrappers.py` — root compatibility wrappers delegate correctly

**Critical rules:**
- Do NOT run bot tests while the bot is live — they share `trade.log`'s FileHandler and pollute it with fake data
- Tests must use `datetime.now()` for the `Date` column — stale-trade detection expires rows from prior days
- Always test imports against `venv/bin/python`, not system Python (SDK versions differ: v11.1.0 vs v12.0.0)

---

## 11. Analysis tools

### Weekly update workflow
```bash
venv/bin/python analysis/dedup_trades.py          # check for duplicates (Discord double-fires)
venv/bin/python analysis/dedup_trades.py --apply  # if duplicates found
venv/bin/python analysis/regenerate_site_data.py  # rebuild public_site/data.js
# then deploy public_site/ to Cloudflare Pages
```

### Performance reports
```bash
venv/bin/python analysis/performance_report.py            # cross-strategy leaderboard
venv/bin/python analysis/strategy_metrics.py "Iron Fly V1" --bucket 30
venv/bin/python analysis/exit_analysis.py "Iron Fly V1"
```

### HTML dashboards
```bash
venv/bin/python analysis/overview_dashboard.py --open     # whole roster
venv/bin/python analysis/strategy_dashboard.py "Iron Fly V1" --open

# Jade Lizard (private strategy, needs flag)
venv/bin/python analysis/strategy_dashboard.py "JadeLizard_5DTE" --include-private --open
```

### Default filters applied by all analysis scripts
- `Status` is `CLOSED` or `EXPIRED` with non-null `Exit P/L`
- Private strategies excluded: `Premium Popper`, `ORB-STACK-*`, `JadeLizard_*`
- Outliers excluded: `Credit Collected > $30`
- Override with `--include-private` or `--keep-outliers`

### Backtesting
- Backtest results: `data/v1_bt_cache.json` (1020 sessions)
- Dashboard: `analysis/generate_bt_dashboard.py` → `analysis/dashboard_bt_vs_live.html`
- Deployed at: `bot.w0lverine.uk` (Cloudflare Pages project `tasty-bt-dashboard`)
- Deploy: `npx wrangler pages deploy analysis/pages_deploy --project-name tasty-bt-dashboard`

---

## 12. Cron / scheduling setup

**Live crontab (runs on macOS host):**
```cron
30 14 * * 1-5  cron_start.sh  >> cron.log 2>&1   # start bot 14:30 UK
15 21 * * 1-5  cron_stop.sh   >> cron.log 2>&1   # stop bot 21:15 UK
40 14 * * 1-5  cron_gap_check.sh                  # gap analysis
```

**What cron_start.sh does:** sources venv, runs `./run_autotrader.sh` in background with `caffeinate -i`, writes PID.

**market_session_guard.sh:** independent watchdog that polls `tastytrade.com/market-time` via `curl` every 5 minutes. Its log (`guard_stderr.log`) has **no timestamps** and accumulates stale curl errors from days ago — **do not treat errors there as current**. The guard is completely separate from the bot's SDK session; guard failures do not affect the running bot.

**LaunchAgent (macOS):** `com.example.tasty0dte.plist` provides KeepAlive-style auto-launch. This is in addition to cron; check both if diagnosing unexpected restarts.

---

## 13. DST considerations

**Market open in UK time:**
- US summer (Mar–Nov US DST): 13:30 UK (US ET = UTC-4)
- US winter (Nov–Mar US DST end): 14:30 UK (US ET = UTC-5)
- UK summer only matters when clocks differ

**Current state (as of 2026-06-24):** Both US + UK on summer time. Bot entry times:
- `time(15, 0)` = Open+1:30 (not Open+0:30) — wait, let me be precise:
  - Market opens 13:30 UK
  - `target_times = [time(15, 0), time(15, 30)]` in `tasty0dte/main.py`
  - 15:00 UK = Open+1:30 ... actually 13:30 + 1:30 = 15:00 ✓ (Open+1:30 from clock open, but bot logic calls it "Open+0:30" referencing 30min after the first 15:00 entry window — this is confusing; the bot fires at 15:00 and 15:30 UK regardless)

**When US DST ends (Nov 1, 2026):** market open shifts to 14:30 UK. You must update `target_times` in `tasty0dte/main.py` AND `allowed_times` in `STRATEGY_CONFIGS`. **Both must be updated together** — the 2026-03-30 bug was updating one and missing the other.

**DST audit checklist (run before any time change):**
```bash
grep -rn "time(" tasty0dte/*.py                    # all time() objects
grep -rn "hour ==" tasty0dte/*.py                  # all hour comparisons
crontab -l                                          # cron times
```
`market_session_guard.sh` uses the API (dynamic) — no change needed.

---

## 14. Log hierarchy — read this before diagnosing

**Diagnosis order — stop at the first source that answers the question:**

1. **Is the bot running?**
   ```bash
   ps aux | grep "main.py" | grep -v grep
   ```

2. **What is it doing?** (trusted, bot-owned)
   - `runtime/logs/trade.log` — authoritative structured log: entries, exits, IV Rank, chain fetches, guard rejections
   - `runtime/logs/stdout.log` — live monitor loop; refreshes every 10s with open trades and current P/L

3. **Did anything break today?**
   ```bash
   grep "^2026-06-24" runtime/logs/trade.log | grep -iE "error|warning|exception|traceback|failed"
   ```

4. **Persistent state:**
   - `data/paper_trades.csv` — all trades (open + closed)
   - `runtime/state/.spx_cache.json` — last-known SPX spot

5. **Logs to IGNORE / heavily discount:**
   - `guard_stderr.log` — no timestamps, stale curl errors, NOT the bot
   - `runtime/logs/stderr.log` — noisy, partially unstamped
   - `cron.log` — cron wrapper only

**"Missing trades" ≠ bot down.** First grep `trade.log` for `REJECTED` or `Trade cycle failed`.

---

## 15. Self-improvement loop

After any bug or incident:
1. Update `memory/projects/0dte-bot.md` with: what went wrong, the fix, prevention steps
2. Review `CLAUDE.md` "Bugs Fixed" section — pattern: root cause → fix → test added
3. Add a regression test in `tests/`
4. Commit with a `fix:` prefix and descriptive message

When adding a new strategy:
1. Add config dict to `STRATEGY_CONFIGS` (disabled initially, commented out)
2. Implement leg-selection logic in `strategy.py`
3. Add test coverage in `tests/`
4. Paper-trade for at least 30 sessions before assessing
5. Evaluate by: expectancy + t-statistic + return-on-capital (not just win rate or total P/L)

---

## 16. Gotchas and sharp edges

### SDK version
- venv has tastytrade **v12.0.0**: `get_market_data_by_type()` (no `a_` prefix)
- System Python may have v11.1.0: `a_get_market_data_by_type()` (with `a_` prefix)
- **Always run via `venv/bin/python`**, never `python3` or `python`

### get_mark() can return None
Always check before `float()`. Zero mark is logged as a warning; zero price propagates to credit = 0 which will fail the no-arb guard.

### Leg symbol formats
Two formats, used differently:
- DXLink streamer format (`symbol`): e.g. `.SPXW260624P07390` — used in CSV columns (Short Call etc.) and streaming subscriptions
- OCC format (`occ_symbol`): e.g. `SPX 260624P07390` — used for REST price fetches in `_fetch_leg_prices()`
Both must be set on leg dicts. Missing `occ_symbol` means REST fetch returns nothing and price = $0.

### ExceptionGroup / asyncio.TaskGroup
Python 3.11+ `ExceptionGroup` wraps sub-exceptions. **Always use `exc_info=True` on `logger.error()`** — without it, the real error is invisible. The 2026-04-10 ORB Stacking crash ran silently for 62s because of this.

### IV Rank scale
Stored in CSV as 0–1 ratio. Multiply by 100 only for display. `log_trade_entry()` guards: if `ivr_val > 1.5`, divides by 100. `analysis/common.iv_bin()` expects 0–1 ratio.

### `return` vs `continue` in strategy loop
Using `return` in the per-strategy loop aborts ALL remaining strategies. Use `continue` to skip one and proceed to the next.

### Bare `except:`
Catches `SystemExit` and `KeyboardInterrupt`. Always use `except Exception:` (the codebase follows this rule; don't regress it).

### SPX after-hours data
REST API (`get_market_data_by_type(session, indices=["SPX"])`) works after close. DXLink streaming is for market hours only. For settlement, always use REST as the primary source.

### `discord_notify` can be None
The `local/` module is gitignored. All callers guard: `if discord_notify: ...` or wrap in try/except. Never call methods without checking first.

### Testing while bot is live
Tests in `tests/` that write to `trade.log` share the bot's `FileHandler` — this pollutes the live log with fake entries. **Do not run live-bot tests during trading hours.** `orb_stacking/tests/` (tag-n-turn tests) are safe.

### CSV date precision
`float_format='%.2f'` in `df.to_csv()` rounds all floats to 2dp. Values within ~$0.005 of an IV bin boundary may sit in the wrong bin.

### Jade Lizard credit floor
`$4.50` — do not suggest raising to $5.00. The user deliberately accepts thin upside risk above the long call.

### ORB Stacking disabled
All 15 slices are built and tested (343 tests pass), but the strategy is disabled in `main.py` because it was net-negative (-$16 / 75 trades). To re-enable: uncomment in `main.py`'s main loop. The `orb_stacking/` package is fully functional.

### Analysis default filter excludes private strategies
`JadeLizard_*`, `Premium Popper`, `ORB-STACK-*` are excluded by default. Pass `--include-private` for personal analysis of these.

### Multi-day strategy dispatch order
`execute_trade_cycle()` runs Jade Lizard **before** the 0DTE chain fetch. This is intentional — JL doesn't need the chain, and the early return on chain failure would otherwise skip JL.

---

## 17. Tastytrade SDK patterns

```python
# Session (one-time, never recreate)
session = Session(provider_secret=client_secret, refresh_token=refresh_token)

# Handle sync-or-async SDK returns
result = await _unwrap_awaitable(get_market_metrics(session, ["SPX"]))

# REST price fetch (reliable, works at open)
market_data = await _unwrap_awaitable(
    get_market_data_by_type(session, options=["SPX 260624C07400"])
)
price = md.mark or md.mid or (md.bid + md.ask) / 2

# REST index price (for settlement)
market_data = await _unwrap_awaitable(
    get_market_data_by_type(session, indices=["SPX"])
)
spx_close = md.day_close or md.close or md.last

# DXLink streaming (long-lived, avoid churn)
async with DXLinkStreamer(session) as streamer:
    await streamer.subscribe(Greeks, symbols)
    async for event in streamer.listen(Greeks):
        events = event if isinstance(event, list) else [event]  # always normalize to list
        for e in events:
            if isinstance(e, Greeks):
                greeks_data[e.event_symbol] = e

# Error logging (always exc_info=True for tracebacks)
logger.error(f"Failed: {type(e).__name__}: {e}", exc_info=True)
```

---

## 18. Multi-model build workflow

For non-trivial changes (new strategy, entry logic changes, exit logic changes):
1. **Opus plans** — write a proposal in `docs/proposals/YYYY-MM-DD-topic.md`
2. **Codex/Haiku builds** — implement according to plan
3. **Sonnet reviews** — check deviation from plan, correctness
4. **Opus signs off** — final quality gate
5. **Codex independent review** — catch anything missed

For small fixes (under 20 lines, clear root cause): single-agent is fine.
