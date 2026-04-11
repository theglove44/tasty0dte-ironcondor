# Jonny $5k — The Complete Beginner's System Guide

This is the full playbook for the $5k account. Read it end to end before your first trade, and re-read Sections 5, 6, and 7 every Sunday evening for the first three months.

## Section 1 — What is this strategy?

You are running a **credit spread** strategy on the S&P 500 index. On roughly two days each month, a specific pattern appears in the first hour of US trading. When that pattern is complete, you sell an options spread that pays you a small amount of cash upfront — around $100 per trade. If the market behaves the way the pattern predicts — and historically it has around 93% of the time — that cash is mostly yours by the end of the day.

You will not be clicking buttons all day. You look at the chart for maybe ten minutes in the morning, then spend two minutes placing the trade, then walk away until early afternoon. Most days there is **no trade at all**. That is not the strategy failing — that is the strategy working.

The goal is not to get rich fast. The goal is to turn a $5,000 account into roughly $5,600–$5,900 over a year by catching around two high-quality setups per month and never blowing up.

## Section 2 — Why these specific ingredients

### Why SPX (not stocks, not SPY)

SPX is the S&P 500 index itself. It cannot be halted, delisted, or gapped on single-company news. SPX options are **cash settled** — when they expire, your account is credited or debited in cash. No shares. No assignment surprises. SPX options are **European style** — they cannot be exercised early, so a short leg can never be called away on you unexpectedly.

### Why 0DTE (zero days to expiry)

Options expiring today decay extremely fast in the final hours, which is exactly what a credit seller wants. SPX has 0DTE expiries five days a week. Shorter duration = no overnight risk. You are flat every night by definition.

### Why credit spreads (not single options)

You get paid upfront — the $100 credit lands in your account the moment the trade fills. Your maximum loss is **defined** — you know the worst case before you click. A $5-wide spread uses very little buying power (~$400), sitting comfortably in a $5k account.

## Section 3 — The PDT rule

### The one rule the US government wrote for you

FINRA says any account under $25,000 may take **no more than 3 day trades in any rolling 5 business days**. A "day trade" is opening and closing the same position in the same session.

No more than 3 day trades in any rolling 5 business days. A 4th trade triggers a 90-day freeze on day trading.

**Does SPX count?** Yes. Index options count.

**The rolling window.** Not per calendar week. If you trade Monday, Tuesday, Wednesday — Monday's trade drops off the following Monday, not Saturday. Most beginners miscount this.

**The consequence.** Your broker flags you as a Pattern Day Trader. If your account is under $25k, you get a 90-day freeze on all day trading.

**How to avoid it.** Update the PDT Counter input in the indicator settings every morning. If it shows `3/3` red, no trade today. No exceptions.

## Section 4 — The trade, explained with real numbers

### One complete trade from start to finish

1. It is 10:30 ET on a Thursday. SPX is at 5218. The indicator fires a bull DOUBLE arrow: `Short: 5200 / Long: 5195`.
2. You open TastyTrade. You find today's SPX expiry. You build a **put credit spread**: sell 1 × 5200 put, buy 1 × 5195 put.
3. You place it as a limit order at **$1.00 credit**. It fills. **$100 cash is now in your account.**
4. Immediately, you place a GTC limit order to **buy the same spread back at $0.50**. This is your profit target.
5. You set a **price alert** at $2.00 debit. This is your manual stop reminder.
6. You walk away.

#### Outcome A — the good ending (~93% of the time on DOUBLE days)

SPX drifts sideways or higher through the day. Options decay. At some point the spread's price falls to $0.50. Your GTC fills. You paid $0.50 to close what you sold for $1.00. **Net profit: $50.**

#### Outcome B — the bad ending (~7% of DOUBLE days)

SPX falls through 5200. Your alert fires at $2.00 debit. You manually close the spread. You paid $2.00 to close what you sold for $1.00. **Net loss: $100.**

#### The maths on a full year

Expected value per DOUBLE trade = (0.928 × $50) − (0.072 × $100) = +$39.20. Across ~23 DOUBLE setups per year, that is roughly +$900, or about 18% on a $5,000 account.

#### Max theoretical loss

The spread is $5 wide. Absolute worst case (stop ignored): $5.00 to close minus $1.00 credit = **$400 lost**. The $2.00 stop caps real-world loss at $100 — but $400 is the hard ceiling if you ignore every signal.

## Section 5 — The four daily decisions

### Every morning, ask four questions

1. **Is the PDT counter safe (not red)?** If red: close the laptop. No trade today.
2. **Is it a SKIP day (witching Friday)?** If yes: close the laptop. No trade today.
3. **Did DOUBLE fire by 12:00 ET?** If no: close the laptop. No trade today.
4. **If DOUBLE fired: what does the Trade row say?** Place that exact spread, at $1.00 credit limit.

## Section 6 — How to place the trade on TastyTrade

### Clicking the trade — step by step

1. In the search bar, type `SPX` and select the index.
2. Open the option chain. In the expiration dropdown, select **today's date**. 0DTE contracts appear at the top.
3. Look at the indicator's Row 6 (Trade). Suppose it reads `BPS 5200/5195`. BPS = Bull Put Spread.
4. Find the **5200 put** row. Click its **bid** price (you are selling).
5. Find the **5195 put** row. Click its **ask** price (you are buying).
6. TastyTrade's order ticket shows a two-leg spread. Verify: **1 contract, both legs, expiry = today**.
7. Change the order type to **Limit**. Set the price to **$1.00 credit**. Never use market orders on 0DTE spreads.
8. Review: you should see **+$100** as the credit received and roughly **-$400** buying power used. If the numbers look wildly different, cancel and re-check.
9. Click **Send**. Wait for fill. If it does not fill in 30 seconds, cancel and re-enter at $0.95. Do not chase below $0.90.
10. After fill: **place a closing order immediately.** Build a buy-to-close order at **$0.50 debit**, GTC. Send.
11. Set a **price alert** on the spread at **$2.00 debit**. This is your manual stop — not a resting order.

### Why not use a stop-loss order

0DTE spreads have very wide bid/ask quotes that widen further on any volatility spike. A resting stop order will get triggered on a 2-second spike and sell you out at the worst possible price. A manual alert lets you decide when to close, using the mid price rather than the extremes. Always use an alert. Never a stop order.

## Section 7 — The five rules that must never be broken

### Five rules that must never be broken

1. **One contract only until the account hits $10,000.** Breaking this: one bad day wipes out two months of gains.
2. **Honour the $2.00 stop. Always. Manually.** Breaking this: one un-stopped loss erases four winning trades.
3. **Never take a 4th day trade in a rolling 5 business days.** Consequence: 90-day trading freeze.
4. **Two consecutive losses = sit out the rest of the week.** Breaking this: tilt trading, revenge entries, blown account.
5. **Never trade on witching days.** Breaking this: win rate drops from 93% to 58% — profitable to gambling.

## Section 8 — Calendar

### When to trade and when to stay home

| Day type | Action |
|---|---|
| FOMC Wednesday | Best day of the year — trade DOUBLE with confidence |
| Thursday / Friday (non-witching) | Good days — trade DOUBLE normally |
| Tuesday / Wednesday (non-FOMC) | Average — trade DOUBLE normally |
| Monday | Below average — trade DOUBLE only on A or A+ quality |
| OpEx Friday (third Friday, non-witching) | Trade with extra caution, strict stop |
| Triple/Quad Witching (four Fridays/year) | **SKIP — do not trade** |

## Section 9 — What to expect in Year 1

### Realistic expectations

- **Frequency.** Roughly 2 DOUBLE setups per month = ~23 per year. Most days nothing fires. Waiting is correct.
- **Win size.** Most wins = +$50.
- **Loss size.** Losses = -$100 when the $2.00 stop is honoured.
- **Annual outcome.** Historical expected value: **+$600 to +$900 on a $5,000 account** (12%–18%), if you follow the rules exactly.
- **Worst month.** Two losses in a row, stop trading for the week, down ~$200 for the month.
- **This is not get-rich-quick.** High-probability, low-frequency, rule-bound grinding. The edge is real but small.

## Section 10 — Glossary

### Glossary — every term defined simply

- **0DTE** — Zero Days To Expiration. An option that expires today.
- **Bid/ask** — The best price someone will buy at (bid) and the best price someone will sell at (ask). You sell at the bid and buy at the ask.
- **Bracket order** — A trade with attached profit-target and stop-loss orders. Not recommended for 0DTE spreads — use alerts instead.
- **Breakout** — Price moving decisively above a previous high or below a previous low.
- **Call spread** — Two call options traded together — one sold, one bought at a higher strike. A bear call spread is a credit spread that profits when price stays below the short strike.
- **Cash settled** — When an option expires, the account is credited or debited in cash, not shares.
- **Close alignment** — The system's check that key 5-minute candles closed in the top 20% (bull) or bottom 20% (bear) of the opening range.
- **Credit** — Money you receive when placing a trade. A credit spread pays you upfront.
- **Credit spread** — A two-leg options trade where the sold leg is worth more than the bought leg, so you collect cash immediately.
- **Debit** — Money you pay. Closing a credit spread requires paying a debit.
- **DOUBLE tier** — The highest confirmation level in the stacking system. The only tier that is a trade signal.
- **European style** — An option that can only be exercised at expiry, not early. SPX options are European.
- **GTC order** — Good-Till-Cancelled. The order stays live until it fills or you cancel it. Used for the profit-target buyback.
- **Long strike** — The option you buy as the protection leg of the spread. Defines your maximum loss.
- **Mark price** — The theoretical fair price of an option, usually the midpoint of bid and ask.
- **ORB** — Opening Range Breakout. A strategy family that uses the first N minutes of the session as a reference range.
- **PDT rule** — Pattern Day Trader rule. Accounts under $25k are limited to 3 day trades per rolling 5 business days.
- **Profit target** — The price at which you close a winning trade. For this system: $0.50 buyback = +$50 net.
- **Put spread** — Two put options traded together. A bull put spread is a credit spread that profits when price stays above the short strike.
- **Short strike** — The option you sell. This generates your credit and defines the price level you want SPX to respect.
- **Stop loss** — The price at which you close a losing trade. For this system: $2.00 buyback = -$100 net, triggered manually from a price alert.
