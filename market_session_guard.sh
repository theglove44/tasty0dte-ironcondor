#!/bin/bash
set -euo pipefail

# Guards tasty0dte-ironcondor runtime based on tastytrade market session API.
# Window: [open_at - 15m, close_at + 15m]
# Designed for launchd (no TTY), safe to run repeatedly.
#
# SAFETY (rollout):
# - OBSERVE-ONLY unless marker exists:
#     /Users/office/Projects/tasty0dte-ironcondor/.guard_enabled
# - Manual tests:
#     ./market_session_guard.sh --force-run
#     ./market_session_guard.sh --force-stop

REPO_DIR="/Users/office/Projects/tasty0dte-ironcondor"
RUNTIME_DIR="$REPO_DIR/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
STATE_DIR="$RUNTIME_DIR/state"
LOCKS_DIR="$RUNTIME_DIR/locks"
PIDFILE="$STATE_DIR/bot.pid"
LOCKDIR="$LOCKS_DIR/.guard.lock"
ENABLE_MARKER="$REPO_DIR/.guard_enabled"
SESSION_CACHE="$STATE_DIR/market_session_cache.json"
CURL_ERR_FILE="$STATE_DIR/.market_session_curl.err"

log() {
  echo "[guard $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

FORCE_RUN=0
FORCE_STOP=0
case "${1-}" in
  --force-run) FORCE_RUN=1 ;;
  --force-stop) FORCE_STOP=1 ;;
  "") : ;;
  *) log "Unknown arg: ${1}"; exit 2 ;;
esac

cd "$REPO_DIR"
mkdir -p "$LOG_DIR" "$STATE_DIR" "$LOCKS_DIR"

# Simple lock so concurrent runs don't fight.
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  log "Another guard instance is running; exiting."
  exit 0
fi
cleanup() { rmdir "$LOCKDIR" 2>/dev/null || true; }
trap cleanup EXIT

PYTHON_BIN="python3"
command -v python3 >/dev/null 2>&1 || PYTHON_BIN="python"

NOW_EPOCH=$($PYTHON_BIN -c 'import time; print(int(time.time()))')

# Mon–Fri only (UTC weekday: 0=Mon .. 6=Sun).
if [[ $FORCE_RUN -eq 0 && $FORCE_STOP -eq 0 ]]; then
  NOW_WD=$($PYTHON_BIN -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).weekday())')
  if (( NOW_WD >= 5 )); then
    log "Weekend (weekday=$NOW_WD); exiting without changes."
    exit 0
  fi
fi

STATE=""
OPEN_AT=""
CLOSE_AT=""
ALLOW_START_EPOCH=0
ALLOW_STOP_EPOCH=0

if [[ $FORCE_RUN -eq 0 && $FORCE_STOP -eq 0 ]]; then
  # capture body + http code
  set +e
  RESP=$(curl -sS --max-time 6 --connect-timeout 3 \
    -w "\nHTTP_CODE:%{http_code}\n" \
    "https://api.tastytrade.com/market-time/equities/sessions/current" 2>"$CURL_ERR_FILE")
  CURL_STATUS=$?
  set -e

  HTTP_CODE=$(echo "$RESP" | sed -n 's/^HTTP_CODE://p' | tail -n 1)
  JSON=$(echo "$RESP" | sed '/^HTTP_CODE:/d')

  if [[ $CURL_STATUS -ne 0 || -z "$HTTP_CODE" || "$HTTP_CODE" != "200" || -z "$(echo "$JSON" | tr -d "\r\n\t ")" ]]; then
    CURL_ERR="$(tr '\n' ' ' < "$CURL_ERR_FILE" 2>/dev/null || true)"
    log "WARN: market session API unavailable (curl_status=$CURL_STATUS http=${HTTP_CODE:-none} error=${CURL_ERR:-none})."
    if [[ -s "$SESSION_CACHE" ]]; then
      JSON=$(cat "$SESSION_CACHE")
      log "WARN: using cached market session from $SESSION_CACHE."
    else
      log "WARN: no cached market session available; exiting."
      exit 0
    fi
  else
    printf '%s\n' "$JSON" > "$SESSION_CACHE"
  fi

  # Parse response. API returns {"data":{...}}.
  # IMPORTANT: use python -c so stdin remains available for the JSON.
  read -r STATE OPEN_AT CLOSE_AT < <(
    echo "$JSON" | $PYTHON_BIN -c 'import json,sys
j=json.load(sys.stdin)
data=j.get("data") if isinstance(j,dict) else None
if not isinstance(data,dict):
    data = j if isinstance(j,dict) else {}
state=data.get("state","")
open_at=data.get("open-at") or data.get("openAt")
close_at=data.get("close-at") or data.get("closeAt")
ns=data.get("next-session") or data.get("nextSession")
if (not open_at or not close_at) and isinstance(ns,dict):
    open_at = ns.get("open-at") or ns.get("openAt")
    close_at = ns.get("close-at") or ns.get("closeAt")
print(state, open_at or "", close_at or "")'
  )

  if [[ -z "$OPEN_AT" || -z "$CLOSE_AT" ]]; then
    log "WARN: could not parse open/close from session JSON; exiting."
    exit 0
  fi

  read -r ALLOW_START_EPOCH ALLOW_STOP_EPOCH < <(
    $PYTHON_BIN -c 'from datetime import datetime,timedelta; import sys

def parse_iso(s:str)->datetime:
    s=s.strip()
    if s.endswith("Z"):
        s=s[:-1]+"+00:00"
    return datetime.fromisoformat(s)

o=parse_iso(sys.argv[1]); c=parse_iso(sys.argv[2])
start=o-timedelta(minutes=15)
stop=c+timedelta(minutes=15)
print(int(start.timestamp()), int(stop.timestamp()))' "$OPEN_AT" "$CLOSE_AT"
  )
fi

SHOULD_RUN=0
if [[ $FORCE_RUN -eq 1 ]]; then
  SHOULD_RUN=1
elif [[ $FORCE_STOP -eq 1 ]]; then
  SHOULD_RUN=0
else
  if (( NOW_EPOCH >= ALLOW_START_EPOCH && NOW_EPOCH <= ALLOW_STOP_EPOCH )); then
    SHOULD_RUN=1
  fi
fi

# Determine if trader is running
RUNNING_PID=""
PIDFILE_PID=""
if [[ -f "$PIDFILE" ]]; then
  pid=$(cat "$PIDFILE" 2>/dev/null || true)
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    RUNNING_PID="$pid"
  elif [[ -n "$pid" ]]; then
    PIDFILE_PID="$pid"
  else
    rm -f "$PIDFILE" 2>/dev/null || true
  fi
fi

if [[ -z "$RUNNING_PID" ]]; then
  set +e
  pgrep_out=$(/usr/bin/pgrep -f "main\.py" 2>/dev/null)
  pgrep_status=$?
  set -e
  pid=$(printf '%s\n' "$pgrep_out" | /usr/bin/head -n 1)
  if [[ -n "$pid" ]]; then
    RUNNING_PID="$pid"
    echo "$pid" > "$PIDFILE"
  elif [[ -n "$PIDFILE_PID" && $pgrep_status -gt 1 ]]; then
    RUNNING_PID="$PIDFILE_PID"
    log "WARN: could not verify pidfile pid=$PIDFILE_PID with pgrep; assuming trader is running."
  elif [[ -n "$PIDFILE_PID" ]]; then
    rm -f "$PIDFILE" 2>/dev/null || true
  fi
fi

# Rollout safety: observe-only unless enabled marker exists, or forced.
if [[ $FORCE_RUN -eq 0 && $FORCE_STOP -eq 0 && ! -f "$ENABLE_MARKER" ]]; then
  log "OBSERVE: should_run=$SHOULD_RUN running_pid=${RUNNING_PID:-none} state=${STATE:-?} open_at=${OPEN_AT:-?} close_at=${CLOSE_AT:-?}"
  exit 0
fi

if [[ $SHOULD_RUN -eq 1 ]]; then
  if [[ -n "$RUNNING_PID" ]]; then
    log "OK: trader already running (pid=$RUNNING_PID)."
    exit 0
  fi
  log "START: within window (state=${STATE:-?} open_at=${OPEN_AT:-?} close_at=${CLOSE_AT:-?})"
  nohup /bin/bash "$REPO_DIR/run_autotrader.sh" >> "$LOG_DIR/stdout.log" 2>> "$LOG_DIR/stderr.log" &
  # The backgrounded PID is the bash wrapper; we want the real main.py PID.
  sleep 1
  PY_PID=$(/usr/bin/pgrep -f "main\.py" | /usr/bin/head -n 1 || true)
  if [[ -n "$PY_PID" ]]; then
    echo "$PY_PID" > "$PIDFILE"
    log "STARTED: python pid=$PY_PID"
  else
    log "WARN: wrapper started but main.py pid not found"
  fi
  exit 0
else
  if [[ -z "$RUNNING_PID" ]]; then
    log "OK: trader not running; nothing to stop."
    exit 0
  fi
  log "STOP: outside window; stopping pid=$RUNNING_PID"
  kill "$RUNNING_PID" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if kill -0 "$RUNNING_PID" 2>/dev/null; then
      sleep 1
    else
      rm -f "$PIDFILE" 2>/dev/null || true
      log "STOPPED: pid=$RUNNING_PID"
      exit 0
    fi
  done
  log "WARN: still alive after 10s; SIGKILL"
  kill -9 "$RUNNING_PID" 2>/dev/null || true
  rm -f "$PIDFILE" 2>/dev/null || true
  log "KILLED: pid=$RUNNING_PID"
  exit 0
fi
