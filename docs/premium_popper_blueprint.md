# Premium Popper — ORB20 1st Breakout Strategy Blueprint

## Purpose

This document is a developer-ready specification for implementing the Premium Popper ORB20 1st Breakout strategy as an automated trading module. It should be integrated into the existing 0-DTE bot infrastructure that uses the Tastytrade API.

The strategy sells 0-DTE credit spreads on SPX (or RUT/XSP) based on a 20-minute Opening Range Breakout. Every rule is mechanical with zero discretion.

---

## Strategy Overview

| Parameter | Value |
|---|---|
| Instrument | SPX (primary), RUT, XSP |
| Options Type | 0-DTE, cash-settled, European-style |
| Trade Structure | Vertical credit spread (put spread or call spread) |
| Spread Width | $5 wide |
| Premium Target | ~$1.00 to $1.20 collected |
| Profit Target | Buy back at $0.50 (50% of credit collected) |
| Stop Loss | Buy back at $2.00 (100% of credit added to entry) |
| Short Strike Delta | ~20 delta |
| Active Window | 09:50 ET to 12:00 ET (alert expiry) |
| Trade Duration | Typically 30–90 minutes after entry |
| Trades Per Day | 1 (one signal, one trade, one outcome) |

---

## Phase 1: Pre-Market Setup (Before 09:30 ET)

### Economic Calendar Check

Before the session opens, check for major scheduled economic releases that fall within the first 30 minutes of the regular session (09:30–10:00 ET).

**High-impact events to flag:**
- Federal Reserve announcements
- Non-Farm Payrolls (NFP)
- Consumer Price Index (CPI)
- Any event that occurs *during* regular session hours (not pre-market releases)

**Logic:**
- Most major news is released before the open — those are fine.
- Only flag events scheduled during regular trading hours (09:30 ET onward).
- If a high-impact event falls within the ORB20 window (09:30–09:50 ET) or shortly after, the opening range may be distorted. Log a warning but still collect the range data. The invalid conditions check (Phase 4) handles the final go/no-go.

**Implementation note:** Use an economic calendar API or data feed to automate this check. Store the result as a boolean flag: `has_major_news_during_session = true/false`.

---

## Phase 2: Build the Opening Range (09:30–09:50 ET)

### Data Collection

Collect 5-minute candle data for the instrument (SPX) from 09:30 to 09:50 ET. This produces exactly four 5-minute candles:

| Candle | Start | End |
|---|---|---|
| 1 | 09:30 | 09:35 |
| 2 | 09:35 | 09:40 |
| 3 | 09:40 | 09:45 |
| 4 | 09:45 | 09:50 |

### Range Calculation

At exactly 09:50 ET (when candle 4 closes):

```
orb_high = max(high of candle 1, high of candle 2, high of candle 3, high of candle 4)
orb_low  = min(low of candle 1, low of candle 2, low of candle 3, low of candle 4)
orb_range = orb_high - orb_low
```

### Bias Calculation

Use the **close price of the 09:50 candle** (candle 4) to determine bias.

```
close_position = (candle_4_close - orb_low) / orb_range
```

| Close Position | Bias | Action |
|---|---|---|
| >= 0.60 (top 40%) | Bullish | Watch for break above `orb_high` |
| <= 0.40 (bottom 40%) | Bearish | Watch for break below `orb_low` |
| Between 0.40 and 0.60 | Neutral / No bias | Either direction is valid (see note) |

**Note on neutral zone:** If not constrained by Pattern Day Trade rules, trades in either direction are valid regardless of bias. The bias check identifies the higher-probability side. If PDT-constrained, only trade the biased direction.

### Store Values

```
orb_high          = [calculated]
orb_low           = [calculated]
orb_range         = orb_high - orb_low
orb_midpoint      = orb_low + (orb_range / 2)
bias              = "bullish" | "bearish" | "neutral"
alert_level       = orb_high (if bullish) or orb_low (if bearish) or both (if neutral)
alert_expiry_time = 12:00:00 ET
```

---

## Phase 3: Monitor for Breakout (09:50 ET – 12:00 ET)

### Breakout Detection

After 09:50 ET, monitor the 5-minute candle data in real time. A valid breakout requires a **candle close** beyond the ORB level — a wick penetration alone is NOT valid.

**Bullish breakout (watching `orb_high`):**
```
IF candle_close > orb_high → valid bullish breakout
IF candle_high > orb_high BUT candle_close <= orb_high → NOT valid (wick only)
```

**Bearish breakout (watching `orb_low`):**
```
IF candle_close < orb_low → valid bearish breakout
IF candle_low < orb_low BUT candle_close >= orb_low → NOT valid (wick only)
```

### Expansion Filter

The breakout candle must show expansion — not a weak drift through the level. This is the one area that requires a programmatic definition since the manual describes it qualitatively.

**Suggested implementation (tune as needed):**

```
breakout_candle_body = abs(candle_close - candle_open)
min_expansion = orb_range * 0.10  // at least 10% of the ORB range as candle body size

IF breakout_candle_body >= min_expansion → expansion confirmed
ELSE → weak drift, skip trade
```

**Alternative approach:** Require the close to be at least X points beyond the ORB level (not just barely past it). For SPX, a minimum of 1–2 points beyond the level could work.

**Note:** This parameter may need tuning through backtesting. Start conservative (lower threshold) and tighten if false signals are too frequent.

### Timeout

```
IF current_time >= 12:00:00 ET AND no valid breakout has occurred:
    → No trade today. Cancel monitoring. Log "No breakout before noon."
```

---

## Phase 4: Invalid Conditions Check

Before executing the trade, validate the breakout against these conditions. If any are true, abort the trade.

### Condition 1: Wick-Only Penetration
```
IF price penetrated ORB level but did NOT close outside it → NO TRADE
```
(Already handled by the breakout detection logic in Phase 3, but double-check here.)

### Condition 2: Immediate Violent Reversal
```
IF within the first 1-2 candles after breakout, price reverses and closes back inside the ORB range → NO TRADE
```

**Implementation:** After detecting a valid breakout close, optionally wait for the next candle to confirm price remains outside the range. This adds a slight delay but filters false breakouts. Alternatively, skip this check and rely on the stop loss to manage failed breakouts.

### Condition 3: Major News Distortion
```
IF has_major_news_during_session == true AND breakout occurred within 5 minutes of the scheduled release → NO TRADE
```

### Condition 4: No Expansion
```
IF expansion filter (Phase 3) failed → NO TRADE
```

---

## Phase 5: Trade Execution

### Determine Trade Direction

| Breakout Direction | Spread Type | Short Strike Side |
|---|---|---|
| Bullish (close above `orb_high`) | **Put credit spread** (sell put, buy lower put) | Below the ORB range |
| Bearish (close below `orb_low`) | **Call credit spread** (sell call, buy higher call) | Above the ORB range |

### Strike Selection

**Method 1 — Delta-based (primary):**
```
short_strike = find strike on 0-DTE chain with delta closest to 0.20 (20 delta)
              on the OPPOSITE side of the range from the breakout direction

For bullish breakout: find PUT with ~20 delta (below orb_low)
For bearish breakout: find CALL with ~20 delta (above orb_high)
```

**Method 2 — Midpoint-based (alternative, more conservative):**
```
short_strike = strike closest to orb_midpoint on the opposite side
```

**Long strike (protection leg):**
```
For put spread:  long_strike = short_strike - 5  ($5 further OTM)
For call spread: long_strike = short_strike + 5  ($5 further OTM)
```

### Premium Validation

Before placing the order, validate the credit received:

```
expected_credit = mid_price of (short_strike_premium - long_strike_premium)

IF expected_credit >= 0.80 AND expected_credit <= 1.50:
    → Proceed with trade
ELSE IF expected_credit < 0.80:
    → Premium too low. Skip trade or adjust strikes. Log warning.
ELSE IF expected_credit > 1.50:
    → Unusual premium. Proceed with caution. Log for review.
```

**Target range:** $1.00 to $1.20 is ideal. The 0.80–1.50 range provides acceptable flexibility.

### Order Placement

Place the credit spread as a single order (not individual legs):

```
order = {
    type: "credit_spread",
    instrument: "SPX",  // or RUT / XSP
    expiration: today (0-DTE),
    
    // For bullish breakout (put credit spread):
    sell_leg: PUT at short_strike,
    buy_leg:  PUT at long_strike (short_strike - 5),
    
    // For bearish breakout (call credit spread):
    sell_leg: CALL at short_strike,
    buy_leg:  CALL at long_strike (short_strike + 5),
    
    quantity: [position_size],  // based on account risk management
    order_type: "limit",
    limit_price: expected_credit (or slightly below mid for fill)
}
```

### Fill Confirmation

Wait for fill confirmation before setting management orders. Log:
- Fill price (actual credit received)
- Fill time
- Strike prices
- Delta at time of fill

```
actual_credit = [filled credit amount]
```

---

## Phase 6: Trade Management (Bracket Order)

Immediately after fill confirmation, place a bracket (OCO — one-cancels-other) order:

### Profit Target

```
target_price = actual_credit * 0.50   // 50% of credit collected

// Buy to close the spread at target_price
// e.g., if collected $1.00, buy back at $0.50 → keep $0.50 profit
```

### Stop Loss

```
stop_price = actual_credit * 2.00     // 100% of credit added to entry

// Buy to close the spread at stop_price
// e.g., if collected $1.00, buy back at $2.00 → net loss of $1.00
```

### Bracket Order

```
bracket = {
    // Profit target leg
    take_profit: {
        action: "buy_to_close",
        spread: [same spread],
        limit_price: target_price,      // e.g., $0.50
    },
    
    // Stop loss leg
    stop_loss: {
        action: "buy_to_close",
        spread: [same spread],
        stop_price: stop_price,         // e.g., $2.00
    },
    
    type: "OCO"  // one cancels other
}
```

### Management Rules

- **Do NOT move stops.**
- **Do NOT adjust targets.**
- **Do NOT close early.**
- **Do NOT interfere with the bracket order.**
- The bracket order manages the trade mechanically. No human (or bot) override.

### End-of-Day Handling

If neither the target nor the stop has been hit by market close (16:00 ET):

```
IF spread is OTM (short strike not breached):
    → SPX options are cash-settled. Let expire worthless. Full credit kept.
IF spread is ITM or near ITM:
    → The bracket order should have triggered the stop. If not, close the position manually
      before 15:50 ET to avoid settlement risk on the boundary.
```

---

## Phase 7: Logging and State Management

### Trade Log — Record for Every Session

```json
{
    "date": "YYYY-MM-DD",
    "instrument": "SPX",
    "orb_high": 5920.00,
    "orb_low": 5905.00,
    "orb_range": 15.00,
    "orb_midpoint": 5912.50,
    "bias": "bullish",
    "close_position": 0.72,
    "breakout_time": "10:12:00 ET",
    "breakout_direction": "bullish",
    "breakout_candle_body": 4.50,
    "expansion_confirmed": true,
    "major_news_flag": false,
    "trade_executed": true,
    "spread_type": "put_credit_spread",
    "short_strike": 5900,
    "long_strike": 5895,
    "short_delta_at_entry": 0.19,
    "credit_received": 1.05,
    "target_price": 0.53,
    "stop_price": 2.10,
    "exit_price": 0.50,
    "exit_reason": "target_hit",
    "exit_time": "11:03:00 ET",
    "pnl_per_contract": 0.55,
    "contracts": 1,
    "total_pnl": 55.00,
    "notes": ""
}
```

### No-Trade Log — Record When No Trade Taken

```json
{
    "date": "YYYY-MM-DD",
    "instrument": "SPX",
    "orb_high": 5920.00,
    "orb_low": 5905.00,
    "orb_range": 15.00,
    "bias": "neutral",
    "trade_executed": false,
    "skip_reason": "no_breakout_before_noon",
    "notes": ""
}
```

### Skip Reasons (enum)

```
"no_breakout_before_noon"
"wick_only_no_close"
"weak_expansion"
"major_news_distortion"
"immediate_reversal"
"premium_too_low"
"premium_too_high"
"api_error"
"manual_override"
```

---

## Position Sizing

The manual does not specify exact position sizing rules. This should integrate with your existing risk management framework.

**Suggested approach:**

```
max_risk_per_trade = account_value * risk_percentage  // e.g., 1-2% of account

risk_per_contract = (spread_width - credit_received) * 100
                  // e.g., ($5.00 - $1.00) * 100 = $400 per contract
                  // BUT with stop at $2.00, actual risk = ($2.00 - $1.00) * 100 = $100 per contract

contracts = floor(max_risk_per_trade / actual_risk_per_contract)
```

**Note:** The maximum risk on the spread is $400 per contract (spread width minus credit), but the stop loss at $2.00 limits actual risk to $100 per contract ($2.00 - $1.00 = $1.00 × 100 multiplier). Size based on the stop loss risk, not the theoretical max.

---

## Timing Summary

| Time (ET) | Action |
|---|---|
| Pre-09:30 | Check economic calendar. Ensure data feeds and broker connection are live. |
| 09:30 | Session opens. Begin collecting 5-min candle data. |
| 09:50 | ORB20 range is set. Calculate high, low, range, midpoint, bias. Set alert level. |
| 09:50–12:00 | Monitor for candle close beyond alert level. |
| On breakout | Validate conditions. Execute credit spread. Set bracket order. |
| After entry | Do nothing. Bracket order manages the trade. |
| 12:00 | If no breakout, cancel monitoring. No trade today. |
| 16:00 | Session close. Cash settlement for any remaining positions. |

---

## Edge Cases and Error Handling

### Gap Days
If SPX gaps significantly at the open (e.g., >1% gap), the ORB20 range may be unusually wide or narrow. The strategy still applies — mark the range and follow the rules. The delta-based strike selection will naturally adjust for wider/narrower ranges.

### Very Narrow Range
If `orb_range` is extremely small (e.g., < 3 points on SPX), the short strike may end up very close to the range. The 20-delta selection should still provide adequate distance, but log a warning for review.

### Very Wide Range
If `orb_range` is very large (e.g., > 30 points on SPX), the short strike will be far from current price and the credit may be lower than $1.00. Check premium validation before executing.

### API Failures
If the Tastytrade API fails during any phase:
- Log the error with full context.
- Do NOT retry blindly during the breakout window — market conditions change rapidly.
- If the fill fails, do not chase. Missed trade is better than a bad fill.

### Partial Fills
If the spread only partially fills:
- Set the bracket order on the filled quantity.
- Optionally cancel the remaining unfilled portion.
- Do NOT leave naked legs.

### Multiple Instruments
If running on SPX and RUT simultaneously:
- Treat each instrument independently.
- Each gets its own ORB20 range, bias, breakout detection, and trade execution.
- They are separate trades with separate management.

---

## XSP Note

XSP (mini-SPX) is one-tenth the size of SPX. Same settlement rules, same strategy logic. Use for smaller accounts or more precise position sizing. The spread width and premium targets scale accordingly — use the same delta-based selection process.

---

## Summary: Decision Flowchart

```
09:30 → Collect candle data
09:50 → Calculate ORB high, low, range, bias
         ↓
Monitor for candle close beyond ORB level
         ↓
     ┌─── No close by 12:00 ET ──→ NO TRADE
     │
     └─── Candle closes beyond level
              ↓
         Check: Close outside range? (not just wick)
              ↓ YES
         Check: Expansion confirmed?
              ↓ YES
         Check: No major news distortion?
              ↓ YES
         Check: No immediate violent reversal?
              ↓ YES
         ═══════════════════════════
         EXECUTE TRADE
         ═══════════════════════════
              ↓
         Find ~20 delta short strike (opposite side of range)
         Build $5-wide spread
         Validate premium (~$1.00)
         Place credit spread order
         Wait for fill
              ↓
         Set bracket order:
           Target: 50% of credit (buy back at $0.50)
           Stop: 100% added to entry (buy back at $2.00)
              ↓
         HANDS OFF. Let bracket manage.
```

---

## What This Blueprint Does NOT Cover

This blueprint covers only the **1st Breakout (ORB20)** — the core daily setup. The full Premium Popper system includes additional setups that can be added as separate modules later:

- **2nd Breakout** — Continuation trade after price retraces to the middle 20% of the ORB20 range and breaks out again. Same credit spread structure.
- **3rd Breakout** — Uses the 60-minute opening range (09:30–10:30 ET) with the same Premium Popper options setup.
- **Lazy Popper** — Same 60-minute range, but no stop loss, no target. Hold to expiry for full premium collection. Uses 30-delta short strike instead of 20-delta.
- **Anchored VWAP** — Continuation trades using volume-weighted average price anchored to ORB range highs/lows. Used on trend days after both ORB20 and ORB60 are broken.

These are separate strategy modules that layer on top of the 1st Breakout foundation.
