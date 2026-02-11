#!/bin/bash
#
# Start the bot in the background
#
cd "$(dirname "$0")"

PID_FILE="bot.pid"

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
caffeinate -i python -u main.py >> stdout.log 2>> stderr.log &
BOT_PID=$!

echo "$BOT_PID" > "$PID_FILE"

sleep 2
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "✅ Bot started (PID $BOT_PID). Logs: tail -f stdout.log"
else
    echo "❌ Failed to start. Check stderr.log"
    rm -f "$PID_FILE"
fi
