# ORB RESEARCH — DEAD ENDS REGISTER
## Everything We Tested and Ruled Out
**Purpose:** Prevent re-testing ideas that have already been killed by data.  
**Rule:** If it's on this list, don't test it again unless you have NEW data or a fundamentally different framing.

---

## MACD-V (Tested Extensively — 3 Separate Research Rounds)

| Idea | What We Tested | Result | Sample | Verdict |
|------|---------------|--------|--------|---------|
| MACD-V zero-line as direction filter | Only take ORB breaks matching MACD-V direction (>0 = bull) | Aligned 64.8% vs Opposed 62.3% — 2.5% edge | 5,222 trades, 21yr | **DEAD.** Doesn't hold across periods. |
| MACD-V trend alignment | MACD-V rising at lock → favour bull | Aligned 63.7% vs Opposed 63.9% — literally zero edge | 5,222 trades | **DEAD.** |
| Histogram sign alignment | Histogram same sign as BO direction | 64.0% vs 63.4% — 0.6% edge | 5,222 trades | **DEAD.** |
| Histogram momentum alignment | Histogram accelerating toward BO direction | 64.5% vs 62.0% — 2.5%, inconsistent across periods | 5,222 trades | **DEAD.** |
| Composite MACD-V alignment score | Stack all 4 MACD-V factors into a composite | Score +4: 65.6% vs Score -4: 62.7%. Score +2 was WORSE than -4. No clean gradient. | 5,222 trades | **DEAD.** No useful discrimination. |
| MACD-V ≥ +140 extreme as short filter | 30-min finding: 0% short WR at extreme. Does it translate to 5-min? | Bear ORB breaks at 58.8% when MV > +140. Still profitable. | 226 trades, 21yr | **NOT applicable.** ORB structure protects against it. |
| MACD-V ≤ -140 extreme as long filter | Bull ORB breaks when deeply oversold | 55.6% — degraded but still above breakeven | 160 trades | **MARGINAL.** Not worth filtering. |
| MACD-V Traffic Light (5-min calibration) | Bars since last extreme, graded by recency | No clean gradient. 13-24 bar window shows 68-70% but small sample. | Various | **NOT RELIABLE** enough for a rule. |
| MACD-V as standalone signal — OB entry | Buy when MACD-V crosses above +140 | 57.0% with $15 target/$15 stop — best of all signals tested | 656 trades | **DEAD.** Not enough edge for 0-DTE. |
| MACD-V as standalone signal — OS entry | Sell when MACD-V crosses below -140 | 54.8% | 440 trades | **DEAD.** |
| MACD-V as standalone signal — all 8 types | Tested OB, OBX, OS, OSX, EM+, EM+X, EM-, EM-X in both directions | Best: 57%, Most: 50-53% | 440-1012 per signal | **ALL DEAD.** Coin flips. |
| Fade-the-extreme combos | OB→OBX (fade overbought), OS→OSX (bounce oversold) | OB→OBX: 43.1% favorable. OS→OSX: 46.9%. EM+→EM+X: 43.7%. ALL negative EV. | 382-753 trades | **DEAD.** Every fade combo loses money. |
| MACD-V zero-line crossover | Bull cross (below→above zero), Bear cross (above→below zero) | 50.8% and 49.2% — pure noise | 1,698 / 1,659 signals | **DEAD.** |
| Histogram ±40 as entry filter | Histogram extreme at lock predicts breakout quality | No edge at any level (±20, ±30, ±40, ±50). Win rates flat 76-81% across all buckets. | 5,222 trades | **DEAD for entries.** (Valid as management warning — separate finding.) |

---

## OVERNIGHT / MULTI-DAY MACD-V

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Overnight holds on MACD-V signals | Buy 1-DTE at afternoon signal, hold overnight | Best bullish signal: 68% gap favorable — but baseline overnight gap-up rate is 63.9%. Only +4% above doing nothing. | **DEAD.** Doesn't survive premium decay. |
| MACD-V extreme → next day setup | Previous day hit ±140 → predict next day's BO | +140 yesterday: next day win 79.1%, bear BO 46.5%. -140 yesterday: win 77.3%, bull BO 50.2%. No prediction. | **DEAD.** |
| EOD MACD-V state → next day | What MACD-V reads at 4PM → next morning | Continuation bias (overbought → gap up). Explained by structural drift, not signal. | **DEAD.** |
| MACD-V reset pattern | Extreme → return to neutral as reversal signal | Only 33-35% of resets lead to opposite-direction breakouts. | **DEAD.** Not reliable. |
| Double extreme days (OB+EM+ same day) | Two bullish extreme signals same day → next day | 62.6% positive next day vs 63.9% baseline. No edge. | **DEAD.** |

---

## GAP ANALYSIS

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Gap size → BO quality | Big gap up/down vs flat vs small gaps | Win rates: 62-65% across ALL gap sizes. Maximum variation: 3%. | **DEAD.** Not actionable. |
| Gap as % of ATR | Normalized gap size | 25-50% ATR gap slightly better (66.4-66.9%). Too small. | **NOT WORTH IT.** |
| Gap direction → BO direction | Gap up → bull BO more likely? | Gap up → bull: 54%. Gap down → bear: 47%. Near coin flip. | **DEAD.** |
| Gap direction × BO direction → quality | Gap up + bull BO vs gap up + bear BO | 64.8% vs 65.0% — identical. | **DEAD.** |

---

## PREVIOUS DAY / CONSECUTIVE DAYS

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Previous day direction predicts BO direction | Prev UP → Bull BO more likely? | Prev UP → Bull: 50.9%. Prev DOWN → Bear: 47.2%. Coin flip. | **DEAD.** |
| Previous day direction → BO quality | Prev UP → today's BO better? | Prev UP: 64.6%. Prev DOWN: 62.8%. Tiny edge, inconsistent. | **NOT WORTH IT.** |
| Previous day range vs ATR → quality | Narrow prev day = better breakout? | Narrow (<50% ATR): 66.6% — genuine but small edge. | **MARGINAL.** Not included in composite — too few days at extreme narrow. |
| Consecutive up days → bull BO works? | After 3, 4, 5 up days in a row | No direction prediction. After 4+: quality degrades to 59-61%. | **DEAD for direction.** Slight negative for quality. |
| Consecutive down days → bear BO works? | After 3, 4, 5 down days in a row | After 5 down days: bear BO rate only 37%. No reliable prediction. | **DEAD.** |

---

## CRABLE / NARROW RANGE THEORY (INTRADAY)

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Small ORB → expansion day | Tiny ORB (<15% ATR) predicts a big day move | Only 15.1% of tiny ORB days become big range days (>100% ATR). No predictive power. | **DEAD for intraday.** (May work on daily timeframe — not tested here.) |
| Wide ORB → continuation | ORB already >40% ATR = trending day | 65.8% of wide ORB days are big days. But this is circular — wide ORB IS the big day already. | **NOT A PREDICTOR** — it's a description. |

---

## DAY OF WEEK (PARTIALLY DEAD)

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Tuesday is best/worst day | 21-year DOW analysis | Tuesday has 13.6% spread across 5-year blocks. Wildly inconsistent. 71% one era, 57% another. | **DEAD as a reliable factor.** |
| Monday effect | Monday consistently weak? | 62.0% overall, but 6.9% spread. Not stable enough. | **WEAK.** Included in composite at -1 but marginal. |
| Thursday/Friday best | Consistent across periods? | Thursday: 2.6% spread (most stable). Friday: 4.8%. | **ALIVE.** Kept in composite. |

---

## SPECIFIC STOP/TARGET CONFIGURATIONS (PARTIALLY DEAD)

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Classic stop (opposite ORB level) | vs Options Emulator ($5 whole numbers) | Classic: 60.4%. Options Emulator: 62.8%. OE is 2.4% better. | **Classic is inferior.** Keep OE. |
| Penetration mode (wick breakout) | vs Confirmation (close outside range) | Penetration: 54.7%. Confirmation: 62.8%. 8.1% gap. | **Penetration is dead.** |
| 2x ORB range target | vs 1x and 0.5x | 2x: 52.2%. Diminishing returns beyond 1x. | **2x is marginal.** 0.5x and 1x are the sweet spots. |
| No stop (hold to EOD) | Does removing stops help? | 72.4% win rate — highest. But no risk management. | **ALIVE for options** (max loss = premium). Dead for futures. |

---

## IRON CONDOR ON NO-BREAKOUT DAYS

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| Sell iron condor when ORB doesn't break | How often does ORB20 NOT break by EOD? | 4 days in 5 years (0.3%). ~1 setup per year. | **DEAD.** Too rare to build a strategy. |
| ORB60 no-breakout iron condor | Wider range, more no-breakout days? | 49 days in 21 years (3.1%). ~8 per year. | **BARELY ALIVE** but too infrequent. |

---

## LATE SESSION BREAKOUTS

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| ORB20 breakouts after noon | Are there tradeable afternoon breakouts? | Only 26 breakouts after noon in 21 years. 98.3% break by noon. | **DEAD.** Doesn't exist as a strategy. |

---

## MACD-V ON 30-MIN AS ORB OVERLAY

| Idea | What We Tested | Result | Verdict |
|------|---------------|--------|---------|
| 30-min MACD-V Traffic Light on 5-min ORB | Apply Tag n Turn findings directly | 0% short WR becomes 58.8% on ORB. The defined ORB structure protects trades. | **DOESN'T TRANSLATE.** Different system, different behaviour. |
| Synthetic 30-min MACD-V from 5-min bars | Calculate higher TF indicator | Not tested — ruled out because 5-min MACD-V already showed no edge. Higher TF unlikely to help more. | **SKIPPED.** Low probability of payoff. |

---

## HOW TO USE THIS DOCUMENT

1. **Before testing any "new" idea:** Search this list first. If it's here, don't re-test it.

2. **Exception:** If you have fundamentally NEW data (new instrument, new timeframe, different market regime post-2026), the findings may not hold. But re-test with awareness of what we found here.

3. **"Marginal" items** (marked as such) could become viable if combined with a new factor we haven't discovered yet. But alone, they don't justify the complexity.

4. **"Dead" means dead.** Not "might work with tweaking." The data is clear across 5,000+ trades and 21 years. These ideas have been given every chance.

---

## WHAT WAS TESTED AND SURVIVED

For reference, here's what made it through the filter and IS in the production system:

| Factor | Edge | In System As |
|--------|------|-------------|
| ORB Stacking (20+30+60 same direction) | 80.3% favorable (vs 68.8% base) | Core feature — progressive confirmation |
| ORB Close alignment | 65.8% vs 60.3% (neutral) | Quality signal |
| Range expansion ratio (OR60/OR20) | 88.8% at ≥ 2.5x ratio | Quality enhancer |
| Breakout timing (immediate) | 65.9% vs 58.2% (delayed) | Scoring factor |
| ATR filter (15-20% sweet spot) | 73.4% in recent data | Scoring factor |
| Buffer (A+ = ≥$4) | +4.5% edge on credit spreads | Credit spread quality |
| Day of week (Thu/Fri) | 64.5-65.2%, most stable | Scoring factor |
| FOMC Wednesday | 68.1% | Calendar overlay |
| Triple witching | 58.0% | Calendar warning |
| Last Friday of month | 67.9% (bear bias 71.8%) | Calendar overlay |
| Histogram ±40 (management only) | 62.0% vs 70.5% (bull trades) | Trade management warning |
| ORB as day predictor | 72-78% close in BO direction | Lazy day trade framework |
| 0.5x target | 79.3% win rate | Alternative target mode |
| Options Emulator stop | +2.4% vs Classic | Default stop mode |
| Confirmation mode | +8.1% vs Penetration | Default breakout trigger |

---

**Last updated:** April 2026  
**Total research hours:** Multiple sessions across ORB strategy R&D  
**Data:** 409,644 five-minute SPX bars, 21 years (2005-2026)

**If you're reading this in 2027+:** The market may have changed. But if someone suggests "have you tried using MACD-V as a direction filter?" — the answer is yes, across 5,222 trades and 21 years. It doesn't work. Show them this document.
