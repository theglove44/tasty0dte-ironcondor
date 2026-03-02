# 0DTE SPX Options Trading System

## 1. System Overview
* **Asset:** S&P 500 Index Options (SPX)
* **Expiration:** 0DTE (Zero Days to Expiration)
* **Core Logic:** Strategy selection is dynamically determined by the underlying asset's price action during the first 30 minutes of the regular trading session.

## 2. Phase 1: Observation & Timing (Entry Trigger)
* **Action:** Do not execute any trades immediately at the market open.
* **Wait Period:** Observe the market for exactly 30 minutes from the opening bell.
* **Time of Decision:** 15:00 PM GMT 
* **Data Requirement:** Calculate the percentage change of the SPX from the Opening Price to the Current Price at the 30-minute mark.

## 3. Phase 2: Strategy Selection (Decision Tree)
Evaluate the SPX percentage change calculated in Phase 1 to determine the appropriate options strategy.

### Condition A: Flat or Upward Market
* **Criteria:** SPX is UP, or SPX is DOWN by less than **0.1%** (Move > -0.1%).
* **Market Thesis:** Volatility is contracting or stable; market is grinding or mean-reverting.
* **Selected Strategy:** Iron Condor (Out-of-the-Money).

### Condition B: Downward Market
* **Criteria:** SPX is DOWN by **0.1%** or more (Move <= -0.1%).
* **Market Thesis:** Downward price action has caused a short-term implied volatility (IV) spike. 
* **Selected Strategy:** Iron Fly (At-the-Money).

## 4. Phase 3: Execution Parameters
Construct the selected strategy using the following mechanical parameters. All executions assume mid-price fills.

### Setup A: Iron Condor Execution
* **Short Strikes (Call & Put):** Sell the **20 Delta** options.
* **Long Strikes (Wings):** Buy protection **$20** wide from the short strikes on both the call and put sides.
* **Max Risk:** **$20** minus the total premium collected.

### Setup B: Iron Fly Execution
* **Short Strikes (Call & Put):** Sell the **50 Delta** options (ATM Straddle).
* **Long Strikes (Wings):** Buy protection **$10** wide from the short strikes on both the call and put sides.
* **Max Risk:** **$10** minus the total premium collected.

## 5. Phase 4: Exit Criteria & Risk Management
Strict adherence to the profit target is required to maintain the statistical edge and win rate (~90% for Condors under these conditions).

* **Primary Exit (Take Profit):** The take profit is set at **20%** of the maximum profit. 
    * *Calculation:* If total initial credit received is **$5.00**, buy to close the spread at **$4.00** (capturing **$1.00**, or **20%**).
* **Secondary Exit (Time Stop / Max Loss):** If the **20%** profit target is not achieved by the end of the trading session, close the position entirely before the market closes (e.g., 20:55 PM GMT) to avoid assignment risk and cash settlement surprises. Max loss is capped by the defined width of the wings. Do not hold through expiration.