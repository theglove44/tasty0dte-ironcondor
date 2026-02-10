#!/bin/bash
#
# Check bot status
#
cd "$(dirname "$0")"

PID=$(pgrep -f "python.*main.py")

if [ -z "$PID" ]; then
    echo "❌ Bot is NOT running."
    exit 1
fi

echo "✅ Bot is running (PID: $PID)"
echo ""
echo "Recent log:"
tail -5 stdout.log 2>/dev/null || echo "(no log yet)"
