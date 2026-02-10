#!/bin/bash
#
# Simple startup script for tasty0dte
# No network checks - the bot handles connectivity gracefully
#

cd "$(dirname "$0")"

# Activate venv
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment 'venv' not found"
    exit 1
fi

echo "[$(date)] Starting 0DTE Trader..."

# Run with caffeinate to prevent sleep (macOS)
# The bot handles all errors internally and never crashes
caffeinate -i python -u main.py 2>&1

echo "[$(date)] 0DTE Trader exited"
