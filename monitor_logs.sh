#!/bin/bash
echo "Monitoring Tasty0DTE Logs (Press Ctrl+C to exit)..."
PRIVATE_ROOT="${TASTY_PRIVATE_DATA_ROOT:-${HOME}/Private/ProjectsData/trading/tasty0dte-ironcondor}"
tail -f "$PRIVATE_ROOT/runtime/logs/stdout.log" "$PRIVATE_ROOT/runtime/logs/stderr.log"
