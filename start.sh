#!/bin/bash
#
# Start the bot in the background
#
cd "$(dirname "$0")"

RUNTIME_DIR="runtime"
LOG_DIR="$RUNTIME_DIR/logs"
STATE_DIR="$RUNTIME_DIR/state"
PID_FILE="$STATE_DIR/bot.pid"
STDOUT_LOG="$LOG_DIR/stdout.log"
STDERR_LOG="$LOG_DIR/stderr.log"

mkdir -p "$LOG_DIR" "$STATE_DIR"

# Check if already running via PID file
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Bot is already running (PID $OLD_PID)"
        exit 0
    else
        echo "Stale PID file found, cleaning up"
        rm -f "$PID_FILE"
    fi
fi

echo "Starting bot..."

# Activate venv and start
source venv/bin/activate
caffeinate -i python -u main.py >> "$STDOUT_LOG" 2>> "$STDERR_LOG" &
BOT_PID=$!

echo "$BOT_PID" > "$PID_FILE"

sleep 2
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "✅ Bot started (PID $BOT_PID). Logs: tail -f $STDOUT_LOG"
else
    echo "❌ Failed to start. Check $STDERR_LOG"
    rm -f "$PID_FILE"
fi
