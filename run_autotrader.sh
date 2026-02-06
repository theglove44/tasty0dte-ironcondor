#!/bin/bash

# Navigate to the directory where this script is located
# This makes the script portable and safe for git even if directories change
cd "$(dirname "$0")"

# Activate the virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: Virtual environment 'venv' not found in $(pwd)"
    exit 1
fi

# Run the python script with caffeinate to prevent sleep
# -i prevents the system from idle sleeping while the command is running
echo "Starting 0DTE Trader at $(date)"
# Using 'python' from the activated venv
exec caffeinate -i python -u main.py
