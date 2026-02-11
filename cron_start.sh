#!/bin/bash
#
# Cron job: Start bot before market open
# Runs at 14:30 UK (15 mins before first entry)
#
cd "$(dirname "$0")"

PID_FILE="bot.pid"

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

# Activate venv and start in background
source venv/bin/activate

# Start with caffeinate, capture the caffeinate PID (parent of python)
caffeinate -i python -u main.py >> stdout.log 2>> stderr.log &
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
