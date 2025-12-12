# Tastytrade 0DTE Iron Condor Automator

An automated trading bot designed for **0DTE (Zero Days to Expiration)** Iron Condors on **SPX**, utilizing the Tastytrade API. This tool automates the entire lifecycle of the trade: from identifying opportunities and entering trades at specific times to monitoring positions and executing exits based on profit targets or time constraints.

> [!NOTE]
> This application currently runs in **Paper Trading Mode** by default (logging trades to a CSV file instead of sending live orders).

## Features

- **Automated Entry**: Scans for opportunities at specific times (UK Time).
- **Strategy Logic**: Implements 0DTE Iron Condors with configurable delta targets.
- **Position Monitoring**: Real-time tracking of P/L using live market data streamers.
- **Automated Exits**:
    - **Profit Taking**: Automatically closes trades when they reach 25% max profit.
    - **Time-Based Exit**: Specific strategies exit early at a defined time.
    - **EOD Expiration**: Handles settlement and expiration for positions held to market close.
- **Paper Trading**: fully functional paper trading engine that simulates fills and tracks performance in `paper_trades.csv`.

## Strategies

The bot currently implements two variations of the Iron Condor strategy on SPX. Both target **$20 wide wings**.

### 1. 20 Delta Iron Condor
- **Entry**: Short strikes selected at approximately **20 Delta**.
- **Management**:
    - **Take Profit**: 25% of credit received.
    - **Stop Loss**: None (held to expiration or profit target).

### 2. 30 Delta Iron Condor
- **Entry**: Short strikes selected at approximately **30 Delta**.
- **Management**:
    - **Take Profit**: 25% of credit received.
    - **Time Exit**: Positions are closed automatically at **18:00 UK Time** (13:00 ET) if the profit target hasn't been hit.

### Entry Schedule (UK Time)
The bot triggers entry logic at the following times:
- `14:45`
- `15:00`
- `15:30`

## Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/theglove44/tasty0dte-ironcondor.git
   cd tasty0dte-ironcondor
   ```

2. **Set Up Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Requires `tastytrade-sdk`, `pandas`, `python-dotenv`.*

4. **Configuration**
   Create a `.env` file in the root directory with your Tastytrade credentials. You can use the provided `.env.example` as a template.
   ```bash
   cp .env.example .env
   ```
   
   **Required Variables:**
   ```env
   TASTY_REFRESH_TOKEN=your_token_here
   TASTY_CLIENT_SECRET=your_client_secret_here  # Only if using custom OAuth
   TASTY_ACCOUNT_ID=your_account_id
   ```

## Usage

Run the main script to start the bot:

```bash
python main.py
```

### What to Expect
1. **Authentication**: The bot will authenticate with Tastytrade.
2. **Monitoring**: It will immediately check `paper_trades.csv` for any open positions and start streaming quotes to monitor their P/L.
3. **Scanning**: It will wait for the next scheduled entry time.
4. **Execution**: When a strategy triggers, it will:
    - Fetch the SPX option chain.
    - Filter for 0DTE expirations.
    - Calculate the legs based on the Delta target.
    - Log the "fill" to `paper_trades.csv`.

## Project Structure

- `main.py`: The entry point. Handles the scheduling loop and authenticates the session.
- `strategy.py`: Contains the core logic for finding trade entry candidates (fetching chains, selecting legs based on Delta).
- `monitor.py`: Handles active trade management. Streams real-time quotes, calculates P/L, and updates the CSV when trades close or expire.
- `logger.py`: structured logging setup.
- `paper_trades.csv`: The local database of all trades (Entry/Exit prices, P/L, Status).

## Disclaimer
This software is for educational purposes only. Do not risk money you cannot afford to lose.

## Automated Execution

### Helper Script: `run_autotrader.sh`
This shell script is the engine behind the automation. It performs three key functions:
1. **Prevents Sleep**: Uses `caffeinate -i` to prevent your Mac from sleeping while the trading session is active (crucial for 0DTE management).
2. **Environment Management**: Automatically navigates to the project directory and activates the Python virtual environment.
3. **Execution**: Runs `main.py` with the correct settings.

You can run this script manually if you want to start the trader and ensure your computer stays awake:
```bash
./run_autotrader.sh
```

### Background Service (Launchd)
To run this bot unattended in the background on macOS:

1. **Configure the plist**:
    - Rename `com.example.tasty0dte.plist` to `com.yourname.tasty0dte.plist`.
    - Edit the file and replace `/Users/YOUR_USERNAME/` with your actual home directory path.

2. **Move the configuration file** to your LaunchAgents folder:
    ```bash
    mv com.yourname.tasty0dte.plist ~/Library/LaunchAgents/
    ```

3. **Load the service**:
    ```bash
    launchctl load ~/Library/LaunchAgents/com.yourname.tasty0dte.plist
    ```

The bot will now run constantly in the background, preventing your Mac from sleeping while it is active (using `caffeinate`).

- **Logs**: Output is saved to `stdout.log` and `stderr.log` in the project directory.
- **Stop**: Run `launchctl unload ~/Library/LaunchAgents/com.yourname.tasty0dte.plist`

## Testing & Utilities

The project includes several test scripts to verify logic without waiting for real-time market conditions.

### `test_strategy.py`
**Use Case**: Manual Strategy Verification.
- **What it does**: Bypasses the schedule and attempts to run the full trade entry logic **immediately** using live market data.
- **When to use**: Use this to check if the API connection is working and if the strategy can successfully find legs and calculate credit right now.
- **Warning**: This requires valid credentials in `.env` and makes real API calls (though in paper mode it only logs to CSV).

### `test_monitor.py`
**Use Case**: Unit Testing Logic.
- **What it does**: Tests the P/L calculation and "Take Profit" logic. It uses mocked market data to simulate prices moving in your favor to ensure the code correctly identifies when to close a trade.
- **When to use**: Run this after making changes to `monitor.py` to ensure you haven't broken the exit logic.

### `test_entry_logic.py`
**Use Case**: Scheduler Verification.
- **What it does**: Verifies the time-checking mechanism. It simulates different times of day to ensure the bot triggers *only* at 14:45, 15:00, and 15:30.
- **When to use**: Use this if you are changing the target entry times.

### `test_display.py`
**Use Case**: UI/UX Verification.
- **What it does**: Simulates the console output for open trades. It creates a dummy trade entry to show how the P/L, Credits, and IV Rank are formatted in the console.
- **When to use**: Use this when tweaking the look and feel of the dashboard output.

### `test_empty.py`
**Use Case**: Edge Case Testing.
- **What it does**: Verifies that the dashboard handles an empty state (no open trades) gracefully without crashing.
