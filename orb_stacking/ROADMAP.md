# ORB Stacking — Build Roadmap (Phase 1)

**Author:** Opus (Phase 1 architect)
**Supersedes:** nothing — first roadmap for the ORB Stacking pivot
**Companion doc:** `tag_n_turn/SOURCE_OF_TRUTH.md` (SoT) — all rules live there; this doc is how we build them
**Workflow:** Haiku codes each slice → Sonnet reviews diff against SoT + this roadmap → Haiku fixes → Opus signs off → next slice
**Hard rule:** everything stays in the package (`tag_n_turn/` → to be renamed `orb_stacking/`, see §B) until Slice 14 (Phase 6 integration). Live-bot files are OFF-LIMITS until then.

---

## A. Resolutions to the 7 open questions (SoT §5)

### A1. Single sizing scalar

**Decision.** Contract count is computed as:

```
contracts = clamp(round(BASE_UNIT × stack_mult × base_mult × calendar_mult), 1, MAX_CONTRACTS)
```

where

- `BASE_UNIT = 1` (paper-trading default; one contract per "NORMAL slot")
- `stack_mult` from the stacking ladder (SoT §2.4): `HALF=0.5, NORMAL=1.0, PLUS=1.5, DOUBLE=2.0`, `EXIT=0`
- `base_mult` from the base-setup tier (SoT §2.9): `HALF=0.5, NORMAL=1.0, PLUS=1.25, DOUBLE=1.5`
- `calendar_mult = 1.0 + 0.25 × calendar_score_clamped`, where `calendar_score_clamped ∈ [-2, +2]` (SoT §2.8 range)
- `MAX_CONTRACTS = 4` (paper-trading cap; revisited at Phase 6)

**Justification.** The two sources of size (stacking ladder + base grade) are independent per Doc1 §4/§20 and must compose multiplicatively rather than additively — adding `+2` from stacking to `+4` from base grading produces nonsense when both scales max at DOUBLE. Multiplicative composition preserves the "max-conviction = DOUBLE × DOUBLE" intuition (= 3.0×) while letting either axis downgrade the trade independently. Base-grade is dampened (1.0→1.5 vs stack's 0.5→2.0) because Doc1 Table 20 shows base-grade win-rate spread is only ~8.6 pts (59→67.6), much narrower than the stacking spread (35→90.9). Calendar mult uses ±25% per point so the catastrophic triple-witching (-2) halves size but FOMC (+1) only nudges up 25%. All factors clamped before rounding so a pathological combination cannot blow past `MAX_CONTRACTS`. Formula is implemented and unit-tested in Slice 9.

### A2. Bar source & candle-depth probe

**Decision.** Reuse the existing DXLink `subscribe_candle` path in `bar_fetcher.py`, switching `DEFAULT_INTERVAL` from `"30m"` to `"5m"` and `DEFAULT_LOOKBACK_DAYS` from 10 to 2. Run a one-shot candle-depth probe (Slice 1a) **before** any engine slice lands, to empirically verify that (a) DXLink honors `"5m"`, (b) historical warmup returns enough bars to seed ATR(14), (c) live closed-bar latency is <2s.

**Justification.** Project memory already claims `subscribe_candle(symbols, "5m", start_time)` works (SDK v12.0.0), and the existing `test_candle_depth.py` proves DXLink can stream SPX candles. But the current build only ever exercised `"30m"`, and `ORB20` tolerance is <60s — we cannot take a dependency on an interval we haven't actually probed on SPX during RTH. The probe is a 30-line script that asserts the three things above and runs once manually. Cheap insurance against finding out mid-build that the 5m feed has gaps.

### A3. Live Premium Popper integration path

**Decision.** Option (a): **build the full ORB Stacking pipeline inside `orb_stacking/` and migrate `premium_popper.py` in Slice 14 (Phase 6)**. Until Slice 14, `premium_popper.py` runs untouched in production, and the new package is exercised only via the demo CLI and unit tests.

**Justification.** CLAUDE.md's hardest rule is "Never Break Running System". `premium_popper.py` is live and holds state that interacts with `logger.py`, `monitor.py`, and the trade scheduler in `main.py`. Refactoring it in place means every Haiku commit can blow up the live session. Building alongside lets us (i) ship the engine end-to-end with zero live-bot risk, (ii) ship Slice 12 (demo CLI) and run it side-by-side with the live bot for a session or two to shake out bugs, (iii) make the Slice 14 cutover a single atomic swap: `main.py` stops calling `premium_popper.run_premium_popper` and starts calling `orb_stacking.run_orb_stacking`. The old `premium_popper.py` stays in the tree as a rollback artefact for one week post-cutover, then deletes.

### A4. Historical backtest pass

**Decision.** Yes — a headline-reproduction backtest is a **required build-quality gate**, slotted as **Slice 13** (after the full engine is live but before Phase 6 integration). It must reproduce two headline numbers from Doc1 within tolerance before cutover can happen:

- All-3-same day-favorable ≥ 78% (Doc1 §4.1: 80.3%, tolerance −2.3 pts)
- All-3-same + all-aligned day-favorable ≥ 88% (Doc1 §4.5: 90.9%, tolerance −2.9 pts)

If the backtest diverges more than tolerance, the cutover blocks and we diagnose before Slice 14. The backtester is a read-only replay of the 21yr 5-min CSV data through the closed-bar engine — no live SDK, no options pricing.

**Justification.** Doc1's numbers are the foundation of the pivot. If our implementation can't reproduce them on the exact data they came from, something is wrong in the ORB computation, breakout detection, or close-alignment logic, and shipping to live is malpractice. The gate lives at Slice 13 so it runs on the finished engine (including calendar overlays and base grader), not on half-built pieces. Slice 13 is optional per slice-sequencing but mandatory as a go/no-go gate before Slice 14.

### A5. A+ buffer comparator precision

**Decision.** Buffer is computed against the short strike candidate's target level (the OPPOSITE-side ORB20 boundary), and A+ qualifies when:

```python
def buffer_to_nearest_5(level: float) -> float:
    # distance from `level` to the NEAREST $5 strike, in $ (always 0..2.5)
    return min(level % 5, 5 - (level % 5))

# A+ setup when the protective ORB level sits $4 or more PAST the nearest $5 strike
# toward our short side. Precisely: the distance from the ORB level to the
# nearest $5 strike on the OPPOSITE side from the breakout is ≥ $4.
```

For the worked example in Doc2 (ORB20 high 5928.40, bull break): nearest $5 = 5925, buffer = $3.40 → **NOT A+** (`buffer < 4`). For a hypothetical 5929.00: nearest $5 = 5930, but 5930 is on the *wrong* side for a bull break — we measure distance to 5925, which is 4.00 → **A+**.

**Justification.** Doc1 §18's buffer × stacking table bins by $1 increments and the $4–5 bucket is where the 71.7% peak lives (vs 67.2% in $0–1). The precision question is whether we use `level % 5` (distance to nearest $5 ignoring direction) or "distance to the strike we'd actually pick". Doc2's example makes clear it's the latter: the $3.40 case is discussed as the less-protected case. Implementation uses the short-side target strike, which is deterministic once direction is known. Unit-tested with explicit fixture pairs in Slice 5.

### A6. Entry slippage / lock-bar timestamp tolerance

**Decision.** Lock events (ORB20/30/60) fire on the **closed-bar callback** for the bar whose `start` is the lock-minus-5min mark. Any closed bar arriving within `±3000 ms` of the nominal lock wall-clock time is treated as "on time"; beyond that, the engine logs a `STALE_LOCK_BAR` warning and still processes it (the bar is still valid SPX data; only the clock is slow). The entry order is placed on the NEXT tick after the closed-bar handler finishes, which in the demo CLI is immediate and in live mode is capped at 2s from breakout detection.

**Justification.** DXLink closed-bar events arrive 100–800ms after bar close in normal conditions; the 3s tolerance catches the 99th percentile without masking a broken feed. We intentionally key on bar events (not wall-clock timers) because the bar IS the source of truth — a missing bar is a problem the engine must detect, whereas a late bar is just network jitter. Slice 4 (stacking state machine) codifies this tolerance as `LOCK_TOLERANCE_MS = 3000`.

### A7. Test fixture timezone convention

**Decision.** **Test fixtures use UTC-aware datetimes** for bar `start` fields; the engine accepts UTC, normalizes internally to ET for ORB lock comparisons, and emits UK-time strings only in logging/output fields. The bar dataclass uses `datetime` objects (TZ-aware) throughout — no naive datetimes anywhere.

Helper: `_bar(utc_hhmm, o, h, l, c)` in tests, where `utc_hhmm` is a `"HH:MM"` string interpreted as UTC on a canonical test date (`2025-06-03`, a Tuesday non-OpEx non-FOMC day to avoid calendar overlay contamination).

**Justification.** Doc1's raw data is UTC (14:30 UTC = 09:30 ET). Using UTC in fixtures means tests read cleanly against the docs without mental arithmetic for DST shifts. The engine's ET normalization is trivial (ET = UTC − 4 in DST, UTC − 5 in standard) and lives in one helper (`to_et()`) so it's easy to audit. UK time only matters at the edges — the human-facing log line and the eventual `main.py` trigger — so it's a presentation-layer concern, not engine state.

---

## B. Package rename decision

**Decision.** Rename `tag_n_turn/` → `orb_stacking/` as **Slice 0** (first commit of the build).

**Justification.** The SoT is explicit that the original Tag N Turn methodology is shelved "by decision, not by data". Keeping the directory name under the new methodology creates permanent confusion — every time someone greps "tag_n_turn" they'll hit ORB code. The git history of the rename IS the pivot story and is valuable. External references are small and enumerated below.

### External references requiring update during Slice 0

1. `memory/projects/0dte-bot.md` — any references to `tag_n_turn/` path
2. `/Users/office/.claude/projects/-Users-office-Projects-tasty0dte-ironcondor/memory/MEMORY.md` — "Key Files" section, "Tag N Turn" section header, `project_tag_n_turn.md` reference
3. `CLAUDE.md` — only mentions `tag_n_turn` in passing; should be updated or annotated that ORB Stacking lives in `orb_stacking/`
4. `tag_n_turn_demo.py` — rename to `orb_stacking_demo.py` AND update all imports
5. `test_candle_depth.py` — no rename needed; it's already strategy-agnostic
6. Test discovery command — update to `python -m unittest discover -s orb_stacking/tests -t .`
7. `feedback_*.md` files under `~/.claude/projects/.../memory/` — leave as historical artefacts, add one new feedback file pointing to the rename
8. No live-bot file (`main.py`, `strategy.py`, `monitor.py`, etc.) currently imports from `tag_n_turn/`, so Slice 0 touches zero live code

Slice 0 is a git `mv` + find-and-replace + test-run. No logic changes. Gated on Sonnet verifying all 154 existing tests still pass under the new path (even though most will be deleted in Slice 2).

---

## C. Current file inventory — verified verdicts

I verified the SoT §4.1 inventory by reading every file. Corrections and additions below.

| File | SoT verdict | Verified verdict | Notes |
|---|---|---|---|
| `__init__.py` | Keep (rename) | **Keep (rename + rewrite docstring)** | Docstring still says "BB(30) tag + pulse bar" — must be updated Slice 0 |
| `bar_fetcher.py` | Adapt | **Adapt** | Correct. The 30m→5m switch is literally a constant change (`DEFAULT_INTERVAL`), plus reducing lookback and validating warmup. Candle dedup / garbage-filter / live-stream logic carries over unchanged. |
| `indicators.py` | Partial keep | **Partial keep** | ATR class kept as-is. `BollingerBands` and `MACDV` classes deleted. Tests for ATR survive; BB/MACDV tests deleted. |
| `signals.py` | Shelve entirely | **Delete entirely** | Correct. None of `is_bb_tag`, `bb_penetration_atr`, `detect_v_pattern`, `is_pulse_bar`, `pulse_bar_range` has any use in ORB Stacking. Replaced by a new `breakout.py` (Slice 3). |
| `scoring.py` | Shelve | **Delete entirely** | Correct. Every scoring function (`score_v_pattern`, `score_macdv_light`, `score_pulse_strength`, `score_time_of_day`, `score_bb_depth`) is meaningless under ORB Stacking. The `composite_score / get_tier / TIERS` pattern is conceptually reusable but cleaner to rewrite than to hack. Replaced by `grader.py` (Slice 8). |
| `stops.py` | Shelve | **Delete entirely** | Correct. PFZ is a pattern-failure concept from Tag N Turn; ORB Stacking uses bracket OCO on credit + a hard ORB60-opposes exit. Replaced by `exits.py` (Slice 10). |
| `trade_intent.py` | Adapt | **Rewrite** | The dataclass naming is fine but every field except `timestamp`, `direction`, `spread_side`, `score`, `tier`, `sizing_mult`, `factors` must change. Cleaner to write a new file than to edit in place. `SkippedSetup` is kept conceptually (new reasons). |
| `entry_engine.py` | Replace entirely | **Replace entirely** | Correct. New file (`engine.py`) with a time-indexed stacking state machine instead of a BB-tag → window → pulse state machine. The "closed-bar → state machine → emit intent" shape survives; the guts don't. |
| `tests/test_bar_fetcher.py` | Shelve | **Adapt** | The bar-fetcher tests (history fetch, garbage filter, closed-bar streaming) all still apply — only the interval constant changes. Tests port over with minor edits. |
| `tests/test_indicators.py` | Shelve | **Prune** | Keep all `TestATR` cases; delete `TestBollingerBands` and `TestMACDV` classes. |
| `tests/test_signals.py` | Shelve | **Delete** | Correct. |
| `tests/test_scoring.py` | Shelve | **Delete** | Correct. |
| `tests/test_stops.py` | Shelve | **Delete** | Correct. |
| `tests/test_entry_engine.py` | Shelve | **Delete** | Correct. Replaced by new engine tests in Slice 4+. |

**Net survivor files after Slice 2 prune:** `__init__.py`, `bar_fetcher.py` (interval tweaked), `indicators.py` (ATR only), `tests/test_bar_fetcher.py` (interval tweaked), `tests/test_indicators.py` (ATR only). ~350 LOC survives out of ~1550.

---

## D. Implementation slices

Slices are numbered 0–14. Each slice must satisfy its DoD before the next one starts. Sonnet reviews against SoT + this roadmap + the slice's own checklist. Where a slice number references another, it's a hard dependency.

### Conventions

- **Package root:** `orb_stacking/` (renamed in Slice 0)
- **Test run:** `python -m unittest discover -s orb_stacking/tests -t .`
- **LOC target per slice:** ≤300 lines of new/changed code including tests
- **All datetimes:** `datetime` objects, TZ-aware (UTC inside the engine, UK string in human output)
- **No live-bot imports** until Slice 14

---

### Slice 0 — Package rename + prune

**Subject.** Physically rename the package and delete files that die under the pivot.

**Files:**
- rename `tag_n_turn/` → `orb_stacking/` (git mv)
- delete `orb_stacking/signals.py`, `scoring.py`, `stops.py`, `trade_intent.py`, `entry_engine.py`
- delete `orb_stacking/tests/test_signals.py`, `test_scoring.py`, `test_stops.py`, `test_entry_engine.py`
- prune `orb_stacking/indicators.py` to ATR-only (delete `BollingerBands`, `MACDV` classes)
- prune `orb_stacking/tests/test_indicators.py` to `TestATR` only
- update `orb_stacking/__init__.py` docstring to describe ORB Stacking
- rename `tag_n_turn_demo.py` → `orb_stacking_demo.py` (will be rewritten in Slice 12; for now leave a stub that raises `NotImplementedError("demo rewrite pending in Slice 12")`)
- update `MEMORY.md` Key Files section and Tag N Turn section heading
- update `CLAUDE.md` if it references `tag_n_turn/` path (grep confirms no reference — skip)

**Public API contract:** `orb_stacking.indicators.ATR` still exists and behaves identically. Nothing else is imported yet.

**Test plan:** Run `python -m unittest discover -s orb_stacking/tests -t .`. Only `TestATR` tests should exist and they must all pass (expected ~9 tests).

**DoD:**
- `grep -r "tag_n_turn" .` returns 0 hits except in git history and `feedback_*.md` historical files
- All ATR tests pass
- Old BB/MACD/signals/scoring/stops/entry_engine files are gone
- `orb_stacking_demo.py` exists as a stub
- No live-bot file imports anything from `orb_stacking/`

**Sonnet review checklist:**
1. Verify `git mv` was used (preserves history) not copy+delete
2. Verify the `MACDV` class and all its helper state is gone from `indicators.py`
3. Verify `TestBollingerBands` and `TestMACDV` classes are gone from `test_indicators.py`
4. Verify `orb_stacking/__init__.py` docstring no longer mentions "BB(30) tag"
5. Verify test command works verbatim from repo root
6. Verify no stray `from tag_n_turn` imports remain anywhere in the repo
7. Verify `premium_popper.py` still runs (import-wise) — it should, since it never imported Tag N Turn

---

### Slice 1 — Bar fetcher pivot to 5m + timezone helpers

**Subject.** Switch the bar fetcher to 5-minute SPX candles and add a small timezone utility module. Includes a manual candle-depth probe script.

**Files:**
- MODIFY `orb_stacking/bar_fetcher.py`:
  - `DEFAULT_INTERVAL = "5m"`
  - `DEFAULT_LOOKBACK_DAYS = 2` (5m × 2 days ≈ 160 bars, plenty for ATR(14) warmup)
  - Add `WARMUP_MIN_BARS = 30` constant
  - Add method `fetch_history_with_retry()` that retries the fetch once if the first call returns < `WARMUP_MIN_BARS` bars
- CREATE `orb_stacking/time_utils.py` (~60 LOC):
  - `UK_TZ = pytz.timezone('Europe/London')`
  - `ET_TZ = pytz.timezone('America/New_York')`
  - `to_et(dt)`, `to_uk(dt)`, `to_utc(dt)` — idempotent
  - `lock_times_et()` → `{"ORB20": time(9,50), "ORB30": time(10,0), "ORB60": time(10,30)}`
  - `is_lock_bar(bar_start, orb_name)` — returns True if the bar STARTS at 9:45/9:55/10:25 ET (i.e. would close at the lock moment)
  - `entry_window_closed(dt)` — True after 12:00 ET (Doc1 §9, late-session dead zone)
- MODIFY `orb_stacking/tests/test_bar_fetcher.py` — update interval constant, keep all existing test structure
- CREATE `orb_stacking/tests/test_time_utils.py` — unit tests for each helper, using UTC fixtures crossing both DST boundaries
- CREATE `tools/probe_5m_candles.py` (~40 LOC, one-shot manual probe). Run separately, not a unit test. Asserts a live SPX 5m subscription produces ≥ `WARMUP_MIN_BARS` bars on 2-day lookback AND produces a closed-bar event within 6 minutes of subscription start during RTH.

**Public API contract:**
```python
# orb_stacking.bar_fetcher
BarFetcher(symbol="SPX", interval="5m", lookback_days=2)
  .fetch_history(session) -> list[dict]
  .stream_closed_bars(session) -> AsyncIterator[dict]

# orb_stacking.time_utils
to_et(dt) / to_uk(dt) / to_utc(dt) -> datetime
lock_times_et() -> dict[str, time]
is_lock_bar(bar_start: datetime, orb_name: str) -> bool
entry_window_closed(dt: datetime) -> bool
```

**Test plan:**
- Port existing `test_bar_fetcher.py` (mock DXLink, verify dedup + garbage filter + close-bar emission)
- ≥12 tests in `test_time_utils.py` covering: DST boundary days, lock-bar detection for each ORB, entry-window-closed edge cases around 11:59 / 12:00 / 12:01 ET, round-trip conversions
- Probe script runs manually and logs bar timing to stdout — NOT part of CI, NOT required for slice DoD, but must be committed and documented

**DoD:**
- All existing (adapted) bar-fetcher tests pass with `"5m"` interval
- ATR (14) warms up successfully when fed the first 14 bars from `fetch_history()` of a synthetic 2-day lookback
- Probe script exists and is documented in the slice commit message
- No functional change to dedup / garbage-filter behaviour

**Sonnet review checklist:**
1. Verify `DEFAULT_INTERVAL = "5m"` and `DEFAULT_LOOKBACK_DAYS = 2`
2. Verify `time_utils.is_lock_bar` correctly identifies the bar that *closes* at 9:50/10:00/10:30 ET (i.e. bar whose `start` is 09:45/09:55/10:25 ET)
3. Verify DST handling in `to_et` uses `pytz.localize` / `astimezone` correctly, never naive arithmetic
4. Verify `entry_window_closed` uses ≥ 12:00 ET, not 11:59 or 12:01 (Doc1 §9 cutoff)
5. Verify `test_time_utils.py` covers both March and November DST shifts
6. Verify no test sleeps / no test hits live DXLink
7. Verify probe script is clearly marked as manual-only in its docstring
8. Verify `__init__.py` exports the new `time_utils` module

---

### Slice 2 — ORB level computation (ORB20 / ORB30 / ORB60)

**Subject.** Given a stream of closed 5m bars on a single trading day, compute high/low/range/midpoint/close for each of the three ORB windows and lock them at the right moments. No breakout detection yet.

**Files:**
- CREATE `orb_stacking/orb_levels.py` (~140 LOC):
  - `@dataclass OrbLevels` with fields `high, low, range, midpoint, close, close_pct, locked_at, name`
  - `class OrbBuilder`: accepts closed bars, exposes `update(bar) -> None`, `locked(name) -> OrbLevels | None`, `all_locked() -> bool`, `reset_for_new_session() -> None`
  - `close_pct = (close - low) / range` — undefined (None) if `range == 0`
  - Lock semantics: `ORB20` locks on the bar whose START is 09:45 ET (which closes at 09:50 ET); `ORB30` on START=09:55 ET; `ORB60` on START=10:25 ET. The lock bar is the LAST bar included in the range.
- CREATE `orb_stacking/tests/test_orb_levels.py` (~180 LOC, ~15 tests):
  - 4 bars 09:30/09:35/09:40/09:45 ET → ORB20 locks at the 09:45 bar with the max/min of all 4 bars' high/low and the 09:45 bar's close
  - Adding a 09:50 bar does not modify ORB20
  - ORB30 requires all 6 bars 09:30..09:55 ET
  - ORB60 requires all 12 bars 09:30..10:25 ET
  - Session boundary: feeding a bar from a different date resets (asserts `OrbBuilder` is per-session)
  - Out-of-order bars (late arrival) raise or are rejected — decide and test
  - `close_pct` edge cases: range=0, close at exact low, close at exact high
  - Mid-build query: `locked("ORB30")` before 10:00 ET returns None

**Public API contract:**
```python
@dataclass
class OrbLevels:
    name: str            # "ORB20" | "ORB30" | "ORB60"
    high: float
    low: float
    range: float
    midpoint: float
    close: float
    close_pct: Optional[float]   # None if range == 0
    locked_at: datetime          # UTC, = bar.start + 5min

class OrbBuilder:
    def update(self, bar: dict) -> list[OrbLevels]:  # returns any ORBs that LOCKED on this bar
    def locked(self, name: str) -> Optional[OrbLevels]
    def all_locked(self) -> bool
    def reset_for_new_session(self) -> None
```

**Test plan:** unittest with synthetic UTC bars on `2025-06-03`. Use a `_bar(utc_hhmm, o, h, l, c)` helper that matches SoT §A7 decision.

**DoD:** 15+ passing tests; no dependency on `indicators.py`; pure data transformation.

**Sonnet review checklist:**
1. Verify the lock moments (ORB20 = bar START 09:45 ET, ORB30 = 09:55 ET, ORB60 = 10:25 ET) — one off-by-one here silently poisons everything downstream
2. Verify `close_pct` formula matches SoT §2.2 exactly: `(close - low) / (high - low)` for THAT ORB's final bar (not the instantaneous session close)
3. Verify ORB20 high/low is max/min across 4 bars, NOT just the last bar's high/low
4. Verify DST-aware ET comparison (use `time_utils.to_et` and compare `time()` components, not naive hour math)
5. Verify a bar arriving at 10:30 ET does NOT re-open ORB60
6. Verify session reset clears all three ORBs
7. Verify `range == 0` → `close_pct is None` (not `0.0`, not crash)
8. Verify no coupling to any future module — this file should import only stdlib + `time_utils`

---

### Slice 3 — Breakout detection (Confirmation mode only)

**Subject.** Given an ORB and subsequent closed bars, detect the first bar that closes STRICTLY outside the ORB range. Wick-only does not count (Doc4: penetration mode is dead).

**Files:**
- CREATE `orb_stacking/breakout.py` (~90 LOC):
  - `@dataclass Breakout` fields: `orb_name, direction ("bull"|"bear"), bar, close, timestamp, bars_since_lock`
  - `class BreakoutDetector` holds a reference ORB, tracks whether already fired (one-shot per ORB), exposes `check(bar) -> Optional[Breakout]`
  - Strictly `close > high` or `close < low` — equality is NOT a breakout
  - Function `immediate_breakout(bo: Breakout) -> bool`: True if `bars_since_lock <= 1` (the lock bar or the bar immediately after). Doc1 §9: "immediate" is the 9:50–10:00 ET window, which is the lock bar + 1.
- CREATE `orb_stacking/tests/test_breakout.py` (~180 LOC, ~18 tests):
  - Wick above high, close inside → no breakout
  - Close exactly at high → no breakout (strict >)
  - Close one cent above → bull breakout
  - Second bar also above high → still same Breakout object, no double-fire
  - Bar closes below low after previously closing above high → bear breakout IS reported (detector is one-shot per DIRECTION-AGNOSTIC first close outside)
    - CORRECTION: clarify in spec that the detector is one-shot TOTAL — the first breakout wins, subsequent reversals are handled by exit logic, not breakout detection
  - `bars_since_lock` counting for "immediate" classification
  - Null ORB → detector raises on construction

**Public API contract:**
```python
@dataclass
class Breakout:
    orb: OrbLevels
    direction: str        # "bull" | "bear"
    bar: dict
    timestamp: datetime
    bars_since_lock: int  # 0 if breakout closes ON the lock bar, 1 next bar, etc.

class BreakoutDetector:
    def __init__(self, orb: OrbLevels): ...
    def check(self, bar: dict) -> Optional[Breakout]

def immediate_breakout(bo: Breakout) -> bool  # bars_since_lock <= 1
```

**Test plan:** 18+ tests, Confirmation mode only, strict comparisons, one-shot behaviour.

**DoD:** All tests pass; no penetration-mode code path exists; detector is pure and stateless except for the one-shot flag.

**Sonnet review checklist:**
1. Verify `close > high` is STRICT (not `>=`) — Doc1 §2 "close outside range"
2. Verify no wick-based logic exists (Doc4: Penetration mode dead)
3. Verify the detector one-shots after first valid breakout
4. Verify `bars_since_lock = 0` when breakout is on the LOCK bar itself (i.e. 09:45 ET bar closing at 09:50 ET above ORB20 high)
5. Verify `immediate_breakout` threshold matches Doc1 §9 (≤ 1 bar after lock = 10:00 ET cutoff on ORB20)
6. Verify no coupling to calendar / base grader / stacking state
7. Verify a Breakout's `timestamp` equals the CLOSE time of the bar (= `bar.start + 5min`), not the start

---

### Slice 4 — Stacking state machine (the heart of the strategy)

**Subject.** Consume bars, drive `OrbBuilder` and three `BreakoutDetector`s, emit stacking events (`ORB20_BREAK`, `ORB30_CONFIRM`, `ORB30_OPPOSE`, `ORB60_CONFIRM`, `ORB60_OPPOSE`, `ORB60_NO_BREAKOUT`, `TIMEOUT_NOON`). This slice defines the state-machine output contract that every subsequent slice hangs off.

**Files:**
- CREATE `orb_stacking/stacking.py` (~220 LOC):
  - `class StackingState`: holds current position state (`FLAT | HALF | NORMAL | PLUS | DOUBLE | EXITED`), direction (`None | "bull" | "bear"`), breakout history (list of three slots), and close-alignment flags per ORB
  - `class StackingEngine.on_closed_bar(bar) -> list[StackingEvent]` — drives the state machine
  - Events:
    - `ORB20_BREAK(direction, base_score_placeholder)` — fires HALF entry
    - `ORB30_CONFIRM` — bump HALF→NORMAL
    - `ORB30_OPPOSE` — flag warning; does NOT exit in this slice (reduce-vs-exit decided in Slice 10)
    - `ORB60_CONFIRM` — bump NORMAL→PLUS (and count close-alignments for possible DOUBLE)
    - `ORB60_OPPOSE` — hard exit signal
    - `ORB60_NO_BREAKOUT` — informational; hold
    - `TIMEOUT_NOON` — fires once when first bar past 12:00 ET closes with no ORB20 breakout
  - Lock bar tolerance `LOCK_TOLERANCE_MS = 3000` per §A6
  - Close-alignment per ORB: `close_pct ≥ 0.80` for bull, `≤ 0.20` for bear (SoT §2.2)
  - `all_three_same()`, `close_alignment_count()` query methods
- CREATE `orb_stacking/tests/test_stacking.py` (~320 LOC — this is the biggest test file in the build):
  - 7 canonical permutations from Doc1 §4.1 table — one fixture day per row
  - Edge cases: ORB20 breakout on the lock bar itself; ORB20 never breaks → `TIMEOUT_NOON` fires at first bar ≥ 12:00 ET; stale bar past lock tolerance emits `STALE_LOCK_BAR` log but still processes
  - Close alignment counting: 0/1/2/3 aligned scenarios
  - Session reset between two simulated days

**Public API contract:**
```python
@dataclass
class StackingEvent:
    kind: str          # "ORB20_BREAK" | "ORB30_CONFIRM" | ...
    direction: Optional[str]
    orb: Optional[OrbLevels]
    bar: dict
    timestamp: datetime
    state_snapshot: dict  # {"stack_tier": "PLUS", "closes_aligned": 2, ...}

class StackingEngine:
    def __init__(self): ...
    def on_closed_bar(self, bar: dict) -> list[StackingEvent]
    def reset_for_new_session(self): ...
    @property
    def current_tier(self) -> str  # "FLAT" | "HALF" | "NORMAL" | "PLUS" | "DOUBLE" | "EXITED"
    @property
    def direction(self) -> Optional[str]
```

**Test plan:** 7 permutation fixtures × assertions on emitted event sequence + tier + direction; ≥25 tests total.

**DoD:** All 7 Doc1 §4.1 permutations correctly emit the expected event sequence and leave the state machine in the expected terminal tier.

**Sonnet review checklist:**
1. Verify the 7 permutations from Doc1 §4.1 are each a test case, named after the row (e.g. `test_same_same_all_3_confirm`, `test_same_opp_orb60_exits`, etc.)
2. Verify close-alignment thresholds: `close_pct >= 0.80` for bull, `<= 0.20` for bear (SoT §2.2) — not 0.75/0.25, not strict vs loose inequality mismatches
3. Verify state cannot regress (HALF→FLAT is forbidden; only EXITED is a terminal downgrade)
4. Verify `ORB60_OPPOSE` fires as a first-class event, not as a side-effect of something else — Slice 10 depends on it
5. Verify `ORB30_OPPOSE` does NOT force-exit (Doc1 §4.7 says warning, not exit; exit is handled in Slice 10)
6. Verify `TIMEOUT_NOON` uses `time_utils.entry_window_closed` (12:00 ET cutoff per Doc1 §9, Doc4)
7. Verify session reset between days — a Tuesday that never breaks out must not leak state into Wednesday
8. Verify `current_tier` transitions are unidirectional (`FLAT → HALF → NORMAL → PLUS → DOUBLE → EXITED`), and DOUBLE only reachable from PLUS + enough close-alignments
9. Verify lock tolerance logs but does not drop the bar

---

### Slice 5 — Strike selection + A+ buffer

**Subject.** Given a stacking event (with direction + ORBs) and a list of available strikes, compute the short/long strike for a $5-wide credit spread and the buffer to the nearest $5 strike for A+ classification.

**Files:**
- CREATE `orb_stacking/strike_selector.py` (~120 LOC):
  - `select_short_strike(orb20: OrbLevels, direction: str, strike_grid_step: int = 5) -> int`
    - Rule: short = nearest $5 strike to ORB20 midpoint, on the OPPOSITE side from the breakout (SoT §2.6)
    - For bull breakout: short is a PUT below midpoint
    - For bear breakout: short is a CALL above midpoint
  - `long_strike(short: int, direction: str, width: int = 5) -> int`
    - bull (put spread): `short - 5`
    - bear (call spread): `short + 5`
  - `buffer_to_nearest_5(level: float) -> float` — per §A5 precision decision
  - `is_a_plus_setup(orb20: OrbLevels, direction: str) -> bool` — buffer ≥ 4.0 using the comparator above
  - `validate_credit(credit: float) -> tuple[bool, str]` — returns (valid, reason); credit < 0.80 → skip; > 1.50 → proceed-cautiously
- CREATE `orb_stacking/tests/test_strike_selector.py` (~180 LOC, ~20 tests):
  - Doc2 worked example: ORB20 high 5928.40, low 5919.80, bull break → short strike at ORB20 midpoint (5924.10) → nearest $5 = 5925 → short = 5925 PUT, long = 5920 PUT
  - A+ buffer: ORB20 high 5928.40, bull break → buffer = |5925 − 5928.40| on the protective side = $3.40 → NOT A+
  - A+ buffer: ORB20 high 5929.00, bull break → buffer = $4.00 → A+
  - Credit validation: 0.79 → skip, 0.80 → valid, 1.50 → valid with caution flag, 1.51 → valid with caution flag, 0.50 → skip
  - Bear-side symmetry

**Public API contract:**
```python
def select_short_strike(orb20: OrbLevels, direction: str, grid: int = 5) -> int
def long_strike(short: int, direction: str, width: int = 5) -> int
def buffer_to_nearest_5(level: float) -> float
def is_a_plus_setup(orb20: OrbLevels, direction: str) -> bool
def validate_credit(credit: float) -> tuple[bool, str]
```

**Test plan:** 20+ tests with explicit Doc2-sourced fixtures.

**DoD:** Doc2 worked example passes exactly. A+ buffer comparator matches §A5 decision.

**Sonnet review checklist:**
1. Verify SoT §2.6: short strike at ORB20 MIDPOINT, on OPPOSITE side (this was the old Premium Popper's bug — it used 20-delta, which isn't wrong but is inferior)
2. Verify the Doc2 worked example (ORB20 5919.80–5928.40, bull, midpoint 5924.10, short strike 5925) — exact pass required
3. Verify A+ is ≥ 4.0 (not > 4.0) — SoT §2.6
4. Verify the buffer comparator uses the distance from the ORB protective level (ORB20 high for bull) to the nearest $5 strike ON THE SHORT SIDE, not blindly `level % 5`
5. Verify `validate_credit` boundaries: ≥ 0.80 valid, > 1.50 cautious, anything < 0.80 rejected
6. Verify the selector does NOT use delta — this is a pure price-distance rule
7. Verify bull / bear symmetry is tested explicitly
8. Verify strike_grid_step is a parameter, not a magic number (will matter for XSP in future)

---

### Slice 6 — Range expansion ratio + calendar overlay

**Subject.** Two small quality-signal modules. Range expansion is computable at ORB60 lock; calendar overlay is computable at session start.

**Files:**
- CREATE `orb_stacking/range_expansion.py` (~40 LOC):
  - `range_expansion_ratio(orb20: OrbLevels, orb60: OrbLevels) -> float` — `orb60.range / orb20.range`
  - `expansion_bonus(ratio: float) -> int` — SoT §2.5: ≥ 2.5x → +1 quality flag, else 0
- CREATE `orb_stacking/calendar_overlay.py` (~180 LOC):
  - Hardcoded 2025-2027 lookup for FOMC Wednesdays, quarter-end dates, triple/quad witching Fridays, OpEx Fridays
  - `calendar_score(date: date) -> tuple[int, list[str]]` — returns (score, labels); max ∈ [-2, +2] per SoT §2.8
  - Rules (SoT §2.8): FOMC Wed +1, quarter-end +1, last Friday of month +1, triple/quad witching -2, OpEx Friday -1
- CREATE tests:
  - `orb_stacking/tests/test_range_expansion.py` (~30 LOC, 5 tests: ratio math, boundary at 2.5x, zero-range ORB20 raises)
  - `orb_stacking/tests/test_calendar_overlay.py` (~120 LOC, ~15 tests covering each overlay category across 2025-2027 with named example dates)

**Public API contract:**
```python
def range_expansion_ratio(orb20: OrbLevels, orb60: OrbLevels) -> float
def expansion_bonus(ratio: float) -> int  # 0 or +1

def calendar_score(d: date) -> tuple[int, list[str]]
```

**Test plan:** 20 total tests; explicit named dates for known FOMCs (e.g. 2026-01-28, 2026-03-18, 2026-06-17, …) and 2026 triple-witching (2026-03-20, 2026-06-19, 2026-09-18, 2026-12-18).

**DoD:** All tests pass; every calendar category is represented by at least one real date from 2026.

**Sonnet review checklist:**
1. Verify the hardcoded FOMC list is accurate for 2026 (cross-reference against a public FOMC calendar in the PR description)
2. Verify triple-witching is -2 not -1 (SoT §2.8) and OpEx Fridays are -1
3. Verify "last Friday of month" logic handles months whose last Friday is ALSO the OpEx Friday or triple-witching Friday (precedence rule: take the worst score, i.e. sum them but clamp to [-2, +2])
4. Verify `calendar_score` returns labels too, for logging transparency
5. Verify `expansion_bonus` boundary is INCLUSIVE at 2.5x (`>= 2.5` → +1)
6. Verify `range_expansion_ratio` raises / returns `inf` if orb20.range == 0 — edge case must be explicit
7. Verify calendar file has a TODO comment reminding to re-populate for 2027 before Dec 2026

---

### Slice 7 — Base setup grader

**Subject.** Compute the base setup score at ORB20 lock per SoT §2.9 / Doc1 §20 / Doc2 base-grade table.

**Files:**
- CREATE `orb_stacking/grader.py` (~160 LOC):
  - `@dataclass GraderInputs`: `orb20, direction, breakout_timing_immediate, atr14, day_of_week, buffer_dollars`
  - `grade_base_setup(inputs: GraderInputs) -> dict` returning `{score, tier, factors_breakdown}` where factors_breakdown is a dict per SoT §2.9 table
  - Factor rules from SoT §2.9:
    - `orb_atr_ratio = orb20.range / atr14`:
      - < 0.20 → +2
      - 0.20–0.30 → +1
      - > 0.40 → -1
      - 0.30–0.40 → 0 (gap in the doc; explicit 0)
    - `immediate` → +1
    - ORB20 close aligned with breakout direction (≥ 0.80 bull or ≤ 0.20 bear) → +1
    - Thursday (weekday 3) or Friday (weekday 4) → +1
    - Monday (weekday 0) → -1
    - Buffer ≥ $4 → +1; buffer < $1 → -1
  - Tier mapping SoT §2.9: `≤ -1 → HALF`, `0-1 → NORMAL`, `2-3 → PLUS`, `≥ 4 → DOUBLE`
- CREATE `orb_stacking/tests/test_grader.py` (~200 LOC, ~22 tests):
  - Doc2 worked example fixture (SPX 5920, ATR 65, ORB range 8.60, Tuesday, buffer 3.40, immediate, aligned): expect score = +2 +1 +1 +0 +0 = +4, tier DOUBLE — cross-check with Doc2 "Base grade: +4 = DOUBLE" (Doc2 says +4 with buffer 0, we'll replicate that)
    - NOTE: Doc2 example shows +2 (ATR) +1 (immediate) +1 (aligned) +0 (Tue) +0 (buffer $3.40) = +4. This is the canonical fixture.
  - Each factor in isolation
  - Tier boundary tests (score = -1, 0, 1, 2, 3, 4)
  - Edge case: Tuesday scores 0 (Doc4 says Tuesday is dead as a factor — the grader must NOT give Tuesday any bonus or penalty)

**Public API contract:**
```python
@dataclass
class GraderInputs:
    orb20: OrbLevels
    direction: str
    breakout_timing_immediate: bool
    atr14: float
    day_of_week: int   # 0=Mon .. 6=Sun
    buffer_dollars: float

def grade_base_setup(inputs: GraderInputs) -> dict
# returns {"score": int, "tier": str, "factors_breakdown": dict}
```

**Test plan:** 22+ tests; explicit Doc2 worked-example fixture is the headline test.

**DoD:** Doc2 worked example returns `{"score": 4, "tier": "DOUBLE"}`. Tuesday bonus is exactly 0.

**Sonnet review checklist:**
1. Verify the ATR ratio bins match Doc1 §20 table EXACTLY (<20% +2, 20-30% +1, 30-40% 0, >40% -1)
2. Verify `>=` vs `>` boundaries: `orb_atr < 0.20` not `<=` (ambiguity in the doc, standard interpretation is strict)
3. Verify Tuesday returns 0 (Doc4 killed Tuesday as a DOW factor)
4. Verify Wednesday returns 0 too (only Thu/Fri get +1, only Mon gets -1)
5. Verify buffer dollars factor is strictly ≥ $4 → +1 and strictly < $1 → -1 (the $1-$4 range is 0)
6. Verify the tier boundaries are inclusive on the LOW end: `score == 2 → PLUS`, `score == 4 → DOUBLE`
7. Verify no gap handling (Doc4 killed gaps — grader must not reference gap size anywhere)
8. Verify no MACD-V anywhere in this file

---

### Slice 8 — Trade intent dataclasses + skip schema

**Subject.** Define the output contracts for the engine. No logic.

**Files:**
- CREATE `orb_stacking/trade_intent.py` (~120 LOC):
  - `@dataclass OrbTradeIntent` — the rich event object the Slice 14 integration consumes:
    - `timestamp, direction, spread_side ("put"|"call"), short_strike, long_strike, expected_credit, stack_tier, base_tier, contracts, stack_score, base_score, calendar_score, calendar_labels, closes_aligned_count, range_expansion_ratio, is_a_plus_buffer, is_immediate, orb20, orb30, orb60, notes`
  - `@dataclass OrbSkipEvent` — logged when engine decides not to trade or exits:
    - `timestamp, reason, direction, orb20, orb30, orb60, stack_tier, base_tier, notes`
  - `SKIP_REASONS` enum/list: `"no_breakout_before_noon"`, `"orb20_close_middle_bear"`, `"orb30_opposes_warning"`, `"orb60_opposes_hard_exit"`, `"base_tier_skip"`, `"credit_too_low"`, `"credit_too_high_flagged"`, `"api_error"`, `"calendar_blocked"`, `"daily_cap"`
- CREATE `orb_stacking/tests/test_trade_intent.py` (~40 LOC, 5 tests): dataclass construction, default values, schema completeness (every field listed above exists), `SKIP_REASONS` is a frozen set

**Public API contract:**
```python
@dataclass
class OrbTradeIntent: ...
@dataclass
class OrbSkipEvent: ...
SKIP_REASONS: frozenset[str]
```

**Test plan:** 5 structural tests.

**DoD:** Dataclasses importable, no runtime logic, schemas match the fields that Slice 12/13/14 will consume.

**Sonnet review checklist:**
1. Verify every field the downstream slices (9, 10, 12, 14) reference is present
2. Verify `OrbSkipEvent` uses the exact `SKIP_REASONS` strings — no free-text reasons allowed
3. Verify `notes` is a free-text field separate from `reason`
4. Verify no `MACDV`, `pulse_bar`, `v_pattern`, `bb_at_entry` fields leak from the old `trade_intent.py`
5. Verify the two dataclasses are frozen=False (mutation during construction is expected)
6. Verify `expected_credit` is a float and `contracts` is an int

---

### Slice 9 — Sizing combiner

**Subject.** The formula from §A1. Pure function.

**Files:**
- CREATE `orb_stacking/sizing.py` (~80 LOC):
  - Constants: `BASE_UNIT=1, MAX_CONTRACTS=4, STACK_MULT, BASE_MULT, CALENDAR_MULT_PER_POINT=0.25`
  - `compute_contracts(stack_tier: str, base_tier: str, calendar_score: int) -> dict` — returns `{contracts, stack_mult, base_mult, calendar_mult, raw, clamped}`
- CREATE `orb_stacking/tests/test_sizing.py` (~140 LOC, ~18 tests):
  - HALF × HALF × 0 = `0.5 × 0.5 × 1.0 = 0.25 → 1 contract (floor at 1)`... but wait: clamp floor is 1 ONLY when stack_tier is not EXITED. Decision: if stack_tier == "EXITED" OR raw < 0.5, contracts = 0 (i.e. no trade). Otherwise round-then-clamp to [1, MAX_CONTRACTS].
  - NORMAL × NORMAL × 0 = 1.0 → 1 contract
  - PLUS × DOUBLE × +1 = `1.5 × 1.5 × 1.25 = 2.8125 → 3`
  - DOUBLE × DOUBLE × +1 = `2.0 × 1.5 × 1.25 = 3.75 → 4`
  - DOUBLE × DOUBLE × +2 = `2.0 × 1.5 × 1.50 = 4.5 → 4 (clamped)`
  - Triple witching (calendar_score = -2): `2.0 × 1.5 × 0.5 = 1.5 → 2`
  - EXITED → 0

**Public API contract:**
```python
def compute_contracts(stack_tier: str, base_tier: str, calendar_score: int) -> dict
# keys: contracts, stack_mult, base_mult, calendar_mult, raw, clamped
```

**Test plan:** 18+ tests; explicit numerical fixtures for every interesting combination.

**DoD:** All combinations of (5 stack tiers × 4 base tiers × 5 calendar scores) computable; formula traceable in the returned dict.

**Sonnet review checklist:**
1. Verify the formula matches §A1 exactly (multiplicative, clamped, rounded)
2. Verify `stack_tier == "EXITED"` → `contracts = 0` (hard zero)
3. Verify `MAX_CONTRACTS = 4` clamp is applied AFTER rounding
4. Verify `calendar_score` clamp to `[-2, +2]` is applied INSIDE the function, not pushed onto caller
5. Verify the returned dict includes ALL intermediate values so diagnostics can reconstruct the decision
6. Verify floor behaviour: `raw < 0.5` → 0 contracts (no trade), `0.5 ≤ raw < 1.0` → 1 contract (floor), otherwise normal rounding
7. Verify no floating-point precision bugs on boundary (e.g. `0.5 × 0.5 × 1.5` should not drift)
8. Verify HALF × HALF × -2 = 0.25 × 0.5 = 0.125 → 0 contracts (tiny × bad calendar = skip)

---

### Slice 10 — Exits module (bracket OCO parameters + ORB60-opposes hard exit)

**Subject.** Compute bracket OCO target/stop levels and signal the hard-exit transition on ORB60_OPPOSE.

**Files:**
- CREATE `orb_stacking/exits.py` (~100 LOC):
  - `bracket_levels(entry_credit: float, target_pct: float = 0.50, stop_mult: float = 2.0) -> dict` — `{target_debit, stop_debit}` (target = credit × 0.5, stop = credit × 2.0)
  - `@dataclass HardExitSignal`: `reason ("orb60_opposes" | "orb30_opposes_reduce"), timestamp, position_tier_before, position_tier_after`
  - `evaluate_exit_signal(event: StackingEvent) -> Optional[HardExitSignal]` — consumes a StackingEvent and returns a hard-exit signal if applicable
    - `ORB60_OPPOSE` → `reason="orb60_opposes"`, tier → `EXITED`
    - `ORB30_OPPOSE` → `reason="orb30_opposes_reduce"`, tier goes from NORMAL → HALF (warning, not exit — per SoT §2.4 and Doc2 STEP 2)
- CREATE `orb_stacking/tests/test_exits.py` (~120 LOC, ~14 tests)

**Public API contract:**
```python
def bracket_levels(entry_credit: float, target_pct: float = 0.50, stop_mult: float = 2.0) -> dict
@dataclass
class HardExitSignal: ...
def evaluate_exit_signal(event: StackingEvent) -> Optional[HardExitSignal]
```

**Test plan:** 14 tests: bracket math, ORB60_OPPOSE → EXITED, ORB30_OPPOSE → reduce (not exit), other events return None.

**DoD:** Every exit-path from SoT §2.7 is represented.

**Sonnet review checklist:**
1. Verify target = `entry_credit * 0.50` and stop = `entry_credit * 2.0` (SoT §2.1)
2. Verify `ORB30_OPPOSE` is a REDUCE warning (HALF), NOT a full exit — Doc2 STEP 2 is explicit
3. Verify `ORB60_OPPOSE` is a FULL EXIT regardless of current tier (SoT §2.7)
4. Verify the function returns `None` for all non-exit events so callers can use it as a filter
5. Verify the `HardExitSignal.reason` strings match exactly what the logger expects
6. Verify no P/L-based exit logic lives here — that's the bracket's job
7. Verify EOD handling is NOT in this slice (lives in Slice 14 integration)

---

### Slice 11 — Full engine assembly

**Subject.** Wire everything from Slices 2–10 into one `OrbStackingEngine` class that consumes closed bars and emits `OrbTradeIntent` or `OrbSkipEvent` objects. This is the public face of the package.

**Files:**
- CREATE `orb_stacking/engine.py` (~260 LOC):
  - `class OrbStackingEngine`:
    - owns: ATR(14), OrbBuilder, StackingEngine, (BreakoutDetector instances created on lock), calendar_score (computed once per session), session date
    - `on_closed_bar(bar) -> list[events]` — each event is an `OrbTradeIntent` or `OrbSkipEvent`
    - On ORB20_BREAK: grade base setup, compute calendar, compute initial sizing (HALF × base_tier × calendar), select strikes (but `expected_credit` is `None` at this stage — live mode fills it in; demo/backtest mode leaves None), emit intent with `stack_tier="HALF"`
    - On ORB30_CONFIRM: emit intent with `stack_tier="NORMAL"` and recomputed sizing
    - On ORB30_OPPOSE: emit SkipEvent reason `"orb30_opposes_warning"` (not a real skip, a log marker)
    - On ORB60_CONFIRM: emit intent with `stack_tier="PLUS"` or `"DOUBLE"` depending on close-alignment count (0-1 aligned → PLUS, 2-3 aligned → DOUBLE)
    - On ORB60_OPPOSE: emit SkipEvent reason `"orb60_opposes_hard_exit"`
    - On TIMEOUT_NOON: emit SkipEvent reason `"no_breakout_before_noon"` (once)
    - Session rollover: reset everything
- CREATE `orb_stacking/tests/test_engine.py` (~300 LOC, 20+ tests):
  - Full-day replays of the 7 canonical permutations, asserting the emitted events sequence AND sizing contract counts
  - Cross-day session reset
  - Warmup (not enough ATR history) → no events emitted until ATR is ready

**Public API contract:**
```python
class OrbStackingEngine:
    def __init__(self, atr_period: int = 14, max_contracts: int = 4): ...
    def on_closed_bar(self, bar: dict) -> list[Union[OrbTradeIntent, OrbSkipEvent]]
    def reset_for_new_session(self): ...
```

**Test plan:** 20+ tests, full-day replays from Slice 4's fixtures extended with base grade + calendar.

**DoD:** End-to-end: fed a day of bars, the engine emits a sequence of intents and skip events that match the canonical permutation expected outcome, with correctly computed sizing.

**Sonnet review checklist:**
1. Verify the engine imports ONLY from `orb_stacking/*` (no live-bot imports)
2. Verify ORB20_BREAK emits an intent with `stack_tier == "HALF"` (not "NORMAL" — that only comes with ORB30 confirm)
3. Verify DOUBLE is only reachable when `closes_aligned_count >= 2` AND ORB60 confirms
4. Verify close-alignment count is computed at ORB60 lock, not incrementally updated wrong
5. Verify session reset clears EVERYTHING (ATR is NOT reset — it's multi-day, but stacking state is)
6. Verify warmup suppresses emissions until ATR is ready (otherwise base grader divides by None)
7. Verify calendar_score is computed once per session from the day's date, not re-evaluated each bar
8. Verify ORB30_OPPOSE produces a SkipEvent (warning log), not a TradeIntent downgrade — the downgrade is implicit in the next sizing-intent event
9. Verify every emitted OrbTradeIntent has all required fields populated (use a completeness assertion helper)
10. Verify no DOUBLE emission on ORB20_BREAK or ORB30_CONFIRM — it's ORB60-gated

---

### Slice 12 — Demo CLI (read-only replay of live DXLink)

**Subject.** Replace the stub `orb_stacking_demo.py` with a working read-only CLI that connects to live DXLink, streams 5m closed bars through the engine, and prints events to stdout. Safe to run alongside the live bot.

**Files:**
- REWRITE `orb_stacking_demo.py` (~180 LOC):
  - CLI: `python orb_stacking_demo.py [--replay DATE]` — replay mode reads historical bars from DXLink with a start_time; live mode streams closed bars
  - Instantiates `BarFetcher("SPX", "5m", lookback_days=1)`, warms up ATR, then streams
  - Pretty-prints every `StackingEvent`, `OrbTradeIntent`, `OrbSkipEvent` with timestamps in UK time
  - Exits cleanly on Ctrl-C and on `TIMEOUT_NOON` or `ORB60_OPPOSE` event

**Public API contract:** script, not importable. Entry point `main(argv)`.

**Test plan:** Manual — run during a live session and confirm: (a) bars arrive, (b) events print in the right order, (c) no exceptions. Add ONE unit test that mocks the bar fetcher with a synthetic day and verifies the CLI printer emits the expected lines.

**DoD:** Script runs end-to-end during RTH and prints sensible output without affecting the live bot.

**Sonnet review checklist:**
1. Verify the demo does NOT import anything from `main.py`, `monitor.py`, `strategy.py`, `logger.py`, or `premium_popper.py`
2. Verify the demo does NOT attempt to place any orders — it's strictly read-only
3. Verify ATR warmup happens before the first live bar is processed
4. Verify the printer formats timestamps in UK time (user-facing)
5. Verify Ctrl-C is handled cleanly (no traceback spam)
6. Verify running the demo does not create or append to `paper_trades.csv`, `trade.log`, or any live-bot log file
7. Verify a `--replay` mode exists and reads from DXLink history (not from CSV)

---

### Slice 13 — Historical backtest gate (21yr data)

**Subject.** One-shot script that replays the 21yr 5-min SPX CSVs through the engine and reproduces the Doc1 §4.1 / §4.5 headline numbers. Required to pass before Slice 14.

**Files:**
- CREATE `tools/backtest_orb_stacking.py` (~300 LOC — this slice is the only one allowed >300 LOC because it's a build-quality gate script):
  - Ingest the 4 CSVs under `/docs/SPX 5 min + MACDv - *.txt`, dedupe + sort
  - Yield closed bars grouped by session
  - Run each session through `OrbStackingEngine`
  - Track per-session: what permutation fired, whether day closed favorable per Doc1's definition (`close > open` bull / `close < open` bear), whether close was past ORB20 boundary, closes-aligned count
  - Final report: reproduce Doc1 §4.1 permutation table (7 rows × [days, %, day-favorable]) and §4.5 close-alignment table (5 rows × [days, day-favorable])
  - Gate assertion: all-3-same day-favorable ≥ 78.0%, all-3-same + all-aligned ≥ 88.0% (per §A4)
- CREATE `tools/tests/test_backtest_smoke.py` (~60 LOC, 3 tests): feed 5 synthetic sessions, assert report structure is correct. Do NOT run the full 21yr replay in CI.

**Public API contract:** script, not importable. Entry point `main()`.

**Test plan:**
- CI: smoke test on 5 synthetic sessions
- Manual: `python tools/backtest_orb_stacking.py` takes ~2-5 min on the full dataset, prints the report, exits nonzero if gate fails

**DoD:** Full 21yr run prints the Doc1 §4.1 permutation table within the tolerance stated in §A4. Gate assertion passes. Report committed as `tools/backtest_orb_stacking_report_<date>.txt`.

**Sonnet review checklist:**
1. Verify CSV ingestion dedupes by timestamp correctly
2. Verify session grouping uses ET date, not UTC date (a 23:55 UTC bar is next-day ET in winter)
3. Verify the engine is fed bars in strict chronological order per session
4. Verify the "day favorable" definition matches Doc1 §4 exactly
5. Verify the "past ORB20" definition matches SoT §2.2 and Doc1 §4
6. Verify the reported totals sum to the expected ~5,220 sessions
7. Verify the gate thresholds match §A4 (≥78.0% and ≥88.0%) and exit nonzero on failure
8. Verify the smoke test in CI does not touch the real CSVs
9. Verify no live-bot imports in the tool
10. Verify report output is committed alongside the script so divergences over time are visible in git history

---

### Slice 14 — Phase 6 LIVE INTEGRATION (THE ONLY SLICE THAT TOUCHES LIVE-BOT FILES)

**Subject.** Wire `OrbStackingEngine` into the live bot as the replacement for `premium_popper.py`. Atomic cutover with one-week rollback window.

**Files:**
- CREATE `orb_stacking/live_runner.py` (~220 LOC) — the live adapter:
  - `async def run_orb_stacking(session)` — mirrors `premium_popper.run_premium_popper` signature
  - Instantiates `BarFetcher` + `OrbStackingEngine`
  - On each `OrbTradeIntent` with `contracts > 0`: call `strategy_mod._find_credit_spread_legs` (or a thin ORB-aware wrapper) to price the selected strikes, validate credit, log via `trade_logger.log_trade_entry`, send Discord notification
  - On each `OrbSkipEvent`: log via new `trade_logger.log_skip_event` (add this helper in a minimal logger.py patch)
  - Bracket OCO: existing `monitor.py` handles profit-target / stop-loss
  - Hard exit: on `ORB60_OPPOSE` skip event, enqueue an exit in monitor.py by marking the open trade with a `force_close_reason="orb60_opposes"` flag that monitor.py honors on its next tick
- MODIFY `main.py` (~10 lines):
  - Replace `import premium_popper` with `from orb_stacking import live_runner`
  - Replace `premium_popper.run_premium_popper(session)` with `live_runner.run_orb_stacking(session)`
  - Change the launch trigger: currently `14:30 UK`, stays `14:30 UK` — the ORB20 lock is at 14:50 UK (US DST) / 13:50 UK (US standard), well within the window (DST checklist: verify BEFORE merging)
- MODIFY `logger.py` (~30 lines): add `log_skip_event(skip_event: OrbSkipEvent)` writing to a new `skip_events.csv` file
- MODIFY `monitor.py` (~20 lines): add handling for `force_close_reason` on open trades
- KEEP `premium_popper.py` in tree for 1 week post-cutover as rollback artifact, then delete in a follow-up commit

**Public API contract:**
```python
# orb_stacking.live_runner
async def run_orb_stacking(session) -> None
```

**Test plan:**
- NEW `orb_stacking/tests/test_live_runner.py` (~200 LOC, ~12 tests) mocking Session + bar fetcher + logger, feeding a full-day bar sequence and verifying: trades logged, exits honored, hard-exit flag set
- Full existing test suite must still pass: `python -m unittest test_monitor test_fly_legs -v`
- Pre-merge checklist: (i) run the demo CLI alongside the live bot for one full session without the new `main.py` changes, (ii) verify it prints the same decisions the live Premium Popper would have made (ignoring strike selection), (iii) then merge the `main.py` change
- Post-merge: monitor first live session. Rollback plan = revert the `main.py` lines to re-enable `premium_popper.py`

**DoD:**
- `main.py` launches `live_runner.run_orb_stacking` instead of `premium_popper.run_premium_popper`
- First live session produces either a trade or a logged skip event — no exceptions
- `trade.log` hierarchy per CLAUDE.md reflects the new strategy name (`ORB Stacking`) in strategy_id / strategy_name columns
- `paper_trades.csv` entries have `Strategy` field populated with `ORB Stacking` variants (`ORB-STACK-HALF`, `ORB-STACK-NORMAL`, `ORB-STACK-PLUS`, `ORB-STACK-DOUBLE`) via strategy_id
- All pre-existing tests pass (`python -m unittest test_monitor test_fly_legs -v`)
- `premium_popper.py` still importable but not wired in

**Sonnet review checklist:**
1. Verify `main.py` diff is minimal (≤15 lines changed) — the whole live-bot touch should be surgical
2. Verify the launch time (14:30 UK) is correct for CURRENT DST state (audit against CLAUDE.md DST checklist AND `feedback_dst_time_changes.md`)
3. Verify `premium_popper.py` is NOT deleted in this slice — rollback window
4. Verify `live_runner.run_orb_stacking` catches all exceptions and logs them, never crashes the bot loop
5. Verify `logger.log_skip_event` writes to a NEW file (`skip_events.csv`), does NOT pollute `paper_trades.csv`
6. Verify the `force_close_reason` monitor hook is additive — does not change existing exit logic for non-ORB trades
7. Verify `strategy_name="ORB Stacking"` is consistent with `trade_logger.log_trade_entry` conventions and downstream Discord formatting
8. Verify no live trade is placed BEFORE all base-setup/calendar/sizing checks have run
9. Verify a `contracts == 0` intent is logged as a skip, NOT traded
10. Verify the rollback procedure is documented in the slice commit message
11. Verify Slice 13's backtest gate passed BEFORE this slice is merged

---

## E. Out of scope / V2

Explicitly deferred — must NOT appear in any slice above without a roadmap update:

- **2nd Breakout** (continuation trade after retrace to ORB20 mid) — blueprint §"What This Blueprint Does NOT Cover"
- **3rd Breakout** (ORB60 as a separate entry, same Popper mechanics) — same source
- **Lazy Popper** (hold to expiry, no stop, 30-delta) — same source
- **Anchored VWAP** overlays — same source
- **BWB (broken wing butterfly) structures** — Doc1 §19; flagged as theoretically attractive but out of scope until credit spreads are dialed in
- **Dynamic stop tuning** ($5/$10/$15 from Doc1 §10 table) — future V2; stays at fixed 2× credit stop via bracket OCO for now
- **Histogram ±40 management warning** (Doc4: "marginal exception" — management nice-to-have) — not an entry rule, explicit NO
- **RUT / XSP** instruments — SPX-only in V1; XSP is listed in SoT §2.1 as sizing flexibility but the live integration targets SPX
- **MACD-V in any form** — permanently dead per Doc4
- **Historical backtest of SKIP reasons** — only the headline "did we reproduce Doc1 §4.1/§4.5" is gated; richer backtests are V2
- **PDT rule enforcement** — inherited from `main.py`; the ORB Stacking runner does not add new PDT logic (existing bot's 3-trades-per-5-day counter covers it)
- **Tag N Turn methodology** — shelved by decision; cannot be re-introduced without a new SoT revision

---

## F. Risks and watch-outs

| Risk | Early-detection guardrail | Slice |
|---|---|---|
| DXLink 5m candles don't stream closed bars fast enough to hit lock times | Manual probe in Slice 1 with explicit latency assertion | Slice 1 |
| Lock-bar identification off-by-one (using bar start vs close, 09:45 vs 09:50) silently destroys the strategy | Dedicated `test_orb_levels.py` tests with explicit UTC fixtures AND dedicated `test_stacking.py` tests with canonical permutations | Slices 2, 4 |
| Close-alignment threshold drift (0.80 vs 0.75 vs 0.79) quietly corrupts DOUBLE tier | Unit tests assert EXACTLY 0.80/0.20 boundaries; Sonnet checklist item flags it explicitly | Slice 4 |
| Base grader diverges from Doc1 §20 | Doc2's worked example (+4 → DOUBLE) is a headline test case in Slice 7 | Slice 7 |
| Calendar overlay hardcoded dates go stale end of 2026 | TODO comment in `calendar_overlay.py`; roadmap out-of-scope section calls it out | Slice 6 |
| Sizing formula produces 0 contracts for valid setups (combinatorial dead zones) | 18+ unit tests cover every tier × tier × calendar combination | Slice 9 |
| Backtest reproduces numbers within tolerance BUT the gap reveals a real bug we ignore as "close enough" | Gate threshold is tight (−2.3 and −2.9 pts); any miss forces a diagnosis pass | Slice 13 |
| Slice 14 integration introduces a crash in the live bot loop | `run_orb_stacking` wraps its body in a try/except that logs and returns, never propagates; plus rollback window via retained `premium_popper.py` | Slice 14 |
| ORB60_OPPOSE hard exit fails to reach monitor.py before bracket OCO hits stop | Monitor hook is checked on every tick (~10s); exit latency ≤ 10s worst case; documented in the slice commit | Slice 14 |
| DST handoff between US and UK in early March / late March drifts the 14:30 UK trigger | Slice 1 `time_utils` has explicit DST tests, Slice 14 references CLAUDE.md DST checklist in its review checklist | Slices 1, 14 |
| Hidden live-bot import creeps into an `orb_stacking/*` file and the "don't touch live bot" rule silently breaks | Every slice checklist item 1–2 asks Sonnet to grep for live-bot imports; Slice 14 is the ONLY slice allowed to add them | Every slice |
| Backtest gate uses wrong "day favorable" definition and reports a false positive | Explicit Sonnet checklist item asks for Doc1 §4 quote in the PR description | Slice 13 |
| Strike selector's A+ buffer comparator disagrees with Doc2 worked example | Doc2 worked example IS a headline test in Slice 5 | Slice 5 |
| Engine emits multiple TradeIntents per lock event (duplicate entries) | `test_engine.py` tests assert exactly-one intent per stacking transition | Slice 11 |
| 5m bar feed has a gap during a lock window → ORB computation is wrong | `OrbBuilder.update` tracks bar count; if ORB20 locks with fewer than 4 bars it MUST emit a SkipEvent (`bar_gap_during_lock`) — add this to `SKIP_REASONS` in Slice 8 | Slices 2, 8 |
| Unit tests drift out of sync with the SoT as rules refine | SoT has "last reconciled" line; any slice that changes a rule must bump it | Every slice |

---

## Slice dependency graph

```
0  (rename + prune)
│
1  (bar fetcher 5m + time_utils)
│
2  (orb_levels) ── depends on 1
│
3  (breakout) ── depends on 2
│
4  (stacking engine) ── depends on 2, 3
│
5  (strike_selector)        6  (range_exp + calendar)        7  (grader)
    depends on 2               depends on 2                    depends on 2
│                               │                                │
└──────────┬───────────────┬────┘                                │
           │               │                                     │
           8  (trade_intent dataclasses) ─ depends on 2           │
           │                                                     │
           9  (sizing) ── depends on 4, 7, 6                      │
           │                                                     │
          10  (exits) ── depends on 4                             │
           │                                                     │
          11  (engine assembly) ── depends on 2, 3, 4, 5, 6, 7, 8, 9, 10
           │
          12  (demo CLI) ── depends on 1, 11
           │
          13  (backtest gate) ── depends on 11
           │
          14  (LIVE INTEGRATION) ── depends on 11, 13 (gate must pass)
```

---

## Summary table

| # | Slice | LOC est (code + tests) | Touches live bot? |
|---|---|---|---|
| 0 | Rename + prune | ~0 (deletions + moves) | no |
| 1 | Bar fetcher 5m + time_utils | ~250 | no |
| 2 | ORB levels | ~320 | no |
| 3 | Breakout detection | ~270 | no |
| 4 | Stacking state machine | ~540 | no |
| 5 | Strike selector | ~300 | no |
| 6 | Range expansion + calendar | ~370 | no |
| 7 | Base setup grader | ~360 | no |
| 8 | Trade intent dataclasses | ~160 | no |
| 9 | Sizing combiner | ~220 | no |
| 10 | Exits module | ~220 | no |
| 11 | Engine assembly | ~560 | no |
| 12 | Demo CLI | ~220 | no |
| 13 | Backtest gate | ~360 | no |
| 14 | Live integration | ~450 | **YES (only this slice)** |

**Total:** 15 slices, ~4,600 LOC including tests, spread across ~14 Haiku sessions. Slice 4 and Slice 11 are the heaviest; Slice 0 is near-zero code.

---

## Items genuinely needing user input before the build loop starts

**None.** Every design decision in §A has been made. The only thing that requires the user is pressing "go" on Slice 0. If the user wants to override any decision in §A, §B, §C, §E, or change the slice sizing cap (300 LOC), say so before Slice 0 starts.

---

## SoT corrections / gaps discovered while writing this roadmap

1. **SoT §2.9 has a gap in the ATR ratio bins.** The table specifies `<20% → +2`, `20-30% → +1`, `>40% → -1` but omits `30-40%`. Doc1 §20 has the same gap. The roadmap (Slice 7) resolves this as `30-40% → 0` (explicit zero). **Recommend the user adds this explicit zero to SoT §2.9.**

2. **SoT §2.8 calendar overlay precedence is not specified.** If a date is BOTH last-Friday-of-month (+1) AND OpEx Friday (-1), what's the score? Roadmap decision: sum-then-clamp to `[-2, +2]`. **Recommend SoT §2.8 adds a one-liner: "overlays are additive, clamped to [-2, +2]".**

3. **SoT §4.1 under-scales `tests/test_bar_fetcher.py`** — it says "Shelve with their modules" but the bar fetcher tests actually port over cleanly to 5m (only the interval constant changes). Roadmap §C corrects this to "Adapt".

4. **SoT §4.2 says UK time should be `16:30 / 16:50 / 17:00 / 17:30 UK during BST`** — these numbers are wrong. 09:30 ET during BST (when UK is on BST too) is 14:30 UK, not 16:30 UK (which is actually afternoon ET). The correct BST-period UK lock times are 14:50 / 15:00 / 15:30 UK. **Recommend the user corrects SoT §4.2 before Slice 1 starts.** This is the highest-priority SoT fix because an off-by-2-hour error silently breaks the whole lock-time subsystem.

5. **SoT §2.7 "EOD: ITM/borderline → close before 15:50 ET"** — the time is 15:50 ET but should it be UK-clock-expressed too? Roadmap defers to Slice 14 where this becomes an explicit `EOD_CUTOFF_UK` constant pinned to DST state.

6. **SoT §5 Q2** says project memory already confirms `"5m"` works; the roadmap instructed Slice 1 to still run a candle-depth probe because memory is not the same as verification.

---

**End of roadmap.**
