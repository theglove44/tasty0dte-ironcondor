# Tasty0DTE: Automated Iron Condor & Iron Fly Trader

**Tasty0DTE** is an automated trading bot designed for **0DTE (Zero Days to Expiration)** strategies on **SPX**, utilizing the Tastytrade API. It automates the entire lifecycle of the trade: identifying opportunities at specific times, entering high-probability setups, monitoring P/L in real-time, and executing disciplined exits.

> [!NOTE]
> This application runs in **Paper Trading Mode** by default, logging "fills" to `paper_trades.csv` instead of sending live orders.

## Key Features

- **Automated Entry**: Precise entry execution at **14:45**, **15:00**, and **15:30** (UK Time).
- **Multiple Strategies**: Supports both **Iron Condor** (Delta-based) and **Iron Fly** variants.
- **Smart Management**:
    - **Take Profit**: Automatically closes at predetermined profit targets (e.g., 25%).
    - **Time Exits**: Enforces hard exits (e.g., 18:00 UK) for specific strategies to avoid end-of-day risks.
    - **EOD Handling**: Manages settlement and expiration for positions held into the close.
- **Real-Time Monitoring**: Streams live quotes to track position value and trigger exits instantly.
- **Data Analysis**: Logs detailed trade history with unique **Strategy IDs** for granular performance tracking.
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

### Manual Start
Run the main script to start the bot. It will authenticate and begin the loop (monitoring & scanning).
```bash
python main.py
```

### Automated Execution (Recommended)
Use the helper script to keep your system awake (macOS `caffeinate`) and manage the environment automatically.
```bash
./run_autotrader.sh
```

### Market Session Guard
The guard script manages the bot lifecycle based on tastytrade market session data. It starts the bot during trading hours and stops it outside the window.
```bash
./market_session_guard.sh           # Normal operation (cron/launchd)
./market_session_guard.sh --force-run   # Force start
./market_session_guard.sh --force-stop  # Force stop
```

### Background Service (Set & Forget)
Install the bot as a background service (LaunchAgent) on macOS. It will run silently and persist across reboots.
```bash
./setup_service.sh
```
*To stop the service:* `launchctl unload ~/Library/LaunchAgents/com.$(whoami).tasty0dte.plist`

---

## Monitoring & Tools

Since the bot runs in the background, use these included scripts to check its status:

| Command | Description |
| :--- | :--- |
| `./monitor_logs.sh` | **Live Logs**: Watch the bot's real-time activity. Press `Ctrl+C` to exit. |
| `python view_trades.py` | **Trade History**: Formatted table of all closed trades and their P/L. |
| `python analyze_performance.py` | **Performance Analysis**: Win rates, P/L, and expectancy by strategy and time. |
| `python check_metrics.py` | **Health Check**: Verify API connectivity and fetch current SPX price/IV Rank. |
| `python monitor_live.py` | **Live P/L**: Read-only view of open positions without triggering exits. |

### Sample Output (`analyze_performance.py`)
```text
=== Strategy Performance Analysis ===

Strategy       Time   Trades  Win %  Net P/L ($)  Avg Win ($)  Avg Loss ($)  Exp Value ($)
Iron Fly V2    14:37       1 100.0%        $2.20        $2.20         $0.00          $2.20
   30 Delta    14:45      22  90.9%       $12.35        $2.13        $-5.22          $1.58
...

Overall Stats:
Total Trades: 156
Overall Win Rate: 82.1%
Total P/L: $17.99
```

---

## Testing Scripts

Verify logic without waiting for market hours:

| Script | Description |
| :--- | :--- |
| `python test_strategy.py` | Forces a trade entry scan using current market data. |
| `python test_monitor.py` | Simulates P/L changes to test the "Take Profit" logic. |
| `python test_fly_legs.py` | Tests Iron Fly leg selection algorithm. |
| `python test_entry_logic.py` | Verifies the scheduler triggers at the correct times. |

---

## Discord Notifications

The bot sends trade notifications via Discord webhook (not an interactive bot). Configure the webhook URL in your `.env` file:

```bash
DISCORD_WEBHOOK_URL_0DTE=https://discord.com/api/webhooks/...
```

Notifications include:
- Trade open alerts with strikes, credit, wing width, IV Rank
- Trade close alerts with P/L and exit reason
- EOD expiration settlements

---

## Paper Trading Mode

The bot runs in **Paper Trading Mode** by default -- trades are logged to `paper_trades.csv` instead of being sent to the Tastytrade API. This is suitable for:

- Backtesting strategies
- Developing and testing new logic
- Analyzing performance before going live
- Debugging entry/exit signals

---

## Configuration

### Environment Variables (`.env`)

| Variable | Required | Description |
| :--- | :--- | :--- |
| `TASTY_REFRESH_TOKEN` | Yes | OAuth refresh token from Tastytrade |
| `TASTY_CLIENT_SECRET` | Yes | OAuth application provider secret |
| `TASTY_ACCOUNT_ID` | Yes | Tastytrade account number |
| `DISCORD_WEBHOOK_URL_0DTE` | No | Discord webhook URL for trade notifications |
| `TWEET_SCRIPT_PATH` | No | Path to X/Twitter posting script |

### Project Files

| File | Description |
| :--- | :--- |
| `main.py` | Main entry point and trading loop |
| `strategy.py` | Option chain fetching and leg selection |
| `monitor.py` | Position monitoring and exit management |
| `logger.py` | Trade logging to CSV |
| `local/discord_notify.py` | Discord webhook notifications |
| `local/x_notify.py` | X (Twitter) integration |
| `run_autotrader.sh` | Startup wrapper with caffeinate |
| `market_session_guard.sh` | Market hours lifecycle manager |
| `setup_service.sh` | macOS LaunchAgent installer |

**Important:** Never commit `.env` to version control -- it contains sensitive credentials.
