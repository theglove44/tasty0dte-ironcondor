# ORB BREAKOUT RESEARCH — COMPLETE FINDINGS BRIEFING
## AntiVestor Premium Popper R&D
**Dataset:** 409,644 five-minute bars | 5,270 trading days | 21 years (Jan 2005 – Apr 2026)  
**Instrument:** SPX (S&P 500 Index)  
**Base Model:** ORB20, Confirmation mode (close outside range), Options Emulator stop ($5 whole numbers)

---

## TABLE OF CONTENTS

1. Executive Summary
2. Dataset & Methodology
3. 21-Year Baseline
4. The Stacking Discovery (Core Finding)
5. Close Position Reference Points (Strike Selection)
6. Range Expansion Ratio
7. ATR Filter (Corrected with 21yr data)
8. ORB Close Position as Quality Signal
9. Breakout Timing
10. Max Adverse/Favorable Excursion
11. Time-to-Peak Analysis
12. Failure Analysis
13. Calendar Effects
14. Day of Week
15. Previous Day & Consecutive Days
16. Gap Analysis
17. Opening Range as Day Predictor
18. Credit Spread Implications
19. BWB Structure Implications
20. Composite Grading System
21. What Didn't Work (Dead Ends)

---

## 1. EXECUTIVE SUMMARY

Twenty-one years of SPX 5-minute data reveals one dominant edge: **ORB stacking.** When the 20-minute, 30-minute, and 60-minute opening ranges all break in the same direction, the day closes favorably 80.3% of the time. When all three ranges additionally closed their formation period aligned with the breakout direction (close near the high for bulls, close near the low for bears), the favorable close rate rises to 90.9% — stable across every 5-year block from 2005 to 2026.

This stacking framework provides a progressive, real-time trading model: enter small at the ORB20 breakout (9:50 AM), add when ORB30 confirms (10:00 AM), add again when ORB60 confirms (10:30 AM). Each confirmation step increases both the probability of success and the position size. If any step opposes (particularly ORB60), exit the trade — the opposition signal is equally powerful in reverse, with only 35% favorable outcomes.

Secondary findings include: the ORB60/ORB20 range expansion ratio as a new quality filter (ratio ≥ 2.5x produces 88.8% favorable days), the ATR filter inversion (small ORBs relative to ATR win more often, not less — correcting the 6-year analysis), and comprehensive close-position data enabling optimal strike placement for credit spreads and broken wing butterflies.

MACD-V was tested extensively as both a filter and standalone signal. It adds no meaningful edge to the ORB system on 5-minute bars. Dropped from further development.

---

## 2. DATASET & METHODOLOGY

**Data:** Four files of SPX 5-minute OHLC bars covering 2005-2026, deduplicated and stitched chronologically. Total: 409,644 unique bars across 5,270 trading sessions.

**Time convention:** All data is in UTC. 14:30 UTC = 9:30 AM ET (market open). ORB20 locks at 14:50 UTC (9:50 AM ET). ORB60 locks at 15:30 UTC (10:30 AM ET). Session end at 21:00 UTC (4:00 PM ET).

**ORB computation:** Calculated from raw OHLC, not from pre-embedded breakout flags. ORB high = highest high during formation period. ORB low = lowest low. Breakout = close outside the range (Confirmation mode).

**Win/loss model:** Options Emulator stop = nearest $5 whole number beyond the opposite ORB level. Target = ORB range × multiplier. "Win" = target hit before stop, or no stop triggered by end of day. Full day window (9:50 AM to 4:00 PM ET).

**Period segmentation:** All findings validated across four 5-year blocks: 2005-2009 (includes 2008 crisis), 2010-2014 (recovery/low vol), 2015-2019 (steady growth), 2020-2026 (pandemic/high vol). A finding must hold in at least 3 of 4 periods to be considered robust.

**ATR:** 14-period average true range computed from daily ranges of the 14 preceding sessions.

---

## 3. 21-YEAR BASELINE

### 1st Breakout — ORB20, 1.0x Target

| Period | Total | Win % | Bull | Bull Win % | Bear | Bear Win % |
|--------|-------|-------|------|-----------|------|-----------|
| 2005-2009 | 1,170 | 66.0% | 577 | 67.1% | 593 | 64.9% |
| 2010-2014 | 1,234 | 63.9% | 664 | 64.3% | 570 | 63.5% |
| 2015-2019 | 1,253 | 62.8% | 640 | 62.7% | 613 | 63.0% |
| 2020-2026 | 1,565 | 62.8% | 822 | 63.7% | 743 | 61.8% |
| **ALL** | **5,222** | **63.8%** | **2,703** | **64.3%** | **2,519** | **63.2%** |

### 1st Breakout — ORB20, 0.5x Target

| Period | Win % | Bull Win % | Bear Win % |
|--------|-------|-----------|-----------|
| 2005-2009 | 81.3% | 81.6% | 80.9% |
| 2010-2014 | 77.8% | 77.1% | 78.6% |
| 2015-2019 | 78.9% | 78.3% | 79.4% |
| 2020-2026 | 79.4% | 79.2% | 79.7% |
| **ALL** | **79.3%** | **79.0%** | **79.7%** |

### 2nd Breakout

Total setups: 2,793 | Win rate (1x target): 65.5%

**Key observation:** Bull and bear win rates are nearly identical (64.3% vs 63.2% on 1x). There is no structural directional bias in ORB breakouts on the 5-minute timeframe. Both directions work equally well for the base setup.

---

## 4. THE STACKING DISCOVERY (CORE FINDING)

### 4.1 The Full Permutation Table

When ORB20 breaks in a direction, ORB30 and ORB60 can each confirm (same direction), oppose (opposite direction), or produce no breakout. All 7 occurring permutations:

| ORB30 | ORB60 | Days | % of Total | Day Favorable | Past ORB20 | 1x BO Win |
|-------|-------|------|-----------|---------------|-----------|-----------|
| **SAME** | **SAME** | **3,632** | **69.5%** | **80.3%** | **69.3%** | **79.7%** |
| SAME | OPP | 844 | 16.2% | 35.0% | 22.2% | 30.9% |
| SAME | NONE | 163 | 3.1% | 83.4% | 44.2% | 55.8% |
| OPP | SAME | 57 | 1.1% | 64.9% | 59.6% | 38.6% |
| OPP | OPP | 489 | 9.4% | 36.8% | 17.2% | 11.0% |
| OPP | NONE | 9 | 0.2% | — | — | — |
| NONE | NONE | 29 | 0.6% | 96.6% | 27.6% | 27.6% |

**Interpretation:**

"Day Favorable" = the day closed in the direction of the ORB20 breakout (above open for bulls, below open for bears).

"Past ORB20" = the day closed at or beyond the ORB20 high (for bulls) or at or below the ORB20 low (for bears). This is the more demanding test — price must stay past the breakout level, not just be above/below the open.

"1x BO Win" = the standard ORB20 breakout trade with 1x range target hit before Options Emulator stop.

### 4.2 The Key Insight

The spread between all-same and both-opposed is 43.5 percentage points on day direction (80.3% vs 36.8%). This is the single most powerful predictor in 21 years of data. Nothing else comes close.

### 4.3 The Opposition Signal

When ORB60 breaks OPPOSITE to ORB20 (regardless of ORB30), the trade collapses:

| Scenario | Days | Day Favorable | Past ORB20 | 1x Win |
|----------|------|--------------|-----------|--------|
| 30 agrees, 60 OPPOSES | 844 | **35.0%** | **22.2%** | **30.9%** |
| Both 30+60 oppose | 489 | **36.8%** | **17.2%** | **11.0%** |

ORB60 opposing = **hard exit signal**. Not "tighten up." Close the position.

### 4.4 Bull vs Bear — All 3 Same

| Direction | Days | Day Favorable | Past ORB20 | Near ORB20 | 1x Win |
|-----------|------|--------------|-----------|-----------|--------|
| Bull | 1,957 | 82.5% | 72.2% | 82.7% | 79.8% |
| Bear | 1,675 | 77.7% | 65.9% | 78.0% | 79.6% |

Bull has a 5% edge on day direction and "past ORB20" metrics. Both directions have identical 1x win rates (~80%).

### 4.5 Stacking + Close Alignment (Progressive Quality)

Each ORB can additionally have its close position aligned (close near high for bull days, close near low for bear days). Adding this filter progressively:

| Level | Days | Freq/Year | Day Fav | Past ORB20 | Near ORB20 |
|-------|------|-----------|---------|-----------|-----------|
| All 3 same (no alignment) | 3,632 | 173 | 80.3% | 69.3% | 80.5% |
| + ORB20 close aligned | 2,013 | 96 | 87.5% | 72.9% | 84.5% |
| + ORB20+30 aligned | 1,547 | 74 | 89.7% | 75.6% | 87.0% |
| + ORB20+60 aligned | 1,448 | 69 | 88.5% | 74.8% | 85.5% |
| + ALL 3 close aligned | 1,161 | 55 | **90.9%** | **77.0%** | **87.9%** |

At peak quality (all 3 same + all 3 close aligned): **90.9% day favorable, 77.0% close past ORB20 level.** 55 setups per year — roughly one per week.

Bull at peak: 91.4% favorable, 78.1% past ORB20. Bear at peak: 90.1% favorable, 75.5% past ORB20.

### 4.6 Period Validation

| Period | All 3 Same | All 3 Same + All Aligned |
|--------|-----------|------------------------|
| 2005-2009 | 79.9% | 90.5% |
| 2010-2014 | 82.2% | **93.7%** |
| 2015-2019 | 78.1% | 91.1% |
| 2020-2026 | 80.9% | 88.3% |

Stable across every era. Not curve-fitted.

### 4.7 The Progressive Add-In Model

This is the real-time trading framework:

| Event | Time (ET) | Days | Day Favorable | Past ORB20 | Action |
|-------|-----------|------|--------------|-----------|--------|
| ORB20 breaks | 9:50 AM | 5,223 | 68.8% | 55.6% | Enter initial position |
| ORB30 confirms | 10:00 AM | 4,639 (89%) | 72.2% | 59.8% | Add position |
| ORB60 confirms | 10:30 AM | 3,632 (70%) | 80.3% | 69.3% | Add again |
| ORB30 OPPOSES | 10:00 AM | 555 (11%) | 39.5% | 21.4% | WARNING — tighten/reduce |
| 30 conf, 60 OPPOSES | 10:30 AM | 844 (16%) | 35.0% | 22.2% | EXIT position |

89% of the time, ORB30 confirms ORB20. When it does, the edge improves. When ORB60 also confirms (70% of all days), you're in the highest probability zone. When ORB60 opposes, get out.

---

## 5. CLOSE POSITION REFERENCE POINTS (STRIKE SELECTION)

This table shows the probability that price closes at or past each reference level at end of day. Use for short strike selection on credit spreads and BWB structures.

### All ORB20 Breakout Trades (5,223 days)

| Reference Point | All | Bull | Bear |
|----------------|-----|------|------|
| Favorable vs day open | 68.8% | 72.2% | 65.2% |
| Past ORB20 midpoint | 67.6% | 71.3% | 63.6% |
| Past ORB20 high/low | 55.6% | 59.4% | 51.5% |
| Past ORB30 midpoint | 65.6% | 69.7% | 61.2% |
| Past ORB30 high/low | 51.5% | 55.9% | 46.7% |
| Past ORB60 midpoint | 62.5% | 67.3% | 57.5% |
| Past ORB60 high/low | 43.7% | 48.4% | 38.7% |

### All 3 Same Direction (3,632 days)

| Reference Point | All | Bull | Bear |
|----------------|-----|------|------|
| Favorable vs day open | 80.3% | 82.5% | 77.7% |
| Past ORB20 midpoint | 80.5% | 82.7% | 78.0% |
| Past ORB20 high/low | 69.3% | 72.2% | 65.9% |
| Past ORB30 midpoint | 79.3% | 81.9% | 76.2% |
| Past ORB30 high/low | 65.7% | 69.2% | 61.6% |
| Past ORB60 midpoint | 76.5% | 79.7% | 72.8% |
| Past ORB60 high/low | 57.4% | 61.4% | 52.7% |

**Strike selection implications:**

A short strike at the ORB20 midpoint gives 82.7% OTM probability (bull stacked). At the ORB20 high/low level, it drops to 72.2%. At ORB60 high/low, only 61.4%.

For credit spreads: placing the short strike at the ORB midpoint captures the highest probability. Each step further out toward the ORB level reduces probability but increases credit.

---

## 6. RANGE EXPANSION RATIO (NEW DISCOVERY)

The ratio of ORB60 range to ORB20 range measures how much the market expanded between the 20-minute and 60-minute formation periods. Higher ratios indicate stronger directional momentum developing.

| OR60/OR20 Ratio | Days | Day Favorable | Past ORB20 |
|----------------|------|--------------|-----------|
| 1.0-1.3x (tight) | 1,494 | 75.2% | 60.0% |
| 1.3-1.6x | 804 | 82.0% | 71.3% |
| 1.6-2.0x | 650 | 82.8% | 75.5% |
| 2.0-2.5x | 369 | 85.6% | 78.9% |
| **2.5-5.0x** | **304** | **88.8%** | **83.6%** |

*Data filtered to all-3-same days only.*

When the 60-min range is 2.5x or more the 20-min range, the day is a trending day with 88.8% favorable probability. This ratio is computable at the 60-minute lock (10:30 AM) and provides an additional quality signal on top of the stacking confirmation.

---

## 7. ATR FILTER (CORRECTED WITH 21-YEAR DATA)

**Critical correction:** The earlier 6-year analysis (2020-2025) showed larger ORBs relative to ATR performing better. With 21 years of data, the relationship reverses.

| ORB/ATR % | N | 1x Win % | 0.5x Win % |
|-----------|---|----------|-----------|
| 0-10% | 23 | 78.3% | 87.0% |
| **10-15%** | **276** | **66.3%** | **85.5%** |
| **15-20%** | **624** | **67.9%** | **85.1%** |
| 20-25% | 853 | 65.1% | 82.4% |
| 25-30% | 763 | 64.5% | 80.1% |
| 30-40% | 1,132 | 61.7% | 77.0% |
| 40-50% | 628 | 59.9% | 75.2% |
| 50-75% | 635 | 62.4% | 77.2% |
| 75-100% | 168 | 68.5% | 76.8% |

**Explanation:** Small ranges relative to ATR mean the day's expected move hasn't been consumed yet. The breakout has room to run. Wide ORBs have already used up much of the day's potential.

**Post-2022 validation (2023-2026 only):**

| ORB/ATR % | N | 1x Win % | 0.5x Win % |
|-----------|---|----------|-----------|
| 0-15% | 72 | 56.9% | 77.8% |
| **15-20%** | **124** | **73.4%** | **88.7%** |
| 20-25% | 167 | 65.9% | 83.8% |
| 25-30% | 137 | 64.2% | 80.3% |
| 30-40% | 158 | 65.8% | 78.5% |
| 40-50% | 87 | 54.0% | 72.4% |
| 50-100% | 67 | 53.7% | 70.1% |

The 15-20% ATR bucket dominates in recent data at 73.4%/88.7%. Confirmed as the sweet spot.

**However, on stacked days the relationship inverts again:**

| ORB/ATR % | All 3 Same — Day Favorable | All 3 Same — Past ORB20 |
|-----------|--------------------------|------------------------|
| 0-20% | 78.2% | 72.8% |
| 20-30% | 77.3% | 67.5% |
| 30-50% | 80.4% | 67.9% |
| **50-100%** | **85.8%** | **71.8%** |

On trending days (all 3 same), wide ORBs actually perform BEST at 85.8%. The wider range confirms strong momentum. The ATR filter is useful for the base setup but may be counterproductive when combined with stacking.

---

## 8. ORB CLOSE POSITION AS QUALITY SIGNAL

Where price closes within the ORB range at lock time predicts both breakout direction and quality.

| ORB Close Position | 1x Win % | Bull Rate | Bull Win | Bear Win |
|-------------------|----------|-----------|----------|----------|
| Near low (0-20%) | 65.4% | 20% | 62.7% | 66.1% |
| Low-mid (20-40%) | 62.0% | 36% | 62.5% | 61.8% |
| **Middle (40-60%)** | **59.5%** | 50% | 63.0% | **56.0%** |
| Mid-high (60-80%) | 62.3% | 63% | 62.2% | 62.6% |
| Near high (80-100%) | **66.1%** | 81% | **66.5%** | 64.4% |

**Key insight:** Close near the extreme (top or bottom 20%) indicates conviction. Close in the middle indicates indecision and produces the worst win rates. Bear breakouts from middle-close ORBs are only 56.0% — barely profitable.

**Aligned vs Opposed (21 years, all periods stable):**

| Alignment | 1x Win % | 0.5x Win % |
|-----------|----------|-----------|
| Aligned (close near high + bull BO, or near low + bear BO) | 65.8% | 80.1% |
| Opposed | 62.9% | 78.7% |
| Neutral (middle close) | 60.3% | 78.2% |

---

## 9. BREAKOUT TIMING

| Time ET | N | 1x Win % | 0.5x Win % |
|---------|---|----------|-----------|
| **9:50-10:00 (immediate)** | **2,393** | **65.9%** | **82.0%** |
| 10:00-10:30 | 1,920 | 63.1% | 78.7% |
| 10:30-11:00 | 474 | 58.2% | 74.9% |
| 11:00-12:00 | 246 | 58.1% | 71.1% |
| After 12:00 | 187 | 63.5% | 72.5% |

46% of all breakouts fire immediately (first 10 minutes after lock). These are the highest quality at 65.9%. Delayed breakouts degrade progressively.

---

## 10. MAX ADVERSE / FAVORABLE EXCURSION

### All 3 Same Direction

| Metric | Winners (2,895) | Losers (737) |
|--------|----------------|-------------|
| Median MAE (max against you) | **$2.90** | $10.80 |
| Median MFE (max for you) | $13.10 | $4.10 |

### What % of winners dip by how much?

| MAE Threshold | % of Winners Within |
|--------------|-------------------|
| ≤ $3 | 51.3% |
| ≤ $5 | 67.8% |
| ≤ $8 | 80.2% |
| ≤ $10 | 85.5% |
| ≤ $15 | 92.2% |

**Implications:** On stacked trades, the median winning trade only goes $2.90 against you. Two-thirds never go more than $5 against you. Your options stop has substantial breathing room.

**Non-stacked trades for comparison:** Winner MAE is $7.30 (2.5x worse). Only 14% stay within $3. The stacking confirmation dramatically reduces adverse excursion on winning trades.

### Optimal Stop Distance (stacked trades)

| Stop $ | Winners Kept | Losses Cut | Estimated Win % |
|--------|-------------|-----------|----------------|
| $5 | 1,964/2,895 (68%) | 581/737 (79%) | 72.7% |
| $10 | 2,476/2,895 (86%) | 386/737 (52%) | 77.1% |
| $15 | 2,670/2,895 (92%) | 254/737 (34%) | 78.4% |
| $20 | 2,765/2,895 (96%) | 159/737 (22%) | 79.0% |

A $10 stop on stacked trades captures 86% of winners while cutting 52% of losers. The current Options Emulator stop (opposite ORB ± $5) is generally appropriate.

---

## 11. TIME-TO-PEAK ANALYSIS

### Stacked Trades (All 3 Same, Winners Only)

| Timeframe | Peak Reached |
|-----------|-------------|
| 15 min | 0.8% |
| 30 min | 3.0% |
| 60 min | 10.1% |
| 90 min | 17.4% |
| 120 min | 23.4% |
| 180 min (3 hr) | 33.8% |
| **Median** | **260 min (4.3 hr)** |

**The move develops throughout the day.** Only 10% peak within the first hour. The median peak is 4.3 hours after the ORB20 breakout — meaning the maximum favorable excursion typically occurs in the last hour of trading.

This is ideal for premium sellers: time decay works continuously while the directional move slowly builds. There is no "quick spike then reversal" pattern on stacked days.

### Non-Stacked Trades (Winners Only)

| Timeframe | Peak Reached |
|-----------|-------------|
| 15 min | 30.2% |
| 30 min | **55.8%** |
| **Median** | **30 min** |

Non-stacked winners peak quickly — over half within 30 minutes. These are scalps, not trend days. Very different character.

---

## 12. FAILURE ANALYSIS

### What kills the 20% of stacked trades that fail?

| Factor | Winners (median) | Losers (median) |
|--------|-----------------|----------------|
| ORB/ATR % | 33.1% | 30.1% |
| ORB range ($) | $7.80 | $7.30 |
| Buffer ($) | $2.50 | $2.30 |
| OR60/OR20 ratio | 1.4x | 1.3x |
| **MAE** | **$2.90** | **$12.40** |

The factors that distinguish winners from losers are very similar on entry. The main difference is MAE — losers go $12.40 against you (vs $2.90 for winners). They fail hard and fast.

**Practical implication:** You cannot reliably predict which stacked trades will fail at entry. The best defense is position sizing and stop management, not additional filters. The stacking itself IS the filter.

---

## 13. CALENDAR EFFECTS

| Event | N | Win Rate | vs Baseline (63.8%) | Actionable? |
|-------|---|----------|-------------------|------------|
| **FOMC Wednesday** | 389 | **68.1%** | **+4.3%** | Size UP |
| **Quarter end** | 79 | **68.4%** | +4.6% | Size UP (small sample) |
| **Last Friday of month** | 240 | **67.9%** | +4.1% | Size UP |
| Last trading day of month | 244 | 66.4% | +2.6% | Marginal |
| NFP Friday | 233 | 63.1% | -0.7% | No effect |
| OpEx Friday | 243 | 61.3% | -2.5% | Slight negative |
| **Triple/Quad Witching** | **81** | **58.0%** | **-5.8%** | **Size DOWN** |

**FOMC Wednesdays:** Both bull (68.0%) and bear (68.3%) benefit equally. The volatility around FOMC creates cleaner breakouts.

**Triple witching:** Bull breakouts drop to 50.0%. The chaotic liquidity and option pinning risk damages ORB breakout quality.

**Last Friday of month:** Bears win at 71.8% vs bulls at 64.2%. Month-end rebalancing creates bearish positioning pressure.

---

## 14. DAY OF WEEK

| Day | 1x Win % | 0.5x Win % | Period Spread |
|-----|----------|-----------|---------------|
| Monday | 62.0% | 78.2% | 6.9% |
| Tuesday | 63.1% | 79.2% | **13.6% (unstable)** |
| Wednesday | 64.0% | 78.9% | 5.7% |
| **Thursday** | **64.5%** | **81.9%** | **2.6% (most stable)** |
| **Friday** | **65.2%** | **78.3%** | 4.8% |

Thursday is the most stable day across all periods (spread of only 2.6%). Friday has the highest raw win rate. Tuesday is wildly inconsistent (spread of 13.6%) — not reliable enough to include in scoring.

---

## 15. PREVIOUS DAY & CONSECUTIVE DAYS

| Factor | Win Rate | Notes |
|--------|----------|-------|
| Previous day UP | 64.6% | Slight edge |
| Previous day DOWN | 62.8% | Below baseline |
| Narrow prev day (<50% ATR) | **66.6%** | Compression → expansion |
| After 2 consecutive UP | **66.6%** | Best consecutive pattern |
| After 4+ consecutive (either) | 59-61% | Degraded |

Previous day direction does NOT predict next day's breakout direction (51% continuation — coin flip). Consecutive days don't predict direction either.

Narrow previous day is a genuine edge at 66.6% — compressed energy leads to expansion, consistent with Crable's narrow range theory at the daily level.

---

## 16. GAP ANALYSIS

| Gap Size | Win Rate | Bull Rate |
|---------|----------|-----------|
| Big gap down (<-$30) | 64.4% | 42% |
| Small gap down | 64.1% | 52% |
| Flat (-$5 to +$5) | 63.5% | 51% |
| Small gap up | 65.1% | 54% |
| Big gap up (>+$30) | 63.5% | 58% |

**Gaps have minimal impact on ORB breakout quality.** Small-to-medium gap ups are marginally better. Gaps do not reliably predict breakout direction. Not worth building into the system.

---

## 17. OPENING RANGE AS DAY DIRECTION PREDICTOR

| OR Duration | Bull BO → Close > Open | Bear BO → Close < Open |
|------------|----------------------|----------------------|
| ORB20 | **72.2%** | 65.2% |
| ORB30 | **74.0%** | 67.5% |
| ORB60 | **78.2%** | **73.3%** |

ORB60 bull breakout predicts a bullish day close 78.2% of the time. This is one of the strongest single-factor predictors in SPX day trading.

**With ORB close alignment:** ORB20 closed near high + bull BO → day closes bullish: 78.4%. ORB20 closed near low + bear BO → day closes bearish: 73.0%.

---

## 18. CREDIT SPREAD IMPLICATIONS

$5 wide spread, $2.40 credit, short strike at nearest $5 inside ORB20 level.

| Stacking Level | Win Rate | Setups/Year | Annual PnL |
|----------------|----------|-------------|-----------|
| Baseline (ORB20 only) | 64.6% | ~249 | $156 |
| 20+30 same | 68.4% | ~221 | $181 |
| **20+60 same** | **76.5%** | **~176** | **$215** |
| All 3 same | 76.7% | ~173 | $213 |
| All 3 same + ORB20 aligned | 79.7% | ~96 | $133 |
| All 3 same + ALL aligned | **83.3%** | ~55 | $86 |

**Buffer × Stacking interaction (Past ORB20 rate — for credit spread):**

| Buffer | All Trades | All 3 Same |
|--------|-----------|-----------|
| $0-1 | 53.4% | 67.2% |
| $1-2 | 55.8% | 68.8% |
| $2-3 | 56.5% | 70.9% |
| $3-4 | 54.5% | 68.0% |
| **$4-5** | **57.8%** | **71.7%** |

---

## 19. BWB STRUCTURE IMPLICATIONS

For a broken wing butterfly with the short strike at the day's open:

On stacked days (all 3 same): 80.3% of the time the day closes favorable (you collect the credit). The remaining 19.7% that reverse through the range hit the BWB body — potential max profit zone. The structure profits in both scenarios.

On the 77% of stacked days where price closes past the ORB20 level, the BWB expires with credit collected. On the 23% that come back inside the range, the BWB captures the reversal for potentially larger profit.

Key metric for BWB sizing: median MAE on winning stacked trades is only $2.90. The long wing should be placed wide enough to survive the typical adverse excursion of losing trades ($10.80 median).

---

## 20. COMPOSITE GRADING SYSTEM

### Scoring Factors

| Factor | Condition | Points |
|--------|-----------|--------|
| ORB/ATR ratio | <20% | +2 |
| ORB/ATR ratio | 20-30% | +1 |
| ORB/ATR ratio | >40% | -1 |
| Breakout timing | Immediate (<10 AM) | +1 |
| ORB close aligned | Close near high for bull, near low for bear | +1 |
| Day of week | Thursday or Friday | +1 |
| Day of week | Monday | -1 |
| Buffer (A+ setup) | ≥$4 to nearest $5 strike | +1 |
| Buffer | <$1 | -1 |

### Tier Results

| Tier | Score | N | Frequency | 1x Win % | 0.5x Win % |
|------|-------|---|-----------|----------|-----------|
| HALF | ≤ -1 | 524 | 10.0% | 59.0% | 74.6% |
| NORMAL | 0-1 | 1,992 | 38.1% | 61.1% | 75.9% |
| PLUS | 2-3 | 2,061 | 39.5% | **66.4%** | **82.6%** |
| DOUBLE | ≥ 4 | 645 | 12.4% | **67.6%** | **83.4%** |

**Note:** This grading system applies to the base ORB20 trade independently. The stacking framework operates as a separate, additive layer. A DOUBLE-grade ORB20 that also gets full stacking confirmation is the highest conviction setup available.

---

## 21. WHAT DIDN'T WORK (DEAD ENDS)

| Factor | Finding | Status |
|--------|---------|--------|
| MACD-V direction filter | 2.5% edge, inconsistent across periods | DROPPED |
| MACD-V extreme warning | 4-8% degradation at extremes, ORB structure handles it | DROPPED |
| MACD-V histogram | No edge at any level for entries | DROPPED (keep as management warning) |
| MACD-V standalone signals | Best was 57% — coin flip | DROPPED |
| MACD-V overnight holds | Explained by structural bullish drift | DROPPED |
| Gap analysis | ±2% variation, not actionable | NOT IMPLEMENTED |
| Previous day direction as predictor | 51% continuation — coin flip | NOT IMPLEMENTED |
| Consecutive day streaks | No direction prediction | NOT IMPLEMENTED |
| Crable narrow range (intraday) | Small ORBs don't predict big days | NOT IMPLEMENTED |
| Fade-the-extreme combos | All negative EV | DROPPED |

---

**END OF FULL BRIEFING**

*Analysis conducted across 409,644 five-minute bars spanning 21 years and 5,270 trading sessions. All findings validated across four independent 5-year blocks.*
