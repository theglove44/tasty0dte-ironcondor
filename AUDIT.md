# tasty0dte-ironcondor — Full Audit

**Date:** 2026-02-10
**Issue:** Repeated IP blacklisting from Tastytrade API

---

## Executive Summary

The bot worked perfectly when first built because it was **simple**: one session, running during market hours, streaming for position updates. Over time, "reliability" features were added that **made it less reliable** by hammering the API:

| Problem | Requests Generated |
|---------|-------------------|
| Guard script (every 5 mins) | 1 curl + starts bot |
| run_autotrader.sh network check | Up to 12 curl retries |
| KeepAlive LaunchAgent | Instant restart on crash |
| validate() failure → new Session | Auth request per failure |
| **Total during outage** | **Hundreds of requests/hour** |

---

## How the SDK Actually Works (v12)

### Session Lifecycle

```
Session() created → NO network call
    ↓
First API call (get positions, validate, etc.)
    ↓
_refresh() checks: is token expired?
    ↓
If expired → POST /oauth/token (THIS is the auth request)
    ↓
Token valid for ~15 minutes
    ↓
All subsequent API calls auto-refresh internally
```

**Key insight:** The SDK handles token refresh automatically. You should rarely need to create a new Session.

### What Triggers Auth Requests

| Action | Auth Request? |
|--------|---------------|
| `Session()` constructor | ❌ No |
| First API call after Session() | ✅ Yes (token refresh) |
| `session.validate()` | ❌ No (just checks validity) |
| API call when token expires | ✅ Yes (auto-refresh) |
| Creating NEW Session object | ✅ Yes (on first use) |

### The Original Simple Design (WORKED)

```
Startup:
  → Create Session
  → One auth request
  
Main loop:
  → Check time, enter trades at 14:45/15:00/15:30
  → Stream position updates (WebSocket, no polling)
  → Exit on profit target or EOD
  → SDK auto-refreshes tokens internally
  
No guard, no KeepAlive, no curl checks.
```

**This ran for days without issues.**

---

## What Broke It

### 1. Guard Script (market_session_guard.sh)

- Runs every 5 minutes via LaunchAgent
- Makes curl request to market-time API
- If bot not running → starts it
- **Problem:** During outages, guard keeps trying to start bot every 5 minutes

### 2. Network Check in run_autotrader.sh

```bash
# Makes up to 12 curl requests on every startup attempt
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    curl ... "$API_URL" ...  # 12 attempts × 5 second intervals
done
```

### 3. KeepAlive LaunchAgent (com.office.tasty0dte.plist)

```xml
<key>KeepAlive</key>
<true/>
```

**This is brutal.** Every time the bot crashes, launchd immediately restarts it. During an outage:
- Bot starts → network fails → crashes
- launchd restarts immediately
- Repeat infinitely

### 4. validate() Failure → New Session

The main.py code was creating new Session objects when validate() failed:

```python
if not auth_ok:
    session = new_session()  # This triggers auth on next API call
```

During network issues, validate() fails (timeout, not invalid token). Creating new Session + using it = auth request.

### 5. Compounding Effect

All these systems run independently:

```
Guard (every 5 min) → starts run_autotrader.sh
                         ↓
                    12 curl retries
                         ↓
                    Python starts
                         ↓
                    Session created
                         ↓
                    First API call → auth request
                         ↓
                    Network fails → crash
                         ↓
KeepAlive → immediately restarts
                         ↓
                    Auth request
                         ↓
                    Network fails → crash
                         ↓
                    (repeat forever)
```

**During the broadband outage:** Potentially 100+ auth requests per hour.

---

## Tastytrade API Limits (Based on Behavior)

Tastytrade hasn't published official rate limits, but based on experience:

| Limit Type | Estimated Threshold |
|------------|---------------------|
| Auth requests | ~30-50 per hour? |
| IP block duration | 24 hours (possibly longer) |
| API calls (general) | Very generous (thousands/hour) |

**The auth endpoint is the bottleneck.** Regular API calls (positions, quotes) have high limits. The OAuth token endpoint does not.

---

## What You Actually Need

### Core Requirements (from README)

1. **Automated Entry** at 14:45, 15:00, 15:30 UK time
2. **Position Monitoring** with real-time P&L (streaming)
3. **Auto Take-Profit** at target percentages
4. **Time Exits** (18:00 for 30 Delta, EOD for others)
5. **Paper Trading** mode for testing

### What You DON'T Need

- ❌ Guard script running every 5 minutes
- ❌ KeepAlive instant restarts
- ❌ Network pre-checks hitting the API
- ❌ Session validation every 2 minutes
- ❌ New Session creation on transient failures

---

## Recommended Architecture

### Option A: Simple Cron Start (Like Original)

```
Market open (14:30 UK):
  → cron runs: python main.py
  → Bot runs until EOD
  → Exits cleanly after market close
  → No guard, no KeepAlive
```

**Pros:** Simple, what worked originally
**Cons:** If bot crashes mid-day, no restart until tomorrow

### Option B: Smart Guard (Recommended)

```
Guard:
  → Runs every 30 minutes (not 5)
  → If market closed → do nothing
  → If market open AND bot not running → start it
  → If bot crashes 3 times → stop trying, alert you
  
Bot:
  → NO network checks in startup script
  → Single Session, never recreate
  → If network fails → wait and retry (don't exit)
  → If auth truly invalid → exit with special code (guard won't retry)
```

### Option C: Supervisor with Backoff

```
Use macOS launchd with:
  <key>ThrottleInterval</key>
  <integer>300</integer>  <!-- Wait 5 mins between restarts -->
  
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>  <!-- Only restart on crash, not clean exit -->
  </dict>
```

---

## Specific Code Changes Needed

### 1. Remove All Curl Checks

```bash
# DELETE this entire section from run_autotrader.sh:
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl ...
```

### 2. Never Create New Session on Transient Failures

```python
# WRONG:
if not auth_ok:
    session = new_session()

# RIGHT:
if not auth_ok:
    logger.warning("Session invalid, waiting 5 minutes...")
    await asyncio.sleep(300)
    # Try existing session again - SDK auto-refreshes
```

### 3. Distinguish Network Errors from Auth Errors

```python
def should_recreate_session(error: Exception) -> bool:
    """Only recreate session for actual auth failures, not network issues."""
    msg = str(error).lower()
    # These are REAL auth failures:
    if "invalid_grant" in msg or "unauthorized" in msg:
        return True
    # These are NETWORK issues - don't recreate:
    if "timeout" in msg or "connection" in msg or "network" in msg:
        return False
    return False
```

### 4. Use Smart Guard Instead of KeepAlive

```bash
# market_session_guard.sh changes:
# 1. Run every 30 minutes, not 5
# 2. Track consecutive failures in a file
# 3. If failures > 3, stop trying and send alert
# 4. No curl checks - just check if process running
```

### 5. Single Session, Handle Disconnects Gracefully

```python
async def main():
    session = Session(...)
    
    while True:
        try:
            await run_trading_loop(session)
        except NetworkError:
            logger.warning("Network error, waiting 5 minutes...")
            await asyncio.sleep(300)
            # Don't recreate session, just retry
        except AuthError:
            logger.error("Auth failed - token may be revoked")
            # This is the ONLY case to recreate session
            session = Session(...)
```

---

## Immediate Actions

1. ✅ **DONE:** Guard disabled, LaunchAgents unloaded
2. **Wait 24 hours** for IP unblock (or use VPN)
3. **Simplify startup:** Remove curl checks from run_autotrader.sh
4. **Simplify main.py:** Remove validate() loop and session recreation logic
5. **Test manually** before re-enabling any automation
6. **If guard needed:** Rewrite with 30-min interval and failure tracking

---

## Questions to Answer

Before rebuilding automation:

1. Do you need mid-day crash recovery? Or is "start at open, run til close" enough?
2. If the bot crashes at 16:00, is it acceptable to miss the 15:30 entry that day?
3. Do you want alerts when the bot is down, rather than auto-restart?

The simpler the recovery strategy, the less likely you are to hit rate limits.

---

## Summary

| What Worked | What Broke It |
|-------------|---------------|
| Single Session at startup | Creating Sessions on failures |
| Running during market hours only | KeepAlive + Guard fighting |
| Streaming for position updates | Polling + validate() checks |
| Clean exit at EOD | Aggressive restart loops |

**The original design was correct.** The "reliability" features added later caused the reliability issues.
