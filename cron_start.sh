#!/bin/bash
#
# Cron job: Start bot before market open
# Runs at 14:30 UK (15 mins before first entry)
#
cd "$(dirname "$0")"

# Only run on weekdays (1-5 = Mon-Fri)
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    echo "[$(date)] Weekend - skipping"
    exit 0
fi

# Check if already running
if pgrep -f "python.*main.py" > /dev/null; then
    echo "[$(date)] Bot already running"
    exit 0
fi

echo "[$(date)] Starting bot for trading session..."
nohup ./run_autotrader.sh >> stdout.log 2>> stderr.log &

sleep 3
if pgrep -f "python.*main.py" > /dev/null; then
    echo "[$(date)] ✅ Bot started"
else
    echo "[$(date)] ❌ Failed to start"
fi
