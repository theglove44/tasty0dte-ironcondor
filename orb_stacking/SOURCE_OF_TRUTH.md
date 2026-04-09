# Tag N Turn → ORB Stacking — Source of Truth

**Status:** Active calibration reference. All build work must conform to this document. If a piece of code disagrees with this doc, the code is wrong.
**Last reconciled:** 2026-04-09
**Owner thesis pivot:** The original Tag N Turn methodology (BB(30) tag + pulse bar + MACD-V Traffic Light + V-pattern + 5-factor scoring) is **shelved**. The package is being repurposed to implement **ORB Stacking** — the dominant edge surfaced by 21 years of SPX 5-min research.

### Changelog
- **2026-04-09 (post-Slice 2):** Added the `bar_gap_during_lock` contract to §2.2 definitions. Codifies the Slice 2 decision that an ORB is skipped (not locked) whenever a bar at or past its lock boundary is observed without every required in-window bar present. Downstream slices (3–14) may rely on "locked OR skipped with reason — never indefinitely pending" as a precondition.
- **2026-04-08 (post-Opus Phase 1):** Five corrections caught by Opus roadmap pass:
  1. §4.2 — UK lock times were off by ~2 hours; fixed to BST-correct values (14:50 / 15:00 / 15:30 UK).
  2. §2.9 — ATR/ORB ratio bin `30–40%` was missing; added explicitly as `0` points.
  3. §2.8 — calendar overlay precedence undefined; added "sum then clamp to [-2, +2]".
  4. §4.1 — `test_bar_fetcher.py` verdict corrected from "Shelve" to "Adapt" (tests port cleanly to 5m).
  5. §2.7 — EOD cutoff was ET-only; flagged that `EOD_CUTOFF_UK` constant lives in Slice 14 with DST awareness.

---

## 1. Source Documents

All under `/Users/office/Projects/tasty0dte-ironcondor/docs/`. Skim-indexed; full re-reads only when a build question requires it.

| File | Role | One-line summary |
|---|---|---|
| `Doc1_Full_Research_Briefing.md` | **Primary research** | 21yr / 409,644 bar / 5,270 session study. Establishes ORB Stacking as the core edge. Section 4 = the discovery; sections 5-20 = supporting tables. |
| `Doc2_Trading_Playbook_Checklist.md` | **Operational spec** | Step-by-step trading rules derived from Doc1. The mechanical playbook. This is what code must implement. |
| `Doc4_Dead_Ends_Register.md` | **Negative space** | Authoritative list of what NOT to build. Most importantly: every flavour of MACD-V is dead. |
| `premium_popper_blueprint.md` | **Legacy seed doc** | March-2026 ORB20-only first-breakout spec. Predates the stacking discovery. Useful for execution mechanics (strike selection, bracket orders, no-trade logging) but the entry framework is superseded by Doc2. |
| `SPX 5 min + MACDv - *.txt` (4 files, ~71MB total) | **Raw data** | 21yr SPX 5-min OHLC + MACD-V. **Not ingested into this doc.** Available as backtest fuel if needed. |

**Conflict-resolution rule:** When two docs disagree, the order of authority is **Doc2 > Doc1 > Doc4 > blueprint**. Doc4 trumps everything *only* on what to NOT build.

---

## 2. The Strategy (ORB Stacking)

### 2.1 Instrument & structure

| Param | Value |
|---|---|
| Instrument | SPX (primary). XSP for sizing flexibility. |
| Options | 0DTE, cash-settled, European-style |
| Structure | Vertical credit spread, $5 wide |
| Target credit | ~$1.00 (acceptable $0.80–$1.50) |
| Profit target | 50% of credit (buy back at half) |
| Stop loss | 100% of credit added (buy back at 2× entry) |
| Bar timeframe for entry logic | **5-minute SPX OHLC** |
| Trading window | 09:50–12:00 ET (entries); hold to EOD per management rules |
| Trading window in UK time (BST) | **14:50–17:00 UK** (during BST). Outside BST: subtract 1 hour from UK column. |

### 2.2 Definitions

- **ORB20:** opening range high/low over the first 20 minutes (09:30–09:50 ET, four 5-min bars).
- **ORB30:** first 30 minutes (09:30–10:00 ET, six 5-min bars).
- **ORB60:** first 60 minutes (09:30–10:30 ET, twelve 5-min bars).
- **Breakout (Confirmation mode):** a 5-min bar **close** strictly outside the ORB high (bull) or low (bear). Wick-only does NOT count. (Doc4: Penetration mode is dead, -8.1% vs Confirmation.)
- **Lock time:** the moment a given ORB freezes — 09:50 / 10:00 / 10:30 ET (= 14:50 / 15:00 / 15:30 UK during BST; subtract 1hr outside BST).
- **Close position within ORB:** `(orb_close - orb_low) / (orb_high - orb_low)` for that ORB's final-bar close. Aligned-with-bull = close ≥ 0.80; aligned-with-bear = close ≤ 0.20.
- **Range expansion ratio:** `orb60_range / orb20_range`.
- **All 3 same:** ORB20 broke direction X, ORB30 broke direction X, ORB60 broke direction X.
- **Bar gap during lock (`bar_gap_during_lock`):** an ORB is marked SKIPPED — not locked — if at any point before it locks, the engine observes a 5-min bar whose start is at or past that ORB's lock-bar start without every required in-window bar being present. This catches three variants: (a) the lock bar arrives but a prior in-window bar is missing, (b) the lock bar itself never arrives and a later bar is observed, (c) bars arrive reordered such that a post-lock-boundary bar is seen before an earlier required bar. In all three cases the ORB is frozen as skipped with a gap reason, and downstream breakout / stacking / grading logic MUST treat it as unavailable for trading decisions. Arrival order before the lock boundary is not enforced; same-timestamp redeliveries overwrite with latest-wins semantics (matching `bar_fetcher`). This contract is implemented in `orb_levels.py::OrbBuilder` (Slice 2) and the reason string is picked up by Slice 8's `SkipEvent`.

### 2.3 The stacking decision tree (Doc2 §STEPS 1–3)

```
09:50 ET — ORB20 locks
  ├─ Did the 09:45–09:50 candle close outside ORB20 range?
  │   └─ NO → wait for next bar; continue monitoring until 12:00 ET
  │   └─ YES → ENTER HALF position (initial credit spread)
  │              Direction = direction of breakout
  │              Baseline edge: 68.8% day favourable
  │
10:00 ET — ORB30 locks
  ├─ Did ORB30 break in the SAME direction as ORB20?
  │   └─ YES (89% of cases) → ADD to NORMAL. Edge: 72.2% day favourable.
  │   └─ NO  (11% of cases) → REDUCE / EXIT WARNING. Edge collapses to 39.5%.
  │   └─ NO BREAKOUT yet → hold, reassess at 10:30
  │
10:30 ET — ORB60 locks (KEY DECISION POINT)
  ├─ Did ORB60 break in the SAME direction?
  │   └─ YES (all 3 same, 70% of days) → ADD to PLUS. Edge: 80.3% day favourable.
  │   └─ NO  (opposes, 26% of days)    → HARD EXIT. Edge: 35.0%. NOT a "tighten" signal.
  │   └─ NO BREAKOUT (4% of days)      → hold; edge 83.4% but tiny sample
  │
10:30 ET — Quality enhancers (only evaluated if all 3 same)
  ├─ ORB20 close aligned with breakout direction?  → +1 quality tier
  ├─ ORB30 close aligned?                          → +1 quality tier
  ├─ ORB60 close aligned?                          → +1 quality tier
  └─ All 3 closes aligned                          → DOUBLE position. Edge: 90.9%.
```

### 2.4 Position sizing ladder (Doc2)

| State | Score | Size | Approx frequency |
|---|---|---|---|
| ORB20 break only | 0 | HALF | start of every breakout day |
| + ORB30 confirms | +1 | NORMAL (100%) | 89% of breakout days |
| + ORB60 confirms (all 3 same) | +2 | PLUS (150%) | 70% of all days |
| + 1–3 close alignments | +3 to +5 | DOUBLE (200%) | 22–38% of days |
| ORB30 opposes | -1 | reduce / exit | 11% of days |
| ORB60 opposes | EXIT | flat | 26% of days |

For paper-trading and the initial automated build, "size" maps to **contract count multipliers**: HALF=1, NORMAL=2, PLUS=3, DOUBLE=4 (subject to risk-budget cap). To be confirmed in the roadmap.

### 2.5 Quality enhancers beyond stacking

- **Range expansion ratio (Doc1 §6):** When `OR60/OR20 ≥ 2.5x` on stacked days, day-favourable rises to 88.8%. Use as an additional **quality flag** at the 10:30 lock, not as a gate.
- **Breakout timing (Doc1 §9):** Immediate breakouts (close in 09:50–10:00 ET) win 65.9% vs 58.2% delayed. Score +1 if breakout fires on the lock bar.
- **ATR filter (Doc1 §7):** Sweet spot is `ORB20/ATR14 ∈ [15%, 20%]` (73.4% in recent data). HOWEVER on stacked days the relationship inverts — wide ORBs (50–100% ATR) hit 85.8%. **Apply the ATR filter to the BASE setup score, NOT to stacked-day decisions.**

### 2.6 Strike selection (Doc1 §5, Doc2 §STRIKE SELECTION GUIDE)

Probability that price closes past the reference level by EOD on stacked days:

| Short strike at | Bull OTM prob | Bear OTM prob |
|---|---|---|
| **ORB20 midpoint** | **82.7%** | **78.0%** |
| ORB20 high/low | 72.2% | 65.9% |
| ORB30 midpoint | 81.9% | 76.2% |
| ORB60 midpoint | 79.7% | 72.8% |
| ORB60 high/low | 61.4% | 52.7% |

**Default rule:** Short strike = nearest $5 strike to **ORB20 midpoint**, on the OPPOSITE side of the breakout. Long strike = short ± $5.

**A+ buffer rule (Doc1 §18):** When the ORB20 high/low sits $4–$5 from the nearest $5 strike, stacked-day "past ORB20" rises to 71.7% vs 67.2% at $0–$1 buffer. Score +1 in base grading.

**Premium validation:** If selected spread credit < $0.80 → skip or scan adjacent strikes. If > $1.50 → log + proceed cautiously.

### 2.7 Stops & exits

- **Bracketed credit spread management (legacy from blueprint):** OCO at 50% target / 100% stop on credit. Hands-off.
- **Stacking-driven hard exit:** ORB60 opposing the position → close everything immediately, regardless of P/L. This is an *additional* exit overlaid on the bracket.
- **EOD:** Cash-settled, OTM = expire worthless. ITM/borderline → close before 15:50 ET to avoid settlement risk. (DST-aware `EOD_CUTOFF_UK` constant is defined in Slice 14 of the roadmap, not here.)
- **Stop sizing reference (Doc1 §10):** On stacked trades the median winning trade only goes $2.90 against you; 86% of winners stay within $10. The bracket's 100% stop on a $1 credit (= $2 buyback = ~$1 underlying move) sits comfortably inside the historical adverse-excursion band.

### 2.8 Calendar overlays (Doc1 §13, Doc2)

Apply at the start of session — these adjust the base score by ±1 or ±2:

| Event | Adjustment | Note |
|---|---|---|
| FOMC Wednesday | +1 | 68.1% win rate |
| Quarter end | +1 | 68.4% (small sample) |
| Last Friday of month | +1 | 67.9% (bear bias 71.8%) |
| **Triple/Quad witching** | **-2** | 58.0% — size DOWN explicitly |
| OpEx Friday | -1 | 61.3% |

**Precedence when multiple events stack on the same day:** sum all applicable adjustments, then **clamp to the range [-2, +2]**. This prevents any single rare alignment (e.g. quarter-end + last-Friday + FOMC) from swamping the base score, and matches the magnitude of the strongest single negative event (Triple Witching at -2).

### 2.9 Base setup grading (independent of stacking — Doc1 §20, Doc2)

This is a separate quality score evaluated at the ORB20 lock, additive to the stacking ladder:

| Factor | Condition | Points |
|---|---|---|
| ORB/ATR | <20% | +2 |
| ORB/ATR | 20–30% | +1 |
| ORB/ATR | 30–40% | 0 |
| ORB/ATR | >40% | -1 |
| Breakout timing | Immediate (lock-bar close beyond level) | +1 |
| ORB close aligned | ≥80% / ≤20% in breakout direction | +1 |
| Day of week | Thursday or Friday | +1 |
| Day of week | Monday | -1 |
| Buffer | ≥$4 to nearest $5 strike | +1 |
| Buffer | <$1 | -1 |

| Tier | Score | 1x Win | 0.5x Win |
|---|---|---|---|
| HALF | ≤ -1 | 59.0% | 74.6% |
| NORMAL | 0–1 | 61.1% | 75.9% |
| PLUS | 2–3 | 66.4% | 82.6% |
| DOUBLE | ≥ 4 | 67.6% | 83.4% |

**Combined sizing:** A DOUBLE-grade base setup that ALSO clears full stacking + close alignment is the maximum-conviction trade. The two scores are independent and additive — the roadmap will define how they combine into a single contract count.

---

## 3. Dead Ends — Do NOT Build (Doc4)

The following have been tested across 5,000+ trades and 21 years. They are dead and must not appear in the new build:

- **MACD-V in any form** — direction filter, histogram alignment, traffic light, standalone signals (OB/OS/EM/extremes), fade combos, overnight holds, zero-line crosses, composite scores. All dead. *(The histogram ±40 management warning is the only marginal exception, and it's a trade-management nice-to-have, not an entry rule.)*
- **Gap analysis** — gap size, gap direction, gap × BO direction. ≤3% variation across all bins.
- **Previous day direction as predictor** — 51% continuation. Coin flip.
- **Consecutive day streaks** — no edge.
- **Crable narrow-range theory (intraday)** — small ORBs do NOT predict big days.
- **Tuesday day-of-week effect** — 13.6% spread across periods, unstable.
- **Penetration mode breakouts** (wick-only) — 54.7% vs 62.8% Confirmation.
- **2x range targets** — diminishing returns, 52.2%.
- **Iron condor on no-breakout days** — too rare (≤8/year on ORB60).
- **Late-session breakouts** (after 12:00 ET) — 26 occurrences in 21 years.
- **Overnight holds on MACD-V signals.**
- **Fade-the-extreme combos** — every variant has negative EV.
- **30-min MACD-V Traffic Light overlay on 5-min ORB** — doesn't translate.
- **BB(30) tag + pulse bar + V-pattern entry framework (the original Tag N Turn methodology)** — not in Doc4 because it was never tested in this research, but it sits on top of MACD-V Traffic Light scoring which IS dead. Shelved by decision, not by data.

---

## 4. Current `tag_n_turn/` Build Inventory

### 4.1 Files and their fate under the pivot

| File | Lines (~) | Purpose | Fate |
|---|---|---|---|
| `__init__.py` | small | package marker | **Keep** (rename when package renames) |
| `bar_fetcher.py` | medium | DXLink 30m SPX bar fetcher with history warmup + live closed-bar streaming | **Adapt** — switch to **5m** interval and re-validate candle depth via DXLink. The fetcher pattern is reusable; the interval constant changes. `tests/test_bar_fetcher.py` ports cleanly to 5m alongside it (also **Adapt**, not Shelve). |
| `indicators.py` | medium | ATR(14), BollingerBands(30,2), MACDV(12,26,14) | **Partial keep** — ATR(14) is still needed for the ATR filter. **Drop** BollingerBands and MACDV (both unused under the new strategy). |
| `signals.py` | medium | `is_bb_tag`, `bb_penetration_atr`, `detect_v_pattern`, `is_pulse_bar`, `pulse_bar_range` | **Shelve** — entire file. None of these signals are used by ORB Stacking. |
| `scoring.py` | medium | 5-factor composite (V-pattern, MACDV light, pulse strength, time-of-day, BB depth) | **Shelve** — replace with new ORB-stacking scorer + base setup grader. The factor-decomposition pattern (return `{score, tier, sizing_mult, factors_breakdown}`) is reusable. |
| `stops.py` | small | PFZ stop + ATR fallback | **Shelve** — ORB Stacking uses bracket OCO + ORB60-opposes hard exit. New stops module needed. |
| `trade_intent.py` | small | `TradeIntent` / `SkippedSetup` dataclasses | **Adapt** — the dataclass shape stays useful; field set needs revision (drop BB/MACD/V-pattern fields, add ORB20/30/60 levels, stacking state, close alignments). |
| `entry_engine.py` | medium | State machine: BB tag → 15-bar window → pulse bar → score → emit | **Replace entirely** — new state machine driven by ORB lock times and stacking confirmation. Pattern (closed-bar stream → state machine → emit intents) is reusable. |
| `tests/test_*.py` | 154 tests | Unit tests for the above | **Shelve with their modules.** Keep the test infrastructure (`unittest`, `_bar()` helper style, synthetic-bar fixtures, `python -m unittest discover` setup). |

### 4.2 What survives the pivot intact

- The **package isolation discipline** — `tag_n_turn/` does not import from the live bot, and the live bot does not import from `tag_n_turn/`. This is a load-bearing constraint and must be preserved through the pivot.
- The **bar fetcher → indicator → state machine → trade intent → consumer** layering. Architecture is sound; only the contents of each layer change.
- **ATR(14)** indicator class — reused as-is.
- **`unittest` discipline** — every signal/state-machine module has unit tests with synthetic bars. Continue this.
- **UK timezone for scheduling** — the live bot is UK-time; ORB times must be expressed as UK clock equivalents. **During BST (US and UK both on summer time), the lock times are 14:50 / 15:00 / 15:30 UK; entry window cutoff is 17:00 UK.** Outside BST: subtract 1 hour from each. Cross-reference DST checklist in `feedback_dst_time_changes.md`.
- **The non-import-into-main rule** — Phase 6 (live integration) is the ONLY phase that may touch live-bot files. Until then everything stays inside the package and is exercised via demo scripts only.

### 4.3 Package rename decision

Two options for the roadmap to choose:

1. **Keep `tag_n_turn/` as the directory name** — the contents change but the path doesn't, minimising churn in any external references (memory files, demo scripts, test commands).
2. **Rename to `orb_stacking/`** — semantically honest, makes git history of the pivot explicit, but requires updating `MEMORY.md`, `tag_n_turn_demo.py`, test discovery commands, and CLAUDE.md references.

**Recommendation:** Defer to the Opus roadmap. Both are defensible.

---

## 5. Open Questions for the Roadmap

These are deliberately left undecided in this SoT — they need design judgment, not just compilation of facts.

1. **Single sizing scalar.** Doc2 has stacking sizing (HALF/NORMAL/PLUS/DOUBLE) AND base grading sizing (HALF/NORMAL/PLUS/DOUBLE). They're additive but Doc2 doesn't specify the formula. The roadmap must define how to combine them into one contract count.
2. **Bar source.** Live bot gets SPX from tastytrade SDK; the existing bar fetcher uses DXLink 30m candles. New build needs DXLink 5m candles — does the same `subscribe_candle` API support `"5m"` reliably? *(Note: project memory says yes — `subscribe_candle(symbols, interval, start_time)` with interval as a string like `"5m"`.)* Needs a quick candle-depth probe analogous to the original `test_candle_depth.py`.
3. **Live Premium Popper integration.** The existing `premium_popper.py` is the live ORB strategy currently running (-$105 over 4 trades). The pivot's natural endgame is to replace its entry logic with the full stacking ladder. The roadmap must decide: (a) build ORB Stacking inside `tag_n_turn/` and migrate `premium_popper.py` over in Phase 6, or (b) refactor `premium_popper.py` directly. Option (a) preserves the "don't break the live bot" constraint.
4. **Historic backtesting.** The 21yr 5-min data files (~71MB) are sitting in `/docs/`. Do we want a one-shot backtester pass against them as part of the build to validate the implementation reproduces the headline numbers (80.3% all-3-same, 90.9% all-aligned) before going live? Strong recommendation: yes, as a build-quality gate.
5. **A+ buffer rule precision.** Doc2 says "≥$4 to nearest $5 strike". For SPX at e.g. 5928.40 (ORB20 high), nearest $5 = 5925, buffer = $3.40 — does that count as A+? Need a precise comparator.
6. **Entry slippage realism.** ORB20 lock is at 09:50:00 ET. The 09:45–09:50 candle "closes" at 09:50:00 but the bar event arrives some milliseconds later. Need to define the entry order timestamp tolerance.
7. **Time zone normalization in tests.** All historic data is in UTC per Doc1. All live-bot scheduling is UK time. Test fixtures should use UTC and the engine should accept UTC + emit UK-time decisions to match the rest of the bot.

---

## 6. How This Document Is Used

- **Build phases (Haiku):** every coding task references this doc for spec. If the task asks for behaviour not described here, escalate to the roadmap, not to invention.
- **Reviews (Sonnet):** every diff is checked against this doc. Deviations require either a roadmap update or a code fix — never silent drift.
- **Final review (Opus):** final pass validates that the completed unit matches the spec here AND the Opus roadmap's slice of it.
- **Updates to this doc:** any change must include a one-line entry at the top reconciling what changed and why. This doc is the single source of truth — it cannot drift.
