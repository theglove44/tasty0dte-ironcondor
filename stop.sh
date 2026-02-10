#!/bin/bash
#
# Stop the bot gracefully
#
cd "$(dirname "$0")"

PID=$(pgrep -f "python.*main.py")

if [ -z "$PID" ]; then
    echo "Bot is not running."
    exit 0
fi

echo "Stopping bot (PID: $PID)..."
kill "$PID" 2>/dev/null

# Wait for graceful shutdown
for i in {1..10}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "✅ Bot stopped."
        exit 0
    fi
    sleep 1
done

echo "Force killing..."
kill -9 "$PID" 2>/dev/null
echo "✅ Bot killed."
