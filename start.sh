#!/bin/bash
#
# Start the bot in the background
#
cd "$(dirname "$0")"

if pgrep -f "python.*main.py" > /dev/null; then
    echo "Bot is already running."
    exit 0
fi

echo "Starting bot..."
nohup ./run_autotrader.sh >> stdout.log 2>> stderr.log &
sleep 2

if pgrep -f "python.*main.py" > /dev/null; then
    echo "✅ Bot started. Logs: tail -f stdout.log"
else
    echo "❌ Failed to start. Check stderr.log"
fi
