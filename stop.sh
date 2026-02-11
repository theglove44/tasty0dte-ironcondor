#!/bin/bash
#
# Stop the bot gracefully
#
cd "$(dirname "$0")"

PID_FILE="bot.pid"

# Get PID from file or fallback to pgrep
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "Found PID file: $PID"
else
    PID=$(pgrep -f "python.*main.py" | head -1)
fi

if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
    echo "Bot is not running."
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping bot (PID: $PID)..."

# Kill children first (python), then parent (caffeinate)
pkill -TERM -P "$PID" 2>/dev/null
kill -TERM "$PID" 2>/dev/null

# Wait for graceful shutdown
for i in {1..10}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "✅ Bot stopped."
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill
echo "Force killing..."
pkill -KILL -P "$PID" 2>/dev/null
kill -KILL "$PID" 2>/dev/null
rm -f "$PID_FILE"

# Clean up any orphans
pkill -KILL -f "python.*main.py" 2>/dev/null

echo "✅ Bot killed."
