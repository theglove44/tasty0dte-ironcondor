#!/bin/bash
#
# Cron job: Start bot before market open
# Runs at 14:30 UK (15 mins before first entry) — both US+UK DST active
#
cd "$(dirname "$0")"

PRIVATE_ROOT="${TASTY_PRIVATE_DATA_ROOT:-${HOME}/Private/ProjectsData/trading/tasty0dte-ironcondor}"
RUNTIME_DIR="$PRIVATE_ROOT/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
STATE_DIR="$RUNTIME_DIR/state"
PID_FILE="$STATE_DIR/bot.pid"
STDOUT_LOG="$LOG_DIR/stdout.log"
STDERR_LOG="$LOG_DIR/stderr.log"

mkdir -p "$LOG_DIR" "$STATE_DIR"

# Only run on weekdays (1-5 = Mon-Fri)
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    echo "[$(date)] Weekend - skipping"
    exit 0
fi

# Check if already running via PID file
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date)] Bot already running (PID $OLD_PID)"
        exit 0
    else
        echo "[$(date)] Stale PID file found, cleaning up"
        rm -f "$PID_FILE"
    fi
fi

echo "[$(date)] Starting bot for trading session..."

PYTHON="./venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "[$(date)] Error: $PYTHON not found"
    exit 1
fi
caffeinate -i "$PYTHON" -u main.py >> "$STDOUT_LOG" 2>> "$STDERR_LOG" &
BOT_PID=$!

# Write PID file
echo "$BOT_PID" > "$PID_FILE"

sleep 3
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "[$(date)] ✅ Bot started (PID $BOT_PID)"
else
    echo "[$(date)] ❌ Failed to start"
    rm -f "$PID_FILE"
    exit 1
fi
