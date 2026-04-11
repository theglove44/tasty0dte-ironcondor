# ORB Stacking Indicator — User Guide

## What It Is

The ORB Stacking indicator is a TradingView companion tool for the ORB Stacking options strategy on SPX. It visualises the three Opening Range Breakout levels (ORB20, ORB30, ORB60) on the chart and runs the full strategy logic in real time — displaying each tier signal as it fires, and providing a live status panel so you can follow the session state at a glance without reading logs.

It does not place orders. It is a read-only visual layer that mirrors exactly what the live bot computes.

---

## Requirements

- **Symbol:** SPX (or SPXW)
- **Timeframe:** 5-minute bars only. The indicator will throw a runtime error on any other timeframe.
- **Session:** US Regular Trading Hours. All logic is anchored to ET (Eastern Time).

---

## Setup

1. Open a 5-minute SPX chart in TradingView.
2. Open the Pine Script editor (bottom toolbar).
3. Paste the full contents of `orbstack_indi` into the editor.
4. Click **Add to chart**.
5. The indicator loads with sensible defaults. All settings can be adjusted via the indicator's settings panel (gear icon).

---

## The Strategy in Brief

The ORB Stacking strategy builds a position in tiers as the market confirms a directional move off the opening range.

**Three opening ranges are measured:**

| Range | Window | Lock bar closes at |
|---|---|---|
| ORB20 | 09:30 – 09:50 ET | 09:50 ET |
| ORB30 | 09:30 – 10:00 ET | 10:00 ET |
| ORB60 | 09:30 – 10:30 ET | 10:30 ET |

A **breakout** is when price closes *outside* a range for the first time after that range locks. The direction of the ORB20 breakout (bull or bear) sets the session direction. ORB30 and ORB60 either confirm that direction or oppose it.

**Four entry tiers build up as confirmations arrive:**

| Tier | Trigger | What it means |
|---|---|---|
| HALF | ORB20 breakout | Initial position — range has broken, direction established |
| NORMAL | ORB30 confirms | Momentum confirmed at the 30-minute range |
| PLUS | ORB60 confirms | Full trend confirmation — standard full position |
| DOUBLE | ORB60 confirms + all 3 closes aligned | Highest-conviction setup — double the position |

**Two exit signals:**

| Signal | Trigger | What it means |
|---|---|---|
| ORB30 OPPOSES | ORB30 breaks opposite to ORB20 direction | Warning — trend weakening, no new entries |
| HARD EXIT | ORB60 breaks opposite to ORB20 direction | All open positions force-closed immediately |

Entry window closes at **12:00 ET noon**. If ORB20 has not broken by then, the session is abandoned.

---

## Chart Visuals

### ORB20 Box

A filled blue box drawn from the 09:30 opening bar and extending rightward to **11:30 ET** (market open +2 hours).

- **Height:** the exact high-to-low range of the first 20 minutes of trading (four 5-minute bars)
- **Top 20% zone:** shaded green — price closing here on the ORB20 lock bar is bull-aligned, a quality signal
- **Bottom 20% zone:** shaded red — price closing here is bear-aligned
- **Why it extends to 11:30:** the ORB20 range remains the relevant reference zone well after it locks. Visualising it through the morning makes it easy to see where price is relative to the range as ORB30 and ORB60 confirmations arrive.

The main box colour is configurable (default: blue, 80% transparent). The green/red alignment zones use the bull/bear signal colours from the colour settings.

### ORB30 Lines

Two horizontal lines (high and low) spanning from the opening bar rightward. No fill — only the boundary lines are shown. Toggled by **Show ORB30 range box** in settings (the label is legacy; it now controls lines only).

Default colour: green.

### ORB60 Lines

Same as ORB30 but for the 60-minute range. Default colour: orange.

### ORB20 H/L Extension Lines

After the ORB20 locks (09:50 ET), the ORB20 high and low are extended as separate lines running to 15:55 ET. These make it easy to see whether price is respecting the ORB20 level as the day progresses. Toggled by **Extend ORB H/L after lock**.

### ORB20 Midpoint Line

A lighter blue dashed line at the exact midpoint of the ORB20 range, extended from 09:50 through 15:55 ET. The midpoint is the short strike used by the live strategy — it is the most important single price level on the chart. Toggled by **Show ORB20 midpoint line**.

### Signal Labels

Labels appear directly on the chart bar where each tier fires. They are positioned above price for bear signals and below price for bull signals.

| Label | Colour | What fired |
|---|---|---|
| `HALF` | Bull green / Bear red | ORB20 breakout — session direction set |
| `NORMAL` | Same as direction | ORB30 confirmed |
| `PLUS` | Same as direction | ORB60 confirmed, standard setup |
| `DOUBLE` | Purple | ORB60 confirmed, all 3 closes aligned — highest conviction |
| `ORB30 OPPOSES` | Orange | ORB30 broke against direction — warning |
| `HARD EXIT` | Dark red | ORB60 broke against direction — force close |
| `NO BREAKOUT` | Grey | Noon reached without ORB20 break — session abandoned |

### Background Flashes

- **Yellow wash:** FOMC day. The background turns pale yellow during market hours (09:30–16:00 ET) on any day with a scheduled Federal Reserve announcement.
- **Orange flash:** Single-bar orange wash when ORB30 opposes. Draws attention to the bar where the warning fires.
- **Red flash:** Single-bar dark red wash when ORB60 hard exit fires.

---

## The Status Panel

The panel sits in the **bottom-right corner** of the chart and updates on every new bar close. It shows the current state of the strategy engine. It only appears when **Show stacking signals** is enabled and the current bar is within the history lookback window.

| Row | Label | What it shows |
|---|---|---|
| 0 | *(FOMC flag)* | `⚠ FOMC DAY` on a yellow background — only visible on FOMC days, invisible otherwise |
| 1 | Entry Window | Minutes remaining until the 12:00 ET entry cutoff. Shows `Pre-market` before 09:30, a green countdown during the session, and `CLOSED` (red) after noon or once the session times out |
| 2 | Direction | `BULL`, `BEAR`, or `WAIT`. Set by the ORB20 breakout and does not change for the rest of the session |
| 3 | Stacking | Current tier: `FLAT` → `HALF` → `NORMAL` → `PLUS` or `DOUBLE`. Shows `EXITED` if ORB60 opposed |
| 4 | Next | What needs to happen to advance to the next tier. Updates as tiers fire. Shows `Complete` at PLUS/DOUBLE, `Exited` after a hard exit |
| 5 | ORB20 Break | `BULL 94%` or `BEAR 12%` — direction plus the lock-bar close percentile within the ORB20 range. Higher % = stronger bull close; lower % = stronger bear close. Shows `WAIT` before the break, `NO BREAKOUT` at noon timeout |
| 6 | ORB30 Confirm | `CONFIRMED 88%` or `OPPOSED 15%` — confirmation status plus the ORB30 lock-bar close percentile. Shows `WAIT` if ORB20 has broken but ORB30 hasn't locked yet |
| 7 | ORB60 Confirm | `PLUS 91%` or `DOUBLE 95%` or `HARD EXIT 8%` — confirmation status plus percentile. The tier name is shown on confirmation so you know immediately whether it qualifies as PLUS or DOUBLE |
| 8 | Close Align | `X/3` — how many of the three ORB close percentiles are directionally aligned (≥80% for bull, ≤20% for bear). 3/3 = DOUBLE territory; 2/3 or lower = PLUS |
| 9 | ORB20 Range | The ORB20 high-to-low range in points. Gives immediate context for whether the day is tight or wide. A 10pt range and a 50pt range produce very different option credits |
| 10 | Expansion | ORB60 range ÷ ORB20 range. Shows how much the range expanded as the morning progressed. ≥1.5× (green) indicates a genuine trending session; below 1.5× (orange) suggests the market stalled after the opening |

### Panel Colour Coding

| Colour | Meaning |
|---|---|
| Green | Active, confirmed, positive |
| Orange / amber | Warning, partial, oppose signal |
| Dark red | Hard exit, session ended adversely |
| Grey | Inactive, not yet triggered, waiting |
| Transparent | FOMC row on non-FOMC days (hidden) |

---

## Reading a Live Session

**Before 09:30 ET:** Panel shows `Pre-market` in the entry window row. No ranges or lines visible yet.

**09:30 – 09:50 ET:** The ORB20 box is being built bar by bar. No signals yet — the range is still accumulating. Panel Direction shows `WAIT`.

**09:50 ET (ORB20 locks):** The ORB20 box finalises its height. The green and red alignment zones appear. The `ORB20 Break` row shows the lock-bar close percentile. The indicator begins watching for the first post-lock close outside the range.

**09:50 – 10:00 ET:** Breakout window for ORB20. The moment a 5-minute bar closes above the high or below the low, the `HALF` label fires on the chart and the panel Direction and Stacking rows update.

**10:00 ET (ORB30 locks):** If ORB20 has broken, the indicator begins watching ORB30 for confirmation or opposition. `ORB30 Confirm` row shows the percentile.

**10:00 – 10:30 ET:** ORB30 confirmation window. `NORMAL` fires on confirm, `ORB30 OPPOSES` fires on oppose.

**10:30 ET (ORB60 locks):** ORB60 percentile fills in. Confirmation window opens.

**10:30 – 12:00 ET:** ORB60 confirmation window. `PLUS` or `DOUBLE` fires on confirm, `HARD EXIT` fires on oppose. Entry window countdown ticks down. The `Next` row will show `Complete` once PLUS or DOUBLE has fired.

**12:00 ET:** Entry window closes. `Entry Window` row turns red and shows `CLOSED`. The `NO BREAKOUT` label fires if ORB20 never broke.

---

## Settings Reference

### Display group

| Setting | Default | Description |
|---|---|---|
| Show ORB20 range box | On | Toggles the ORB20 filled box and green/red zones |
| Show ORB30 range box | On | Toggles the ORB30 H/L lines |
| Show ORB60 range box | On | Toggles the ORB60 H/L lines |
| Show ORB20 midpoint line | On | Toggles the midpoint (short strike) line |
| Extend ORB H/L after lock | On | Toggles ORB20 H/L extension lines after 09:50 |
| Show stacking signals | On | Toggles signal labels and the status panel |
| Highlight FOMC days | On | Toggles yellow background on FOMC days |
| History: calendar days to show | 7 | How many calendar days back to draw visuals. Increase to see more history; decrease for a cleaner chart on a single session |

### Colours group

All colours are fully configurable. The defaults are:

| Setting | Default | Used for |
|---|---|---|
| ORB20 | Blue 80% transparent | ORB20 box fill |
| ORB20 line | Blue solid | ORB20 H/L and extension lines |
| ORB30 | Green 80% transparent | *(legacy — no longer used for fill)* |
| ORB30 line | Green solid | ORB30 H/L lines |
| ORB60 | Orange 80% transparent | *(legacy — no longer used for fill)* |
| ORB60 line | Orange solid | ORB60 H/L lines |
| Bull signal | Bright green | Bull labels and panel active cells |
| Bear signal | Bright red | Bear labels and alignment zone |
| ORB30 oppose | Amber | ORB30 oppose label and panel warning cells |
| ORB60 hard exit | Dark red | Hard exit label, panel exit cells, background flash |
| DOUBLE tier | Purple | DOUBLE tier label |
| ORB20 midpoint | Light blue 50% | Midpoint line fill |
| ORB20 mid line | Light blue solid | Midpoint line colour |

---

## Notes and Limitations

- The indicator enforces a 5-minute timeframe. Adding it to any other timeframe will produce a runtime error by design.
- All timestamps are ET (Eastern Time). The chart timezone display does not affect the indicator's internal logic.
- The status panel only updates on `barstate.islast` — it reflects the current state as of the most recently closed bar, not intrabar.
- Historical days within the lookback window replay the full strategy logic, so signal labels and panel state will appear correctly on past sessions.
- The FOMC dates array covers 2025–2026. Dates for 2027 will need to be added to the script before December 2026.
- The expansion ratio threshold for the green/orange colour in the panel (≥1.5×) is a visual cue only and does not affect strategy logic.
