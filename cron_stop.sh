#!/bin/bash
#
# Cron job: Stop bot after market close
# Runs at 21:15 UK (after EOD expiration at 21:00)
#
cd "$(dirname "$0")"

PID_FILE="bot.pid"

# Check PID file first
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "[$(date)] Found PID file: $PID"
else
    echo "[$(date)] No PID file found"
    PID=""
fi

# Also check for any orphaned processes
ORPHAN_PIDS=$(pgrep -f "python.*main.py" 2>/dev/null | tr '\n' ' ')

if [ -z "$PID" ] && [ -z "$ORPHAN_PIDS" ]; then
    echo "[$(date)] Bot not running - nothing to stop"
    rm -f "$PID_FILE"
    exit 0
fi

echo "[$(date)] Stopping bot after market close..."

# Kill main process from PID file
if [ -n "$PID" ]; then
    if kill -0 "$PID" 2>/dev/null; then
        echo "[$(date)] Killing PID $PID and children..."
        # Kill the process group (caffeinate + python)
        pkill -TERM -P "$PID" 2>/dev/null  # Kill children first
        kill -TERM "$PID" 2>/dev/null       # Then parent
        sleep 2
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            pkill -KILL -P "$PID" 2>/dev/null
            kill -KILL "$PID" 2>/dev/null
        fi
    fi
fi

# Clean up any orphaned python processes
if [ -n "$ORPHAN_PIDS" ]; then
    echo "[$(date)] Cleaning orphaned processes: $ORPHAN_PIDS"
    for OPID in $ORPHAN_PIDS; do
        kill -TERM "$OPID" 2>/dev/null
    done
    sleep 2
    for OPID in $ORPHAN_PIDS; do
        kill -KILL "$OPID" 2>/dev/null
    done
fi

# Clean up PID file
rm -f "$PID_FILE"

# Verify
sleep 1
REMAINING=$(pgrep -f "python.*main.py" 2>/dev/null)
if [ -z "$REMAINING" ]; then
    echo "[$(date)] ✅ Bot stopped cleanly"
else
    echo "[$(date)] ⚠️ Some processes may still be running: $REMAINING"
fi
