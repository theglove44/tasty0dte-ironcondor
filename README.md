# Tasty0DTE Iron Condor

Automated **paper-trading bot** for SPX 0DTE option strategies using the **Tastytrade API**.

This project focuses on systematic same-day premium-selling strategies and includes:

- scheduled strategy entries during the US cash session
- live quote monitoring via DXLink / dxFeed
- profit-target exits and time-based exits
- end-of-day handling for positions that remain open
- CSV-based trade logging and performance review tools
- an optional Flask dashboard for monitoring session state and results

> [!IMPORTANT]
> This repository is currently implemented as a **paper-trading system**. It logs trades to `paper_trades.csv` and is designed for strategy testing, monitoring, and iteration rather than live execution.

## What the bot does

At a high level, the bot:

1. starts a single Tastytrade session
2. waits for scheduled entry windows in `Europe/London` time
3. selects option legs for the configured strategy
4. logs the trade to CSV with buying power, credit, and target metrics
5. monitors open positions for profit targets, time exits, and end-of-day settlement logic

The main runtime loop is in `main.py`, with strategy selection in `strategy.py`, position monitoring in `monitor.py`, and CSV logging in `logger.py`.

## Current strategy set

The current codebase includes these strategies:

| Code | Strategy | Structure | Entry windows (UK) | Profit target |
|---|---|---|---|---:|
| `IC-20D` | 20 Delta | Iron Condor | 13:45, 14:30 | 25% |
| `IC-30D` | 30 Delta | Iron Condor | scheduled in main cycle | 25% |
| `IF-V1` | Iron Fly V1 | Iron Fly | 14:00 | 10% |
| `IF-V2` | Iron Fly V2 | Iron Fly | 14:00 | 20% |
| `IF-V3` | Iron Fly V3 | Iron Fly | 14:30 | 10% |
| `IF-V4` | Iron Fly V4 | Iron Fly | 14:30 | 20% |
| `GF-20D` | Gap Filter 20D | Iron Condor | 14:00, 14:30 | 25% |
| `DY-0D` | Dynamic 0DTE | Adaptive IC / IF | 14:00 | 20% |
| `PP-ORB` | Premium Popper | ORB credit strategy | 13:45 launcher | 50% |

### Dynamic 0DTE

The `DY-0D` strategy checks the SPX move from the open and switches structure based on that move:

- stronger/flat early move -> iron condor configuration
- weaker move -> iron fly configuration

### Gap Filter 20D

The `GF-20D` strategy uses the overnight SPX gap to decide whether to trade. In the current implementation it is intended to trade large up-gap or flat-gap conditions and skip weaker / down-gap conditions.

## Repository layout

```text
.
├── main.py                  # scheduler and trade-cycle runner
├── strategy.py              # option-chain, greeks, SPX data, leg selection
├── monitor.py               # quote streaming, profit exits, time exits, EOD logic
├── logger.py                # CSV logging and trade persistence
├── premium_popper.py        # ORB-style strategy task
├── analyze_performance.py   # post-session performance analysis
├── view_trades.py           # quick trade log inspection
├── dashboard/               # Flask monitoring dashboard
├── checks/                  # pre-session checks
├── docs/                    # supporting docs
└── .env.example             # expected environment variables
```

## Requirements

- Python 3.11+
- Tastytrade API credentials
- macOS is the smoothest fit for the helper scripts because they use `caffeinate`

Dependencies in `requirements.txt` currently include:

- `tastytrade`
- `pandas`
- `python-dotenv`
- `websockets`
- `pytz`
- `flask`

## Quick start

```bash
git clone https://github.com/theglove44/tasty0dte-ironcondor.git
cd tasty0dte-ironcondor

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Add your credentials to `.env`:

```env
TASTY_REFRESH_TOKEN=your_refresh_token
TASTY_CLIENT_SECRET=your_client_secret
TASTY_ACCOUNT_ID=your_account_id

# Optional
DISCORD_WEBHOOK_URL_0DTE=https://discord.com/api/webhooks/your_webhook_url
# TWEET_SCRIPT_PATH=/path/to/tweet-trade.py
```

## Running the bot

### Foreground

```bash
./run_autotrader.sh
```

### Background helper scripts

```bash
./start.sh
./status.sh
./stop.sh
```

### Cron automation

Example:

```cron
# Start before the first session trigger (UK time)
30 13 * * 1-5 /path/to/tasty0dte-ironcondor/cron_start.sh >> /path/to/tasty0dte-ironcondor/cron.log 2>&1

# Stop after the end-of-day handling window
15 21 * * 1-5 /path/to/tasty0dte-ironcondor/cron_stop.sh >> /path/to/tasty0dte-ironcondor/cron.log 2>&1
```

## Logs and data files

| File | Purpose |
|---|---|
| `paper_trades.csv` | trade ledger / paper-trading source of truth |
| `trade.log` | runtime events and trade lifecycle logs |
| `stdout.log` | standard output from helper scripts |
| `stderr.log` | error output from helper scripts |
| `cron.log` | cron start / stop events |
| `.spx_cache.json` | cached SPX value used as a settlement fallback |

Useful commands:

```bash
tail -f stdout.log
tail -f trade.log
python view_trades.py
python analyze_performance.py
```

## Dashboard

A lightweight Flask dashboard is included for read-only monitoring.

```bash
source venv/bin/activate
python dashboard/app.py
```

Open `http://127.0.0.1:5050`

The dashboard is intended to surface session status, open positions, closed trades, performance metrics, and recent operational issues.

## Testing

```bash
venv/bin/python -m unittest discover -v
venv/bin/python -m py_compile main.py strategy.py monitor.py logger.py
```

## Known limitations

- currently designed around **paper trading**, not live order placement
- helper shell scripts are geared toward **macOS** because of `caffeinate`
- the codebase is still fairly script-centric rather than packaged as an installable Python project
- the repository would benefit from screenshots, sample output, and a clearer roadmap for contributors

## Roadmap ideas

- add example dashboard screenshots / sample `paper_trades.csv`
- package the bot as a proper Python module with a cleaner CLI
- separate strategy configs into YAML or JSON rather than inline dictionaries
- add CI for tests and linting
- document performance-analysis workflow with example outputs
- add architecture diagram for scheduler, strategy engine, logger, and monitor loop

## Disclaimer

This project is for strategy research, automation practice, and paper-trading workflows. Options trading is risky, and nothing in this repository should be treated as financial advice.
