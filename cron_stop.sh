#!/bin/bash
#
# Cron job: Stop bot after market close
# Runs at 21:15 UK (after EOD expiration at 21:00)
#
cd "$(dirname "$0")"

PID=$(pgrep -f "python.*main.py")

if [ -z "$PID" ]; then
    echo "[$(date)] Bot not running - nothing to stop"
    exit 0
fi

echo "[$(date)] Stopping bot after market close..."
kill "$PID" 2>/dev/null

sleep 5
if ! kill -0 "$PID" 2>/dev/null; then
    echo "[$(date)] ✅ Bot stopped cleanly"
else
    kill -9 "$PID" 2>/dev/null
    echo "[$(date)] ✅ Bot force-stopped"
fi
