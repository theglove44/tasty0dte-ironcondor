# Jonny $5k's Guide to Trading ORB Stacking Under PDT

---

## 1. PDT Reality Check

**The rule:** Any margin account under $25,000 is capped at **3 day trades per rolling 5 business days**. SPX and XSP are **not exempt** — index options count. A 0DTE credit spread opened and closed same-day = **1 day trade consumed**.

**What about expiration?** If the spread expires worthless, that is not a day trade. But you should never let a 0DTE $5-wide spread ride to expiration with a $5k account — pin risk on the short strike can blow up the position. Assume every trade you open gets closed same-day = 1 day trade consumed.

**The cliff:** 3 day trades per 5-day rolling window. A 4th trade flags you as a Pattern Day Trader. The broker freezes you out of day-trading for 90 days or until you fund to $25k. **This is a cliff, not a slope. Never take the 4th trade.**

---

## 2. EV Math — Why DOUBLE Only

Per contract mechanics: $1.00 credit collected, profit target at $0.50 buyback (+$50), stop at $2.00 buyback (−$100 net).

| Tier | Win Rate | EV per Trade |
|---|---|---|
| DOUBLE | 92.8% | (0.928 × $50) − (0.072 × $100) = **+$39.20** |
| PLUS only (ex-DOUBLE) | 77.6% | (0.776 × $50) − (0.224 × $100) = **+$16.40** |
| PLUS+DOUBLE combined | 80.2% | **+$20.30** |
| ORB60 opposes | 34.6% | **−$82.70** — never trade, it's the hard exit signal |

DOUBLE has **2.4× the EV of PLUS alone.** With only 3 bullets per week, never spend one on a PLUS when a DOUBLE is available.

---

## 3. Is PDT Actually a Binding Constraint?

DOUBLE fires on **11.5% of days = ~23 days/year = ~0.44 days/week.**

The odds of 4+ DOUBLE setups in any 5-day window are statistically negligible. **PDT is essentially never a binding constraint if Jonny trades DOUBLE-only.** He will rarely hit even 2 per week, let alone 3.

PLUS+DOUBLE combined fires 65.7% of days (~3.3/week) — that one would hammer the PDT cap constantly.

**Two regimes:**

| Regime | What to trade | Trades/year | Est. annual edge | PDT impact |
|---|---|---|---|---|
| A — DOUBLE only | DOUBLE tier only | ~23 | +$900/contract (~18% on $5k) | Never binds |
| B — DOUBLE + best PLUS | DOUBLE + graded PLUS up to 3/week | ~130 | +$3,250/contract | Now binding — requires setup prioritisation |

**Recommendation:** Start in Regime A for 2–3 months to build execution discipline. Graduate to Regime B after banking a cushion and reaching $5,500+ in the account.

---

## 4. What Triggers a DOUBLE

All four conditions must be true at **10:30 ET** before entering:

1. **ORB20 broke** — a 5-min bar closed outside the 09:30–09:50 range, direction established
2. **ORB30 confirmed** in the same direction (not opposed)
3. **ORB60 confirmed** in the same direction
4. **All 3 ORB closes are aligned** with the breakout direction:
   - Bull: each ORB's lock-bar closed in the **top 20%** of its range (close_pct ≥ 80%)
   - Bear: each ORB's lock-bar closed in the **bottom 20%** of its range (close_pct ≤ 20%)

If any box is not checked at 10:30 ET: **do nothing today.** Patience is the strategy.

---

## 5. When DOUBLE Fires 4+ Times in a 5-Day Window

Rare, but it will happen eventually. Priority stack:

**Hard skip (regardless of everything else):**
- Triple/Quad witching Friday (−2 overlay)
- Any day where the calendar overlay total is negative

**Rank remaining candidates by composite score — take the top 3:**

| Priority | Factor | Edge |
|---|---|---|
| 1 | Calendar overlay | FOMC Wednesday (+1) beats everything. FOMC + quarter-end = maximum conviction. |
| 2 | Base setup grade | Sum of ORB/ATR, breakout timing, close alignment, strike buffer, day-of-week factors |
| 3 | Day of week | Thu/Fri > Wed/Tue > Mon (Monday carries a −1 base factor) |
| 4 | ORB/ATR ratio | Tight ORB (<20% ATR) at DOUBLE tier is the single best setup in the 21-year dataset |
| 5 | Strike buffer | ≥$4 to nearest $5 strike beats <$1 buffer meaningfully |

Take the top 3 by composite. Skip the 4th. Do not split, do not average — one contract, best three setups.

---

## 6. Calendar Overlays

Check these before the session opens:

| Day type | Adjustment | Action |
|---|---|---|
| Triple/Quad witching | −2 | **Skip even if DOUBLE fires** — win rate drops to 58% |
| OpEx Friday | −1 | Skip or reduce size |
| FOMC Wednesday | +1 | Highest conviction DOUBLE of the year |
| Last Friday of month | +1 | Lean in |
| Quarter end | +1 | Lean in |
| Monday | −1 (base grade) | Caution — worst day of week for ORB |
| Thursday / Friday | +1 (base grade) | Best days of week |

---

## 7. Account Growth Path

PDT stops mattering at **$25,000.**

| Regime | Est. annual edge | Realistic years to $25k |
|---|---|---|
| A — DOUBLE only | +$900/contract | ~22 years — training wheels, not a growth plan |
| B — DOUBLE + best PLUS | +$3,250/contract, scaling | **4–6 years with disciplined execution** |
| B + deposits ($500/mo) | strategy P/L + deposits | **~2–3 years** |

The fastest path: **combine monthly deposits with Regime B.** The strategy accelerates compounding; deposits solve the capital problem directly.

---

## 8. Execution Checklist

### Pre-market (before 09:30 ET)
- Check calendar overlay — witching Friday? Stand down. FOMC? Flag as A+ candidate.
- Verify buying power: 1 contract fits, account is in good standing.
- Check PDT counter: how many day trades have been used in the rolling 5-day window?

### 09:30–09:50 ET — ORB20 formation
- Do nothing. Watch the range build.
- At 09:50 ET, the ORB20 locks. Note the lock-bar close_pct in the status panel.

### 09:50–10:00 ET — ORB30 watch
- If no breakout yet, wait.
- **Do not enter on ORB20 alone.** Wait for full DOUBLE confirmation.

### 10:00 ET — ORB30 lock
- ORB30 confirms same direction? Hold for ORB60.
- ORB30 opposes ORB20? **Setup is dead — no trade today.**

### 10:30 ET — ORB60 lock, decision point
- All 3 ORBs confirmed same direction + all 3 close_pct aligned? → **DOUBLE. Enter.**
- Only partial alignment? → PLUS. Enter in Regime B only if it passes the grade filter above.
- ORB60 opposes? → Do nothing. (If already in a position from ORB20/30, this is a hard exit — close immediately.)

### Strike selection (bull breakout example)
- SPX at 5200, ORB20 midpoint at 5180
- Sell put spread: **short the 5180 put, long the 5175 put**
- Target credit: ~$1.00
- If credit < $0.80: skip — not worth the risk
- Symbol format: `.SPXW{YYMMDD}P5180` / `.SPXW{YYMMDD}P5175`

### Entering the order
- **Limit credit order only.** Never market a 0DTE spread.
- If the order does not fill within 60 seconds at the target, walk away.
- Immediately set a **GTC limit buyback at $0.50** (profit target) after the fill.
- Set a **manual alert at $2.00 debit** for the stop — broker GTC stops on wide 0DTE spreads can misfire.

### Managing the trade
- Profit target fills: done. Next DOUBLE in ~2 weeks.
- Stop alert at $2.00 debit: **close manually.** Do not hesitate.
- **15:30 ET time stop:** if still open and not at target, close it. Do not let theta-gamma roulette decide the outcome near expiration.

---

## 9. Risk Management

| Item | Number |
|---|---|
| Max theoretical loss ($5-wide less $1 credit) | $400/contract = 8% of $5k |
| **Practical stop (2× credit)** | **$100 = 2% of account** |
| Profit target | $50 = 1% of account |
| Breakeven win rate at this payoff ratio | 66.7% |
| Probability of 5 consecutive losses at 92.8% WR | 0.072⁵ ≈ 1 in 520,000 |
| Probability of 5 consecutive losses at 77.6% WR (PLUS) | 0.224⁵ ≈ 1 in 1,800 |

### Rules that must never be broken

1. **One contract only** until account ≥ $10,000
2. **Always honour the stop** — skip it once and the annual edge is erased
3. **Two consecutive losses:** sit out the rest of the week
4. **Three consecutive losses ever:** review the trade log, identify what broke, do not trade again until you can articulate it
5. **No rolling, no adjustments, no averaging down** — 0DTE either works in 2 hours or it does not
6. **Never take the 4th day trade in a rolling 5-day window. Ever.**

**The real risk is not the spread — it is the trader.** Strategy edge is +$39 per DOUBLE trade. Skipping the stop once costs $300 of edge. Taking one revenge trade on a no-breakout day (EV −$42) costs another $80. Discipline is the alpha. The backtest is the ceiling; execution determines where in the range you actually land.

---

## Summary Card

| Item | Value |
|---|---|
| PDT limit | 3 day trades / rolling 5 business days. Index options count. Never take the 4th. |
| Setup | DOUBLE only — all 3 ORBs same direction + all 3 closes aligned at 10:30 ET |
| Frequency | ~23 days/year (~2/month). PDT never binds on DOUBLE-only. |
| Instrument | SPX 0DTE $5-wide credit spread |
| Strike | Short at ORB20 midpoint (OTM side), long $5 further OTM |
| Credit target | ~$1.00. Skip if < $0.80. |
| Profit target | $0.50 buyback = +$50/contract (GTC limit) |
| Stop | $2.00 buyback = −$100/contract (manual) |
| Time stop | 15:30 ET latest — close it |
| Annual baseline | +$900/contract (~18% on $5k) in Regime A |
| Growth regime | Regime B (DOUBLE + graded PLUS, up to 3/week) = +$3,250/year, PDT-managed |
| Path to $25k | 4–6 years Regime B. Faster with monthly deposits. |
| Best single trade | DOUBLE on FOMC Wednesday with ORB/ATR < 20% and Thursday/Friday |
| Worst mistake | Taking the 4th day trade |
