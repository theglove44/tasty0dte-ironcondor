# Tasty0DTE: Automated Iron Condor & Iron Fly Trader

**Tasty0DTE** is an automated trading bot designed for **0DTE (Zero Days to Expiration)** strategies on **SPX**, utilizing the Tastytrade API. It automates the entire lifecycle of the trade: identifying opportunities at specific times, entering high-probability setups, monitoring P/L in real-time, and executing disciplined exits.

> [!NOTE]
> This application runs in **Paper Trading Mode** by default, logging "fills" to `paper_trades.csv` instead of sending live orders.

---

## Key Features

- **Automated Entry**: Precise entry execution at **14:45**, **15:00**, and **15:30** (UK Time).
- **Multiple Strategies**: Supports both **Iron Condor** (Delta-based) and **Iron Fly** variants.
- **Smart Management**:
    - **Take Profit**: Automatically closes at predetermined profit targets (e.g., 25%).
    - **Time Exits**: Enforces hard exits (e.g., 18:00 UK) for specific strategies to avoid end-of-day risks.
    - **EOD Handling**: Manages settlement and expiration for positions held into the close.
- **Real-Time Monitoring**: Streams live quotes to track position value and trigger exits instantly.
- **Resilient Design**: Handles network interruptions gracefully — logs errors and continues running.
- **Discord Notifications**: Sends trade open/close alerts via webhook.

---

## Strategies

The bot operates on **SPX** and currently implements the following strategy variants:

| Strategy | ID Prefix | Entry Time (UK) | Structure | Profit Target | Time Exit | EOD Exit |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **20 Delta IC** | `IC-20D` | 14:45, 15:00, 15:30 | Short ~20 Delta, Wings $20 | 25% | None | Yes (21:00) |
| **30 Delta IC** | `IC-30D` | 14:45, 15:00, 15:30 | Short ~30 Delta, Wings $20 | 25% | **18:00** | No |
| **Iron Fly V1** | `IF-V1` | 15:00 | ATM Short, Wings $10 | 10% | None | Yes (21:00) |
| **Iron Fly V2** | `IF-V2` | 15:00 | ATM Short, Wings $10 | 20% | None | Yes (21:00) |
| **Iron Fly V3** | `IF-V3` | 15:30 | ATM Short, Wings $10 | 10% | None | Yes (21:00) |
| **Iron Fly V4** | `IF-V4` | 15:30 | ATM Short, Wings $10 | 20% | None | Yes (21:00) |

---

## Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/theglove44/tasty0dte-ironcondor.git
    cd tasty0dte-ironcondor
    ```

2.  **Set Up Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configuration**
    Create a `.env` file with your Tastytrade credentials (template provided in `.env.example`).
    ```bash
    cp .env.example .env
    ```
    *Required: `TASTY_REFRESH_TOKEN`, `TASTY_CLIENT_SECRET`, `TASTY_ACCOUNT_ID`.*

---

## Usage

### Quick Start (Manual)

```bash
./start.sh      # Start the bot in background
./status.sh     # Check if running
./stop.sh       # Stop the bot
```

Or run directly in foreground:
```bash
./run_autotrader.sh
```

### Automated via Cron (Recommended)

The bot can be scheduled to start and stop automatically on trading days:

```bash
# Add to crontab (crontab -e):

# Start at 14:30 UK (15 mins before first entry)
30 14 * * 1-5 /path/to/tasty0dte-ironcondor/cron_start.sh >> /path/to/cron.log 2>&1

# Stop at 21:15 UK (after EOD handling)
15 21 * * 1-5 /path/to/tasty0dte-ironcondor/cron_stop.sh >> /path/to/cron.log 2>&1
```

| Time (UK) | Action | Days |
|-----------|--------|------|
| 14:30 | Start bot | Mon-Fri |
| 21:15 | Stop bot | Mon-Fri |

**Note:** The cron scripts automatically skip weekends.

---

## Architecture

### Design Principles

This bot follows a **simple, resilient architecture**:

1. **One Session**: A single Tastytrade session is created at startup and reused throughout.
2. **SDK Auto-Refresh**: The tastytrade SDK handles token refresh automatically — no manual session management needed.
3. **Graceful Error Handling**: Network errors are logged and the bot continues running. No crashes, no aggressive restarts.
4. **Persistent State**: Open positions are stored in `paper_trades.csv` and survive restarts.

### Why This Design?

Previous versions used complex "reliability" features (session guards, KeepAlive restarts, network pre-checks) that actually **caused reliability problems** by hammering the Tastytrade API during outages. The current design is simpler and more robust:

- If the network drops for 5-10 minutes, the bot logs warnings and keeps trying
- When connectivity returns, monitoring resumes automatically
- No IP blacklisting from excessive auth requests

---

## Monitoring & Tools

| Command | Description |
| :--- | :--- |
| `./status.sh` | Check if bot is running |
| `tail -f stdout.log` | Watch live bot output |
| `tail -f trade.log` | Watch trade-specific logs |
| `python view_trades.py` | Formatted table of all trades |
| `python analyze_performance.py` | Win rates, P/L, and expectancy |
| `python check_metrics.py` | Verify API connectivity |
| `python monitor_live.py` | Read-only view of open positions |

### Log Files

| File | Contents |
|------|----------|
| `stdout.log` | Main bot output |
| `stderr.log` | Error output |
| `trade.log` | Trade entries and exits |
| `cron.log` | Cron job start/stop messages |
| `paper_trades.csv` | Trade database |

---

## Discord Notifications

Configure webhook URL in `.env`:
```bash
DISCORD_WEBHOOK_URL_0DTE=https://discord.com/api/webhooks/...
```

Notifications include:
- Trade open alerts with strikes, credit, wing width, IV Rank
- Trade close alerts with P/L and exit reason
- EOD expiration settlements

---

## Configuration

### Environment Variables (`.env`)

| Variable | Required | Description |
| :--- | :--- | :--- |
| `TASTY_REFRESH_TOKEN` | Yes | OAuth refresh token from Tastytrade |
| `TASTY_CLIENT_SECRET` | Yes | OAuth application provider secret |
| `TASTY_ACCOUNT_ID` | Yes | Tastytrade account number |
| `DISCORD_WEBHOOK_URL_0DTE` | No | Discord webhook URL for trade notifications |

### Project Files

| File | Description |
| :--- | :--- |
| `main.py` | Main entry point and trading loop |
| `strategy.py` | Option chain fetching and leg selection |
| `monitor.py` | Position monitoring and exit management |
| `logger.py` | Trade logging to CSV |
| `start.sh` | Start bot in background |
| `stop.sh` | Stop bot gracefully |
| `status.sh` | Check bot status |
| `cron_start.sh` | Cron job for automated start |
| `cron_stop.sh` | Cron job for automated stop |
| `run_autotrader.sh` | Direct run wrapper with caffeinate |

---

## Troubleshooting

### Bot won't start
1. Check `.env` file has valid credentials
2. Check `stderr.log` for errors
3. Verify venv is set up: `source venv/bin/activate && pip install -r requirements.txt`

### Network errors in logs
This is normal during connectivity issues. The bot will:
- Log the error
- Wait 10-30 seconds
- Retry automatically

No action needed unless errors persist for extended periods.

### Checking bot health
```bash
./status.sh              # Is it running?
tail -20 stdout.log      # Recent activity
tail -20 trade.log       # Recent trades
```

---

## Paper Trading Mode

The bot runs in **Paper Trading Mode** by default — trades are logged to `paper_trades.csv` instead of being sent to the Tastytrade API. This is suitable for:

- Strategy validation
- Performance tracking
- Testing new configurations
- Learning the system

---

## License

MIT

---

**Important:** Never commit `.env` to version control — it contains sensitive credentials.
