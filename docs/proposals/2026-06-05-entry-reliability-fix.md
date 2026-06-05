# Proposal: Fix silent 0DTE entry skips (parity-guard retry + cycle isolation)

**Date:** 2026-06-05
**Status:** ✅ IMPLEMENTED 2026-06-05 via the build-qa multi-model pipeline (Opus plan → Haiku build → Sonnet review → Opus approve → Codex independent review → fixes). All of Fixes 1–3 landed in `tasty0dte/main.py` (`_build_validated_trade`, `_fetch_chain_with_retry`, `_notify_skip`, `_notify_0dte_cycle_skip`); `validate_credit_sanity` kept its 2-tuple (zero churn to jade_lizard.py + 14 tests). Codex additionally caught silent chain-level skips + a config-read isolation gap (now fixed in both loops). 21 new tests in `tests/test_entry_reliability.py`; **full suite 117 green**. Applies on next 14:30 cron start. Commit pending (left uncommitted alongside the roster trim until you say so).
**Trigger:** Iron Fly V1 missed 3 of 4 entries the week of Jun 1 2026 (only Tuesday logged). User spotted the gaps in the V1 dashboard.

---

## 1. Evidence (from `runtime/logs/trade.log`)

```
Mon Jun 1 15:00:20  [Iron Fly V1] REJECTED: put-call parity violation at 7580: drift=$2.06 > $2.00 ... Skipping.
Tue Jun 2 15:00:33  [Iron Fly V1] Trade logged. Credit: $8.65          ← only day it passed
Wed Jun 3 15:00:28  [Iron Fly V1] REJECTED: parity drift=$2.18 > $2.00 ... Skipping.
Thu Jun 4 15:00:26  [Iron Fly V1] REJECTED: parity drift=$2.15 > $2.00 ... Skipping.
Thu Jun 4 15:00:31  ERROR - Trade cycle failed: ReadTimeout         ← V2 timed out, cascaded
```

Per-strategy this week: V3/V4 (15:30) and ORB traded **every day**; the 15:00 batch (V1/V2/Dynamic/JL) carried all the failures. The bot was **not** down — cron ran it 14:30–21:15 daily.

Frequency (full history): **21 parity rejections** — Iron Fly V4×7, V1×6, V2×4, V3×2, Dynamic×2 — clustering more often recently as SPX≈7600 makes a flat $2 tolerance relatively tighter. V1 took 3 of its 6 lifetime hits this single week.

## 2. Root causes

1. **No retry on the parity/credit guard.** `validate_credit_sanity` ([strategy.py:642](../../tasty0dte/strategy.py), `PARITY_TOLERANCE = $2.00`) rejects when `|(C−P) − (spot−strike)| > $2`. The caller ([main.py:206-208](../../tasty0dte/main.py)) just `continue`s — **one stale REST reading abandons the whole day's entry.** The guard itself is correct (it protects against the 2026-04-06 phantom-fill incident); the failure is giving up instead of re-reading.
2. **V1 is first in `STRATEGY_CONFIGS`** ([main.py:54](../../tasty0dte/main.py)), so it executes right at the 15:00 open spike and systematically catches the stalest marks. V2 fetches ~15 s later and passes. So the *same* trade would be valid moments later.
3. **No per-strategy isolation.** The entire `execute_trade_cycle` is wrapped in a single `try/except` at the call site ([main.py:316-318](../../tasty0dte/main.py)). An exception in one strategy (Thu: V2 `ReadTimeout`) propagates out and **aborts every later strategy** — that's why Dynamic never ran Thursday (the `return`-vs-`continue` pitfall from CLAUDE.md).
4. **Silent.** Rejections/skips are `logger.warning` in `trade.log` only — no Discord/dashboard signal. Invisible for weeks until spotted via dashboard gaps.

## 3. Fix

### Fix 1 — Retry the sanity check with fresh marks  *(addresses root cause #1/#2)*
- Change `validate_credit_sanity` to return `(is_valid, reason, retryable)`. Both failure modes (parity drift, max-credit/arbitrage) are stale-mark artifacts → `retryable=True`; missing-leg-data / genuine config issues → `retryable=False`.
- Wrap the leg-find → credit → validate block ([main.py:156-208](../../tasty0dte/main.py)) in a retry loop: on a retryable failure, `await asyncio.sleep(PARITY_RETRY_DELAY_S)`, **re-fetch the legs** (`find_iron_fly_legs`/`find_iron_condor_legs` → fresh REST marks) and **re-fetch `spx_spot`**, then re-validate. Up to `PARITY_RETRY_ATTEMPTS`.
- New constants (strategy.py): `PARITY_RETRY_ATTEMPTS = 3`, `PARITY_RETRY_DELAY_S = 6` (≈ up to 18 s of re-reads — well inside the entry window; mirrors why V2 naturally passes).
- After exhausting retries, skip as today **but** emit a notification (Fix 3).

### Fix 2 — Isolate each strategy in the cycle  *(addresses root cause #3)*
- Wrap each iteration body of the 0DTE loop ([main.py:135-227](../../tasty0dte/main.py)) **and** the Jade Lizard loop ([main.py:106-118](../../tasty0dte/main.py)) in `try/except Exception` → `logger.error(..., exc_info=True)` + notify + `continue`. One strategy's `ReadTimeout` must not skip the rest.
- Add a small retry (2–3 attempts) to the shared chain fetch ([main.py:122](../../tasty0dte/main.py)) — it's the one true cross-strategy dependency; if it still fails the cycle legitimately ends.

### Fix 3 — Surface every skip  *(addresses root cause #4)*
- On any entry rejection or per-strategy error, call `discord_notify` (guard `None`) with a one-line `⚠️ {strat} skipped at {time}: {reason}`.
- Optional: append skipped entries to a small `skips.csv` (or a dashboard badge) so misses are auditable.

### Fix 4 — Tolerance tuning *(optional, low priority once Fix 1 lands)*
- Consider scaling `PARITY_TOLERANCE` with spot (~0.03% of spot ≈ $2.3 at 7600) or bumping to $2.50. Size it by replaying the 21 historical rejections. The retry makes this mostly cosmetic.

## 4. Tests (`unittest`, fully mocked — safe to run mid-session)
- `validate_credit_sanity` returns the correct `retryable` flag for parity / max-credit / ok / missing-data.
- **Retry path:** mock `find_iron_fly_legs` to return stale marks then fresh → assert entry succeeds on the 2nd attempt; stale-throughout → assert skip after N attempts **and** a notify fired.
- **Isolation:** mock strategy *k* to raise `ReadTimeout` → assert strategies *k+1…n* still execute and the error is logged with `exc_info=True`.
- Use `AsyncMock` for the session/streamer per existing test patterns. **Do not** run the live bot (shared `trade.log` FileHandler — see `feedback_no_live_bot_tests_during_session.md`).

## 5. Rollout (Never Break Running System)
- Implement + test **outside** market hours; deploy when the bot is stopped (after the 21:15 cron stop or before the 14:30 start). `STRATEGY_CONFIGS` and entry code load on next cron start.
- Verify all imports against `venv/bin/python` (SDK version differs from system Python).
- Watch the first live session: confirm V1 enters, and that any retry/skip now produces a notification.

## 6. Related decision (separate from this fix): roster size
Cycle isolation (Fix 2) removes the *blast radius* of a crowded 15:00 batch, but the roster is independently worth trimming:
- **Reliability:** fewer strategies firing at 15:00 = smaller REST burst = fewer `ReadTimeout`s (the Thursday failure mode).
- **Returns (per `analysis/REPORT_2026-06-04.md`):** Dynamic 0DTE is net-negative since April, ORB Stacking isn't profitable yet, and V3/V4 are weak/insignificant. Concentrating on V1/V2 (+ watching JL) would *both* cut API contention and focus capital on the proven edge.
- This is a strategy decision for the owner, not part of the reliability patch. Recommend deciding it off the performance report, not just to reduce load.

## 7. Out of scope / noted
- Stale comment at [main.py:58](../../tasty0dte/main.py) still cites the bogus "Dynamic 0DTE +$7,418 over 13 trades" figure (same ~100× inflation corrected elsewhere) — worth cleaning when this file is next touched.
