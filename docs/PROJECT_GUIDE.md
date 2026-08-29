# Project Guide

This is the plain-English map of `tasty0dte-ironcondor`. It is written for the owner of the project. The deeper technical map is in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md); detailed strategy and operational notes remain in [`AI_GUIDE.md`](../AI_GUIDE.md).

## What the project is for

The project runs scheduled SPX options strategies, records simulated trades, watches their prices, and calculates paper-trading results. It is designed for strategy research and monitoring.

It deliberately does not place live orders. The runtime creates a Tastytrade session to read market data, option chains, Greeks, and market metrics, but the current code logs trades to CSV rather than submitting orders.

## How to use it

Set up the virtual environment and `.env` file using [`README.md`](../README.md). The important local commands are:

```bash
./run_autotrader.sh          # foreground bot; macOS caffeinate wrapper
./start.sh                   # background bot
./status.sh                  # inspect the background bot
./stop.sh                    # stop the background bot
venv/bin/python dashboard/app.py  # read-only local dashboard
```

The dashboard normally opens at `http://127.0.0.1:5050`. It reads the ledger, logs, cached SPX price, and PID file; it does not control trades.

The bot's default private data root is controlled by `TASTY_PRIVATE_DATA_ROOT` and defaults to `~/Private/ProjectsData/trading/tasty0dte-ironcondor`. `project_paths.py` is the source of truth for all runtime paths. Do not assume that `data/` or `runtime/` in the repository contains the live records.

## The normal trading-day workflow

1. **Start-up.** A shell helper, cron job, or macOS LaunchAgent starts `main.py`. The root `main.py` is a compatibility wrapper that loads `tasty0dte.main`. The bot validates that the three required credential variables exist, creates one Tastytrade `Session`, and keeps that session for the process lifetime.

2. **Scheduled entries.** In the current code snapshot, the scheduler checks UK time every 10 seconds and triggers cycles at 15:00 and 15:30. The active configuration in `tasty0dte/main.py` currently enables four Iron Fly variants and three Jade Lizard variants. The exact active roster and allowed times live in `STRATEGY_CONFIGS`; do not rely on the older strategy table in `README.md`.

3. **Trade selection.** Each cycle runs Jade Lizard entries first. It then fetches the shared SPX option chain for 0DTE strategies, obtains IV rank and SPX spot, selects option legs, fetches REST marks, checks credit sanity, and logs any accepted paper trade. Failed chains, missing expiries, invalid prices, and per-strategy errors are logged and surfaced as skips where the optional notifier is available.

4. **Position monitoring.** The monitor runs roughly every 10 seconds. It reads `OPEN` rows from the paper ledger, subscribes to DXLink quotes for their legs, calculates the debit needed to close and current profit, and closes paper positions when profit targets, stop losses, or time exits are reached. It rejects obviously corrupt quotes rather than declaring a false profit.

5. **Settlement and review.** After the UK market-close threshold, remaining 0DTE positions are settled from the SPX close. The monitor tries REST data first, then a dxFeed Summary event, then the same-day cached SPX price. Jade Lizard positions use multi-day hold/freshness rules and are intrinsically settled only on their recorded target expiry. The dashboard and analysis scripts then read the ledger for operational and performance review.

## Major parts

| Area | Plain-English responsibility |
|---|---|
| `tasty0dte/main.py` | Runs the scheduler, owns the single Tastytrade session, dispatches strategies, and catches failures so the process can continue. |
| `tasty0dte/strategy.py` | Fetches chains, SPX data, IV/Greeks, option marks, and selects Iron Fly/Iron Condor legs. It contains the credit sanity guards. |
| `tasty0dte/jade_lizard.py` | Builds the multi-day short-put plus bear-call-spread strategy, chooses the target expiry, applies the expected-move calculation, and logs entries. |
| `tasty0dte/monitor.py` | Watches open positions, calculates paper P/L, applies exit rules, and performs end-of-day settlement. |
| `tasty0dte/logger.py` | Creates/migrates the paper-trade CSV and appends entries, exits, and ORB skip events. |
| `dashboard/` | Flask pages and JSON endpoints for read-only status, positions, performance, charts, system health, and PDT tracking. |
| `analysis/` | Offline performance reports and HTML/public-site data builders. See [`analysis/README.md`](../analysis/README.md). |
| `tools/` | Manual probes, backtests, trade inspection, operational utilities, and the optional historical chain-capture workflow. |
| `orb_stacking/` | A separately tested ORB engine and live adapter. It is currently disabled in the main runtime, but remains present as a tested rollback/research path. |

Root modules such as `main.py`, `strategy.py`, `monitor.py`, and `logger.py` are compatibility wrappers. New runtime behaviour belongs in `tasty0dte/`.

## Where data lives

The private root contains the records that should not be committed or shared casually:

- `data/paper_trades.csv` — persistent source of truth for paper entries and exits. Rows use `OPEN`, `CLOSED`, or `EXPIRED` status. The column order is part of the migration contract.
- `data/skip_events.csv` — ORB skip-event records when that optional path is used.
- `runtime/logs/trade.log` — authoritative structured bot log; `stdout.log`, `stderr.log`, and `cron.log` serve operational/helper output.
- `runtime/state/.spx_cache.json` — same-day SPX fallback price for settlement.
- `runtime/state/bot.pid` — PID used by helper scripts and the dashboard to check whether the process exists.
- `data/chain_capture/` — optional Databento parquet captures and derived Greeks sidecars for backtesting.
- `artifacts/` and `reports/` — private generated outputs used by analysis/backtesting.

The dashboard caches the CSV in memory based on its modification time. The bot and monitor write the same CSV that the dashboard and analysis tools read, so schema or path changes affect several parts at once.

## Configuration

Required environment-variable names:

- `TASTY_REFRESH_TOKEN`, `TASTY_CLIENT_SECRET`, `TASTY_ACCOUNT_ID` — Tastytrade authentication and account selection.
- `TASTY_PRIVATE_DATA_ROOT` — common private root for the ledger, captures, state, logs, and reports.

Useful optional variables include `DISCORD_WEBHOOK_URL_0DTE` for notifications, `TWEET_SCRIPT_PATH` for the optional X/Twitter hand-off, `DASHBOARD_HOST` and `DASHBOARD_PORT` for the dashboard listener, and per-file `TASTY_*` path overrides defined in `project_paths.py`.

The historical chain-capture workflow additionally expects `DATABENTO_API_KEY`. The capture/enrichment scripts also check for optional packages such as `databento`, `pyarrow`, `yfinance`, `scipy`, and `numpy`; these are not all declared in the base `requirements.txt`.

## Important rules and calculations

- **Paper-only boundary:** keep all strategy changes paper-only. No order-submission client or order call is part of the current runtime.
- **Credit sanity:** `tasty0dte/strategy.py:validate_credit_sanity` rejects impossible credit and excessive ATM put-call-parity drift. This protects the ledger and exit calculations from stale marks.
- **Expected move:** `tasty0dte/jade_lizard.py:fetch_expected_move` uses SPX spot, the target expiry's IV, time to expiry, and a `0.68` factor before choosing strikes.
- **CSV schema:** `tasty0dte/logger.py:HEADER` defines the canonical 20-column layout. `logger.py` contains migration logic for older ledgers.
- **Time zones:** scheduling and settlement logic use `Europe/London`, while market-data tools may convert to `America/New_York`. Any time change needs a DST audit across Python schedules, allowed strategy times, cron, helper scripts, and ORB time utilities.

## Testing

The project uses Python `unittest`, not pytest:

```bash
venv/bin/python -m unittest discover -v
venv/bin/python -m py_compile main.py strategy.py monitor.py logger.py tasty0dte/*.py tools/*.py analysis/*.py
```

Tests are heavily mocked and are intended to avoid live market calls. Do not run bot tests while the live bot is running: some imports configure a shared file logger, and tests can create misleading log output. In a restricted environment where the default private root is not writable, use the supported `TASTY_PRIVATE_DATA_ROOT` override with a temporary directory.

## Things most likely to break

1. **Time drift.** The scheduler, per-strategy allowed times, cron, dashboard session display, and ORB time utilities do not all share one configuration object.
2. **Duplicate configuration.** `tasty0dte/main.py` is the active strategy source. `dashboard/config.py` contains a separate, currently stale display copy and must not be treated as the trading roster.
3. **Shared CSV changes.** Renaming columns, changing status values, or moving the ledger affects the bot, monitor, dashboard, analysis, and migration code.
4. **Quote freshness.** REST marks, DXLink quotes, and cached settlement prices have different timing and reliability. Do not remove the sanity/freshness guards without a test and a rollback plan.
5. **Optional integrations.** Discord, X/Twitter, Databento, and the local macOS service are outside the core paper ledger and may be absent or unavailable. The bot generally treats notifications as best-effort, but capture/deployment scripts can fail when their dependencies or credentials are missing.

## Where to look next

- [`AI_GUIDE.md`](../AI_GUIDE.md) — detailed strategy, guards, CSV schema, logs, DST notes, and SDK patterns.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — component connections and data flow.
- [`README.md`](../README.md) — initial setup and user-facing commands; verify runtime paths and the active roster against code.
- [`analysis/README.md`](../analysis/README.md) — performance-analysis workflows and default filters.
- [`orb_stacking/SOURCE_OF_TRUTH.md`](../orb_stacking/SOURCE_OF_TRUTH.md) and [`orb_stacking/ROADMAP.md`](../orb_stacking/ROADMAP.md) — ORB research design and history.
