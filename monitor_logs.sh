#!/bin/bash
echo "Monitoring Tasty0DTE Logs (Press Ctrl+C to exit)..."
tail -f runtime/logs/stdout.log runtime/logs/stderr.log
