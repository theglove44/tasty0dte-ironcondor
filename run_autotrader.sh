#!/bin/bash
#
# Simple startup script for tasty0dte
# No network checks - the bot handles connectivity gracefully
#

cd "$(dirname "$0")"

PYTHON="./venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "Error: $PYTHON not found"
    exit 1
fi

echo "[$(date)] Starting 0DTE Trader..."

# Run with caffeinate to prevent sleep (macOS)
# The bot handles all errors internally and never crashes
caffeinate -i "$PYTHON" -u main.py 2>&1

echo "[$(date)] 0DTE Trader exited"
