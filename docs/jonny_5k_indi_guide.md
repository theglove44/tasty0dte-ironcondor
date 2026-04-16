# Jonny $5k — TradingView Indicator Guide

## Section 1 — What this indicator does

The indicator watches the first hour of the US market looking for a specific rare pattern. When complete, it draws an arrow telling you the exact trade to place. Most days the arrow never appears. That is normal and expected.

## Section 2 — Setup

### Setting up the indicator

1. Open TradingView. Load an SPX chart (ticker `SPX` or `CBOE:SPX`).
2. Set the timeframe to **5 minutes** — the indicator will throw an error on any other timeframe.
3. Open Pine Editor (bottom panel). Paste the full contents of `docs/jonny_5k_indi` into the editor. Click **Add to chart**.
4. In the indicator settings, find the group labelled **── Trade ──**. Set **Day trades used this week** to match your current PDT count. Update this every morning before the open.
5. Save the chart layout so the indicator reloads every session.

**If you forget to update the PDT counter, the panel will lie to you.**

## Section 3 — The ORB20 box

### The blue box — the opening range (ORB20)

ORB stands for Opening Range Breakout. The first 20 minutes of the US session (09:30–09:50 ET) are when the day's battle between buyers and sellers is loudest. The indicator draws a translucent blue box covering the high and low of those first 20 minutes. That box is your map for the rest of the morning. The 20-minute window is long enough for real information to flow in, yet short enough to not miss the whole morning waiting.

## Section 4 — The green zone

### The green zone inside the box

The top 20% of the ORB20 range is shaded green. If the 09:45 ET candle closes inside this green zone, buyers won the opening twenty minutes decisively. This is one ingredient for a bull DOUBLE setup. For example: ORB20 high = 5215, low = 5185, range = 30 points. Top 20% = 5209–5215. A close at 5210 counts; a close at 5208 does not. The green zone (along with the ORB20 box itself) stops extending at 11:30 ET — after that only the H/L and midpoint lines remain visible.

## Section 5 — The red zone

### The red zone inside the box

The bottom 20% of the ORB20 range is shaded red. A close in the red zone means sellers won decisively. This is one ingredient for a bear DOUBLE setup. Using the same example: red zone = 5185–5191. Close at 5190 counts; 5192 does not.

## Section 6 — The dashed midpoint line

### The dashed line — your short strike

A light blue dashed horizontal line through the middle of the ORB20 box. **This is the level where your short strike will be placed** if a trade fires. The short strike is the leg of the spread you sell — the one that generates your income. The indicator snaps this midpoint to the nearest $5 because SPX strikes only exist at $5 intervals. In the worked example: midpoint = 5200, so short strike = 5200.

## Section 7 — The ORB20 H/L extension lines

### The solid blue lines — ORB20 high and low

After the box locks at 09:50, two solid blue horizontal lines extend rightwards from the ORB20 high and low, all the way to 15:55 ET. These are your reference levels for the rest of the day. When price crosses the high line going up, that is the ORB20 breakout. **These are the only horizontal ORB lines on your chart.** There are no 30-minute or 60-minute range lines drawn. The system uses those internally to confirm the setup, but they never appear as drawings.

## Section 8 — The ATR envelope lines

### The dotted gray lines — ATR-based volatility envelope

After ORB20 locks at 09:50 ET, two dotted gray horizontal lines appear symmetrically around the ORB20 midpoint. These lines represent the Average True Range (ATR) over the last 14 bars, placed ±ATR/2 from the midpoint. These lines give you a quick visual sense of current volatility around the trade midpoint.

The indicator also displays the **ORB/ATR ratio** in the status panel Row 10. This ratio compares the ORB20 range to ATR:
- **Green (< 0.20):** tight opening range. The day has room to trend. Best conditions for a clean breakout.
- **Amber (0.20–0.40):** normal opening range relative to volatility.
- **Red (> 0.40):** the opening range already consumed a large share of expected volatility. Lower probability of a clean continuation trend.

The ATR envelope is context only. It is never a reason to skip a valid DOUBLE signal. Its primary use is helping you prioritise which DOUBLE to spend a day trade on when you have multiple DOUBLE setups in a week and limited PDT slots. When multiple DOUBLEs appear in a rolling 5-day window, prefer the day where the ORB/ATR ratio is lowest (tightest range).

The envelope lines themselves are optional visual reference. The ORB/ATR ratio in the panel is the key metric.

## Section 9 — HALF, NORMAL, PLUS labels

### Signal labels that require no action

Three labels appear during the morning as the system's confidence builds. They are **watch-only**. You do nothing when you see them. They are not trade signals. They are the system building up internally.

Order of appearance: HALF when ORB20 breaks (earliest 09:50), NORMAL when ORB30 confirms (earliest 10:00), then at the ORB60 check (earliest 10:30) the tier becomes either **PLUS** (partial close alignment — no trade) or **DOUBLE** (full alignment — trade). PLUS and DOUBLE are two alternative outcomes of the same final check. A session that shows PLUS will never then progress to DOUBLE. **Only DOUBLE is a trade signal.**

## Section 10 — The DOUBLE entry arrow

### The DOUBLE arrow — the only signal that requires action

The only label that requires action. It fires once, on the 10:30 ET candle at the earliest, never before. It contains three lines of text:

- **Line 1:** `` `▲ ENTER` `` (bull) or `` `▼ ENTER` `` (bear)
- **Line 2:** `` `BULL PUT SPREAD` `` or `` `BEAR CALL SPREAD` ``
- **Line 3:** `` `Short: XXXX / Long: YYYY` `` — the exact two strike prices for your order

Reading our example: if the label says `` `▲ ENTER` `` / `` `BULL PUT SPREAD` `` / `` `Short: 5200 / Long: 5195` ``, this means: sell the 5200 put, buy the 5195 put, same expiry (today).

## Section 11 — The green PT line

### The green dashed line — PT (short strike level)

After DOUBLE fires, a **green dashed horizontal line** appears at the **short strike** level and extends to 15:50 ET.

This green line is not your profit target in dollars. Your profit target in dollars is +$50, and you hit that by buying the spread back at $0.50, not by price touching this line.

For a bull put spread at 5200/5195, the green line sits at 5200. As long as SPX stays **above** this line, the spread is decaying in your favour. If SPX crosses **down** through it, your short leg is starting to go in the money. For a bear call spread, the green line is at the short call strike — SPX must stay **below** it.

## Section 12 — The red SL line

### The red dashed line — SL (long strike level)

A **red dashed horizontal line** at the **long strike**, extending to 15:50 ET. For a bull put spread at 5200/5195, the red line sits at 5195. This is the blow-up level. If SPX falls to 5195, the spread is at or near maximum loss. You should never see this because your $2.00 stop exits long before price reaches the red line. For a bear call spread, the red line is at the long call strike.

## Section 13 — SKIP: WITCHING

### `` `⛔ SKIP: WITCHING` `` — stay out

An orange label that appears at the session open on triple or quadruple witching days — four Fridays per year (March, June, September, December). Win rate on these days drops to around 58%. **Action: do not trade today, regardless of what any other part of the indicator shows.** Close TradingView. Do something else.

## Section 14 — CAUTION: OPEX

### `` `⚠ CAUTION: OPEX` `` — extra care

A yellow label on monthly options expiry Fridays that are not witching days. Not a skip day, but volatility can be unpredictable. **Action: if DOUBLE fires, you may trade — but be extra strict on your stop, and do not chase a re-entry if stopped.**

## Section 15 — HARD EXIT

### `` `⚠ HARD EXIT` `` — close immediately

A red label reading `` `⚠ HARD EXIT / ORB60 OPPOSE` ``. Fires when the system detects the trend has reversed against your open trade. **Action: immediately switch to TastyTrade and close the position at market price, no matter what price is showing.** Do not hope for a bounce. Do not wait for the time exit. Positions that get a HARD EXIT signal and are held usually end at maximum loss.

## Section 16 — TIME EXIT

### `` `⏰ TIME EXIT` `` — close at 15:30

Appears at 15:30 ET if you have a DOUBLE trade still open. Text: `` `⏰ TIME EXIT / Close now` ``. **Action: close the spread manually on TastyTrade.** Reason: 0DTE options can swing wildly in the last 30 minutes. Locking in whatever you have is safer than gambling on the close.

## Section 17 — FOMC background

### Yellow background — FOMC day

On Federal Reserve announcement days, the chart background turns pale yellow from 09:30 to 16:00 ET. FOMC days are the best day of the year for this strategy. If DOUBLE fires on an FOMC day, that is your best possible setup. Trade it with normal size, normal rules.

## Section 18 — The status panel

### The status panel — your dashboard

The panel sits in the bottom-right corner and updates on every bar close. It shows the current state of the strategy in real time.

#### Row 0 — FOMC flag

Shows `` `⚠ FOMC DAY` `` in yellow on FOMC days. Empty and invisible on all other days. A quick-glance duplicate of the yellow background.

#### Row 1 — PDT Counter

Shows `X/3` where X is what you typed into the settings this morning. Three colours:
- **Green (0/3 or 1/3):** safe to trade today.
- **Amber (2/3):** this is your last allowed trade before the 5-business-day window resets. Only take the trade if DOUBLE fires on an A+ or A quality day.
- **Red (3/3):** **STOP. Do not place any day trade today, no matter what DOUBLE says.** No more than 3 day trades in any rolling 5 business days. A 4th trade triggers a 90-day freeze on day trading.

#### Row 2 — Entry Window

Counts down minutes until 12:00 noon ET. Before 09:30 shows `Pre-market`. After 12:00 shows `CLOSED`. If `CLOSED` appears and no DOUBLE has fired, there is no trade today.

#### Row 3 — Direction

`WAIT` until ORB20 breaks. Then flips to `BULL` or `BEAR`. Tells you which spread type you will use if DOUBLE fires.

#### Row 4 — Stacking

Shows the current tier: `FLAT` → `HALF` → `NORMAL` → `PLUS` or `DOUBLE` → `EXITED`. Jonny only cares when it reads `DOUBLE`.

#### Row 5 — DOUBLE Status

Four possible values:
- `WAITING` — still building, be patient
- `FIRED ✓` — DOUBLE just fired, check the arrow and place the trade
- `NOT TODAY` — either the pattern broke, or it reached PLUS (partial alignment) instead of DOUBLE. Either way: no trade today
- `EXITED` — the system flagged a HARD EXIT, close any open position immediately

#### Row 6 — Trade

Shows the exact spread shorthand. `BPS 5200/5195` means Bull Put Spread, short 5200, long 5195. `BCS 5200/5205` means Bear Call Spread, short 5200, long 5205. Shows `—` before DOUBLE fires.

#### Row 7 — Quality

A quality badge assigned when DOUBLE fires:
- `A+` — best possible day (e.g. FOMC Thursday). Trade with confidence.
- `A` — good day (e.g. normal Thursday/Friday). Trade normally.
- `B` — average day. Trade, but expect average results.
- `C` — sub-average day (e.g. Monday after a bad week). Consider skipping, or be extra strict on your stop.
- `—` — DOUBLE has not fired yet.

#### Row 8 — ORB20 Range

How wide the opening 20-minute range was in SPX points. Under 15 points = tight opening (often precedes clean trends). Over 40 points = wide and noisy.

#### Row 9 — Expansion

How much the range has grown since 09:50. Green if ≥1.5× — genuine trending day. Amber if under 1.5× — the market may have stalled.

#### Row 10 — ORB/ATR

The ratio of ORB20 range to current ATR(14). Three colours:
- **Green (< 0.20):** tight opening range. The day has room to trend. Best conditions for a clean breakout.
- **Amber (0.20–0.40):** normal opening range relative to volatility.
- **Red (> 0.40):** the opening range already consumed a large share of expected volatility. Lower probability of a clean continuation trend.

This row is context only. It is never a reason to skip a valid DOUBLE signal.

This ratio appears only after ORB20 locks at 09:50. Shows `—` before that.

## Section 19 — Live session walkthrough

### A day on the chart — minute by minute

- **09:29 ET.** Panel shows PDT `0/3` green, Entry Window `Pre-market`, Direction `WAIT`. Nothing to do.
- **09:30 ET.** US market opens. SPX prints around 5200. Entry Window begins counting down. Stacking: `FLAT`.
- **09:30–09:50 ET.** The translucent blue ORB20 box starts drawing, growing with each 5-minute candle. By 09:50 it spans low 5185 to high 5215.
- **09:50 ET.** Box locks. The dashed blue midpoint line appears at 5200. Two solid blue lines extend from 5215 and 5185 to the right. The green zone (5209–5215) and red zone (5185–5191) shade in.
- **09:50 ET continued.** The 09:45 candle closed at 5212 — inside the green zone. Price breaks above 5215 on the next candle. Label `HALF` appears. Direction flips to `BULL`. Stacking: `HALF`.
- **10:00 ET.** `NORMAL` label appears. Internal ORB30 confirmation fired. Stacking: `NORMAL`. DOUBLE Status still `WAITING`.
- **10:30 ET.** **`DOUBLE` fires.** A large up-arrow label appears: `` `▲ ENTER / BULL PUT SPREAD / Short: 5200 / Long: 5195` ``. A green dashed line appears at 5200, a red dashed line at 5195, both extending to 15:50. Panel: Stacking `DOUBLE`, DOUBLE Status `FIRED ✓`, Trade `BPS 5200/5195`, Quality `A`.
- **10:31 ET.** Switch to TastyTrade. Sell the 5200 put, buy the 5195 put, expiry today, limit order at $1.00 credit. Order fills. Immediately place a GTC limit to buy the spread back at $0.50. Set a price alert at $2.00 debit.
- **11:00–15:00 ET.** SPX holds above 5200. The spread decays. At some point the GTC buyback fills at $0.50. **Net profit: +$50. Position flat. Done for the day.**
- **Alternative ending.** If the GTC never filled by 15:30: the `` `⏰ TIME EXIT / Close now` `` label appears. Close the spread manually at whatever mid price is showing. If the spread is at $0.40, you keep $60. If $0.70, you keep $30. Either way, flat before 15:31.

## Section 20 — Common mistakes

### Common mistakes — read this carefully

1. **Entering on HALF, NORMAL, or PLUS.** Only DOUBLE is a trade signal.
2. **Ignoring a `` `⛔ SKIP: WITCHING` `` label.** Four days a year — just skip, no matter how good it looks.
3. **Forgetting to update the PDT counter each morning.** The panel will say `0/3` when you are actually at `2/3`.
4. **Trading when PDT shows `3/3` red.** A fourth day trade triggers a 90-day freeze on your account.
5. **Using a stop-loss order on the spread.** 0DTE spreads have wide bid/ask — a stop order fires on a momentary spike and dumps you out at the worst price. Use a price alert and close manually.
6. **Ignoring a `` `⚠ HARD EXIT` `` label.** Positions held through a HARD EXIT usually finish at maximum loss.
7. **Not closing at 15:30 `` `⏰ TIME EXIT` ``.** The last 30 minutes of 0DTE can erase a winning position in two candles.
