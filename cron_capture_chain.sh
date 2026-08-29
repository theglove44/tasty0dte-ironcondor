#!/bin/bash
#
# Daily SPX option-chain capture for the backtesting corpus.
#
# Pulls a trailing 5-calendar-day window (… → yesterday) with --skip-existing.
# Rationale: OPRA historical availability lags ~T+2, so the most recent day
# often 403s ("live data license required"); that day is filled automatically
# on a later run once it publishes. --skip-existing makes every run idempotent,
# so a missed day (machine asleep) is caught up next time with no duplication.
#
# Scope: Tier A (0DTE + 5/7/10 DTE), ~$0.05/day. See
# docs/proposals/2026-06-30-chain-capture-databento.md
#
set -uo pipefail
cd "$(dirname "$0")"

# DATABENTO_API_KEY lives in ~/.zshenv (single export line; cron has a bare env)
[ -f "$HOME/.zshenv" ] && source "$HOME/.zshenv"

if [ -z "${DATABENTO_API_KEY:-}" ]; then
  echo "[$(date)] capture aborted — DATABENTO_API_KEY not set"
  exit 1
fi

if [ ! -d venv ]; then
  echo "[$(date)] capture aborted — venv not found"
  exit 1
fi

START=$(date -v-5d +%Y-%m-%d)
END=$(date -v-1d +%Y-%m-%d)

echo "[$(date)] chain capture: $START → $END (Tier A, --skip-existing)"
venv/bin/python tools/capture_spx_chain.py \
    --start "$START" --end "$END" --confirm --skip-existing

# Derive IV/Greeks sidecars for any newly-captured days (idempotent).
echo "[$(date)] enriching IV/Greeks"
venv/bin/python tools/enrich_chain_greeks.py \
    --start "$START" --end "$END" --skip-existing

echo "[$(date)] chain capture done"
