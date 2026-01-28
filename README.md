# Tasty0DTE: Automated Iron Condor & Iron Fly Trader

**Tasty0DTE** is an automated trading bot designed for **0DTE (Zero Days to Expiration)** strategies on **SPX**, utilizing the Tastytrade API. It automates the entire lifecycle of the trade: identifying opportunities at specific times, entering high-probability setups, monitoring P/L in real-time, and executing disciplined exits.

> [!NOTE]
> This application runs in **Paper Trading Mode** by default, logging "fills" to `paper_trades.csv` instead of sending live orders.

## 🚀 Key Features

- **Automated Entry**: Precise entry execution at **14:45**, **15:00**, and **15:30** (UK Time).
- **Multiple Strategies**: Supports both **Iron Condor** (Delta-based) and **Iron Fly** variants.
- **Smart Management**:
    - **Take Profit**: Automatically closes at predetermined profit targets (e.g., 25%).
    - **Time Exits**: Enforces hard exits (e.g., 18:00 UK) for specific strategies to avoid end-of-day risks.
    - **EOD Handling**: Manages settlement and expiration for positions held into the close.
- **Real-Time Monitoring**: Streams live quotes to track position value and trigger exits instantly.
- **Data Analysis**: Logs detailed trade history with unique **Strategy IDs** for granular performance tracking.

---

## 📊 Strategies

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

## 🛠️ Installation

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
    *Required: `TASTY_REFRESH_TOKEN`, `TASTY_ACCOUNT_ID`.*

---

## 🖥️ Usage

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

### Background Service (Set & Forget)
Install the bot as a background service (LaunchAgent) on macOS. It will run silently and persist across reboots.
```bash
./setup_service.sh
```
*To stop the service:* `launchctl unload ~/Library/LaunchAgents/com.${USER}.tasty0dte.plist`

## 📈 Monitoring & Tools

Since the bot runs in the background, use these included scripts to check its status:

| Command | Description |
| :--- | :--- |
| `./monitor_logs.sh` | **Live Logs**: Watch the bot's real-time activity (scanning, pricing, decision making). Press `Ctrl+C` to exit. |
| `python view_trades.py` | **Trade History**: Displays a formatted table of all closed trades and their P/L, plus a snapshot of open positions. |
| `python analyze_performance.py` | **Performance Analysis**: Detailed breakdown of win rates, P/L, and expectancy by strategy and time variation. |
| `python check_metrics.py` | **Health Check**: Quickly verify API connectivity and fetch current market metrics (SPX Price, IV Rank). |

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

### Sample Output (`view_trades.py`)
```text
=== Closed Trades Log ===

Date        Entry Time  Symbol  Strategy           Rules                    Profit Target  Exit P/L  Notes
2026-01-15  15:00:25    SPX     20 Delta (15:00)   25% Profit | EOD Exp     1.02           1.10      Closed at Debit: 2.98
2026-01-15  15:00:27    SPX     30 Delta (15:00)   25% Profit | 18:00 Exit  1.88           1.90      Closed at Debit: 5.60
2026-01-16  15:00:12    SPX     Iron Fly V2 (15:00) Unknown                 1.74           1.77      Closed at Debit: 6.92

=========================

Summary (Closed Trades):
Count: 42
Total P/L: $65.30
```

## 🧪 Testing Scripts
The project includes scripts to verify logic without waiting for market hours:
- `test_strategy.py`: Forces a trade entry scan immediately using current market data.
- `test_monitor.py`: Simulates P/L changes to test the "Take Profit" logic.
- `test_entry_logic.py`: Verifies the scheduler triggers at the correct times.

---

## 🤖 Discord Bot Interaction

**Discord Bot Name:** `@Jarvis` (ID: 1460642437558173809)

**Discord Bot Channels:**
- **#0dte-tasty** (ID: 1457745924561309767) — Main trading updates and alerts
- **#tasty0dte-trade-summary** — End-of-day and weekly trade performance summaries

### How to Use the Bot

**Available Commands:**

| Command | Description | Example |
|---------|-------------|---------|
| `@Jarvis status` | Check current bot status and connectivity | `@Jarvis status` |
| `@Jarvis positions` | View all current positions | `@Jarvis positions` |
| `@Jarvis trades` | Show recent trade history (last 10 trades) | `@Jarvis trades` |
| `@Jarvis summary` | Display trade performance summary (win rate, P/L) | `@Jarvis summary` |
| `@Jarvis next` | Show next scheduled entry signal | `@Jarvis next` |
| `@Jarvis p/l` | Show current P/L for all open positions | `@Jarvis p/l` |
| `@Jarvis analyze` | Performance analysis by strategy | `@Jarvis analyze iron fly` |

### Manual Bot Control

You can manually control the bot using these scripts in the `scripts/` directory:

| Script | Description |
|--------|-------------|
| `start_bot.sh` | Start the bot in foreground (for testing/debugging) |
| `stop_bot.sh` | Stop a running bot instance |
| `run_autotrader.sh` | Run bot as background service (recommended) |
| `monitor_logs.sh` | Live log viewer showing bot activity in real-time |

### Viewing Logs

**Live Monitoring:**
```bash
./scripts/monitor_logs.sh
```
This shows real-time activity including:
- Market scans and signal detection
- Trade entries and position management
- P/L updates and profit-taking events
- Strategy decisions and order execution

Press `Ctrl+C` to exit the live log viewer.

**Trade History:**
```bash
python scripts/view_trades.py
```
Displays a formatted table of all closed trades with P/L, entry/exit times, and strategy details.

**Performance Analysis:**
```bash
python scripts/analyze_performance.py
```
Provides detailed breakdown of win rates, P/L expectancy, and performance by strategy and time variation.

### Background Service (Recommended)

For production use, run the bot as a background service that starts automatically on login:

```bash
./scripts/run_autotrader.sh
```

This uses `launchd` (macOS) to start the bot as a LaunchAgent, ensuring it runs silently in the background and persists across reboots.

**To stop the background service:**
```bash
launchctl unload com.theglove44.tasty0dte.plist
```

### Paper Trading Mode

The bot runs in **Paper Trading Mode** by default — trades are logged to `paper_trades.csv` instead of being sent to the Tastytrade API. This is perfect for:

- ✅ Backtesting strategies
- ✅ Developing and testing new logic
- ✅ Analyzing performance before going live
- ✅ Debugging entry/exit signals

**To enable live trading:**

1. Set `PAPER_TRADING_MODE=false` in `main.py`
2. Restart the bot

Live trading will send actual orders to Tastytrade API and require valid account credentials.

### Configuration Files

| File | Description |
|------|-------------|
| `.env.example` | Template for environment variables (copy to `.env` to configure) |
| `.env` | Bot configuration (API keys, strategy parameters, etc.) |
| `config.json` | Strategy and bot behavior settings (entry times, profit targets, etc.) |

**Required Environment Variables** (in `.env`):
```bash
# Tastytrade API (Paper Mode)
TASTY_REFRESH_TOKEN=your_token_here
TASTY_ACCOUNT_ID=your_account_id_here

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_GUILD_ID=your_guild_id_here
DISCORD_MAIN_CHANNEL_ID=your_main_channel_id
```

**Important:** Never commit `.env` to version control — it contains sensitive credentials!
