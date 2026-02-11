#!/bin/bash
#
# Check bot status
#
cd "$(dirname "$0")"

PID_FILE="bot.pid"

# Check PID file first
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "✅ Bot is running (PID: $PID)"
        echo ""
        echo "Recent log:"
        tail -5 stdout.log 2>/dev/null || echo "(no log yet)"
        exit 0
    else
        echo "⚠️ Stale PID file (process $PID not running)"
        rm -f "$PID_FILE"
    fi
fi

# Fallback: check for orphaned processes
ORPHAN=$(pgrep -f "python.*main.py" | head -1)
if [ -n "$ORPHAN" ]; then
    echo "⚠️ Bot running without PID file (orphan PID: $ORPHAN)"
    exit 0
fi

echo "❌ Bot is NOT running."
exit 1
