# Tasty0DTE — Automated SPX 0DTE Credit Strategy Bot

Automated **paper-trading** bot for SPX 0DTE credit strategies using the Tastytrade API.

It handles:
- timed entries
- live quote monitoring
- profit-target exits
- strategy-specific time exits
- end-of-day expiration settlement
- CSV-based trade logging and performance analysis

> [!IMPORTANT]
> This project runs in **paper mode** (logs to `paper_trades.csv`). It does **not** place live orders in its current implementation.

---

## Current Strategy Set (from code)

Entry scheduler triggers at **14:45, 15:00, 15:30 UK**.

| Strategy | Code | Type | Entry Times (UK) | Profit Target | Time Exit | EOD Settlement |
|---|---|---|---|---:|---|---|
| 20 Delta | `IC-20D` | Iron Condor | 14:45, 15:30 | 25% | None | Yes (if still open) |
| 30 Delta | `IC-30D` | Iron Condor | 14:45, 15:00, 15:30 | 25% | 18:00 UK | Usually no (closed earlier) |
| Iron Fly V1 | `IF-V1` | Iron Fly | 15:00 | 10% | 18:00 UK | Usually no (closed earlier) |
| Iron Fly V2 | `IF-V2` | Iron Fly | 15:00 | 20% | 18:00 UK | Usually no (closed earlier) |
| Iron Fly V3 | `IF-V3` | Iron Fly | 15:30 | 10% | 18:00 UK | Usually no (closed earlier) |
| Iron Fly V4 | `IF-V4` | Iron Fly | 15:30 | 20% | 18:00 UK | Usually no (closed earlier) |
| Gap Filter 20D | `GF-20D` | Iron Condor | 15:00, 15:30 | 25% | None | Yes (if still open) |
| Dynamic 0DTE | `DY-0D` | Adaptive IC/IF | 15:00 | 20% | 20:55 UK | Possible (if still open) |

### Dynamic 0DTE logic
At 15:00 UK, bot checks SPX move from day open:
- if 30-min move `> -0.1%` → choose IC config (20Δ, 20pt wings)
- else → choose IF config (50Δ ATM, 10pt wings)

### Gap Filter logic (GF-20D)
Uses overnight SPX gap class:
- **Trade** on large up gap (`> +0.5%`) or flat (`-0.2% to +0.2%`)
- **Skip** on small up (`+0.2% to +0.5%`) and all down gaps

---

## Requirements

- Python 3.11+
- macOS recommended (scripts use `caffeinate`)
- Tastytrade API credentials

`requirements.txt` includes:
- `tastytrade`
- `pandas`
- `python-dotenv`
- `websockets`
- `pytz`
- `flask` (dashboard)

---

## Setup

```bash
git clone https://github.com/theglove44/tasty0dte-ironcondor.git
cd tasty0dte-ironcondor

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Set required vars in `.env`:
- `TASTY_REFRESH_TOKEN`
- `TASTY_CLIENT_SECRET`
- `TASTY_ACCOUNT_ID`

Optional:
- `DISCORD_WEBHOOK_URL_0DTE`

---

## Run Modes

### 1) Foreground (simplest)
```bash
./run_autotrader.sh
```

### 2) Background helper scripts
```bash
./start.sh
./status.sh
./stop.sh
```

### 3) Cron automation (recommended)
Example:
```cron
# Start before first entry (UK time)
30 14 * * 1-5 /path/to/tasty0dte-ironcondor/cron_start.sh >> /path/to/tasty0dte-ironcondor/cron.log 2>&1

# Stop after EOD settlement window
15 21 * * 1-5 /path/to/tasty0dte-ironcondor/cron_stop.sh >> /path/to/tasty0dte-ironcondor/cron.log 2>&1
```

---

## Timezone and scheduling notes

- Bot logic uses `Europe/London` timezone in Python.
- Cron expressions above are intended as UK clock times.
- Ensure host timezone / cron timezone matches your intended session timing.

---

## Logs and data

| File | Purpose |
|---|---|
| `paper_trades.csv` | Trade ledger (source of truth) |
| `trade.log` | Bot runtime + trade lifecycle logs |
| `stdout.log` / `stderr.log` | Process output from shell scripts |
| `cron.log` | Start/stop cron events |
| `.spx_cache.json` | Cached SPX price fallback for settlement |

Useful commands:
```bash
tail -f stdout.log
tail -f trade.log
python view_trades.py
python analyze_performance.py
```

---

## Optional dashboard

Read-only Flask dashboard:
```bash
source venv/bin/activate
python dashboard/app.py
```
Open: `http://127.0.0.1:5050`

Shows:
- market/session status
- open positions
- today’s closed trades
- performance metrics
- PDT tracker
- recent errors + cron status

---

## Testing

Run tests with unittest:
```bash
venv/bin/python -m unittest discover -v
```

Syntax check core modules:
```bash
venv/bin/python -m py_compile main.py strategy.py monitor.py logger.py
```

---

## Project map

- `main.py` — main loop, session, strategy execution at trigger times
- `strategy.py` — chain/greeks/quotes, leg selection, gap + dynamic helpers, SPX cache
- `monitor.py` — open-position mark-to-market, profit exits, time exits, EOD settlement
- `logger.py` — CSV initialization/migration and entry logging
- `settle_open_trades.py` — manual settlement utility
- `dashboard/` — Flask monitoring UI

---

## Platform notes

- Shell scripts use `caffeinate` (macOS).
- On Linux, run `python main.py` directly or replace `caffeinate` in scripts.

---

## Safety notes

- Keep `.env` private (never commit credentials).
- Validate changes in paper mode before any live adaptation.
- Confirm EOD settlement outputs in `paper_trades.csv` after each session.
