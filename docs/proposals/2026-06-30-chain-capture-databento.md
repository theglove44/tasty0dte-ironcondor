# SPX Option-Chain Capture for Backtesting — Databento Daily Pull

**Status:** Spec / proposal
**Date:** 2026-06-30
**Author:** research session
**Supersedes:** nothing — extends the proven pattern in `tools/fetch_v1_backtest_data.py`

---

## 1. Goal

Build an ongoing, gap-free corpus of SPX option-chain quotes (bid/ask/mid)
across multiple expirations, so future strategies can be backtested without
re-pulling data or relying on a fragile real-time daemon. Greeks/IV are derived
in a separate enrichment pass, not captured.

The corpus must be:

- **Authoritative** — real NBBO quotes, not mid-price reconstructions.
- **Gap-free** — any missing day is trivially backfillable from history.
- **Reusable** — same parquet schema and tooling as the existing V1 backtest.

---

## 2. Why a daily Databento *batch*, not a live capture

| Approach | Reliability | Cost | Verdict |
|---|---|---|---|
| **tastytrade self-capture (real-time daemon)** | Poor — every Mac sleep / crash / network blip = a permanent hole. Backtest data with silent gaps is worse than none. | Free (within rate limits) | ✗ Rejected |
| **Databento live feed** | Good, but needs a always-on subscriber process | Streaming cost + ops | ✗ Overkill |
| **Databento Historical, daily batch (T+1)** | **Excellent** — OPRA history is immutable and complete; any gap is one re-run away | Pay-per-pull, previewable before every charge | ✓ **Chosen** |

The decisive point: with the Historical API you can **backfill any past day at any
time**. A daily cron is just an optimisation to keep the corpus current — if it
misses a day, you re-run it. There is no live state to lose. This is the entire
reliability argument from the research discussion, made concrete.

---

## 3. Data source — what Databento gives (and doesn't)

- **Dataset:** `OPRA.PILLAR` (same as existing pulls).
- **Schema:** `cbbo-1m` — consolidated NBBO sampled at 1-minute. One row per
  symbol per minute when a quote exists. Workhorse for the chain corpus.
- **Optional `cbbo-1s`** — 1-second NBBO, **only for the specific legs a strategy
  trades** (not the whole chain). Availability floor is **2025-02** (confirmed: no
  2024 legs files exist). Use only for precise exit-fill modelling, as V1 already does.
- **Greeks / IV: NOT included.** `cbbo` schemas are pure quote data (bid/ask).
  This was established previously. Greeks must be **computed** (§7), not pulled.
- **Spot:** not pulled separately — the per-expiry forward is derived from
  put-call parity on the captured quotes (self-consistent, §7).
- **Availability lag:** OPRA historical data is generally available ~**T+1**.
  The cron pulls the *prior* trading day, not the current one.

---

## 4. Capture scope

### Expirations

`SPXW` only (PM-settled weeklies/dailies — the root all current strategies trade).
For each captured trading day **T**, target every `SPXW` expiry in **[T, T+14
calendar days]** — i.e. the next ~10 daily expiries. This covers:

- 0DTE — iron fly / iron condor research.
- 5 / 7 / 10 DTE — Jade Lizard variants.
- Headroom for any future short-DTE idea without re-pulling.

> AM-settled monthly `SPX` (third-Friday) is **out of scope** — no current
> strategy uses it. Easy to add later as a second root if needed.

### Strike band (tiered, centred on T's SPX close)

Because we pull T+1, the day's actual SPX close is known — centre precisely on it.

| DTE bucket | Half-band | Rationale |
|---|---|---|
| 0–2 DTE | **±3%** of spot | 0DTE only needs ATM ± expected move; wings are ±10 |
| 3–14 DTE | **±8%** of spot | Covers JL ~20-delta short put depth + short call, with margin (~2.7σ at 14DTE) |

At SPX 7500: ±3% ≈ ±225 pts (90 strikes/side), ±8% ≈ ±600 pts (240 strikes/side),
5-pt grid.

### Cadence

`cbbo-1m`, full regular session **09:31–16:00 ET**. (V1 used a narrow 09:55–13:10
window; the corpus wants the whole session for general reuse.)

---

## 5. Symbology & cost control

- Enumerate exact OSI symbols (reuse `osi()` from `fetch_v1_backtest_data.py`):
  `SPXW␠␠YYMMDD{C|P}NNNNNNNN` (two spaces, strike×1000, 8 digits).
- `stype_in="raw_symbol"`, as today. **Do not** use `parent` symbology — it pulls
  the entire chain (all expiries/strikes) and is uncontrollably expensive.
- **Every pull is cost-gated**: `client.metadata.get_cost(...)` runs first; the
  `--preview` / `--confirm` pattern from the existing tool is preserved verbatim.

### Volume scale (for intuition — not a price)

~4,500 contracts/day × up to 390 min ≈ **~1.5–1.8M rows/day** worst case (far
fewer in practice — illiquid strikes don't quote every minute). Parquet-compressed
this is on the order of tens of MB/day. **Actual $ is volume-based and must be read
from `get_cost` before committing** — see §9 calibration.

---

## 6. Storage layout & schema

One parquet per captured day, all expiries in the file (matches the existing
single-file-per-day convention):

```
data/chain_capture/{YYYY}/{YYYY-MM-DD}.parquet
```

Schema (superset of the V1 schema — adds expiry context for multi-DTE queries):

| column | type | notes |
|---|---|---|
| `symbol` | str | OSI, e.g. `SPXW  260705P07200000` |
| `expiry` | date | parsed from symbol |
| `dte` | int | `(expiry - capture_date).days` |
| `side` | str | `C` / `P` |
| `strike` | int | dollars |
| `bid` | float64 | from `bid_px_00` / 1e9 |
| `ask` | float64 | from `ask_px_00` / 1e9 |
| `mid` | float64 | `(bid+ask)/2` |
| `ts_et` | datetime[ns, ET] | minute timestamp |

`symbol/bid/ask/mid/ts_et` are byte-identical to the V1 schema, so existing
loaders keep working; `expiry/dte/side/strike` are pre-parsed for convenience.

---

## 7. Greeks / IV enrichment (separate pass)

Kept out of the capture so the raw corpus stays pure NBBO. A standalone
`tools/enrich_chain_greeks.py` reads a day's parquet and writes a sibling
`{date}_greeks.parquet`:

1. **Forward per expiry** via put-call parity on each minute's quotes
   (extends `_find_atm`'s logic to a full forward `F = K + C_mid − P_mid`,
   median across liquid pairs).
2. **Implied vol per option** by Black-Scholes inversion using `F`, `K`, `T`
   (year-fraction to PM settlement), `r` (constant or SOFR; parity-forward
   already bakes in carry+div so `r` only discounts).
3. **Greeks** (Δ, Γ, Θ, Vega) analytically from the same BS inputs.

Deterministic and reproducible from stored quotes → can be re-run/improved any
time without re-pulling data. Output columns: `iv, delta, gamma, theta, vega`.

---

## 8. Automation, idempotency, backfill

- **Cron** (next-morning, after OPRA T+1): pull the prior trading day.
  Reuse the `run_autotrader.sh` venv+caffeinate wrapper pattern.
- **Idempotent**: `--skip-existing` skips days already on disk (as today).
- **Backfill**: `--start/--end` re-pulls any historical range. A missed cron day
  is recovered by simply re-running — no live state, no data loss.
- **Holiday tolerance**: weekday enumeration includes the odd market holiday;
  those expiries return empty / zero-cost and are skipped naturally.
- **Manifest**: append one row per captured day to
  `data/chain_capture/_manifest.csv` (`date, expiries, rows, cost, pulled_at`)
  so gaps are auditable at a glance.

---

## 9. Cost calibration — do this FIRST

Do **not** commit to the full 0–14 DTE × ±8% scope blind. Calibrate against real $:

1. `--preview` a **single recent day** at the proposed scope → read `get_cost`.
2. If acceptable, `--confirm` that one day; inspect row counts and file size.
3. `--preview` a **one-week** backfill → extrapolate monthly/annual $.
4. Decide between:
   - **Tier A (lean):** only the expiries current strategies trade
     (0DTE + the 5/7/10-DTE targets) — cheapest, covers today's roster.
   - **Tier B (flexible):** all expiries 0–14 DTE — denser, future-proof.
5. Lock the scope, enable the cron.

Recommended: **start Tier A, widen to Tier B once the real per-day $ is known.**

---

## 10. Implementation plan

| Phase | Deliverable |
|---|---|
| 1 | `tools/capture_spx_chain.py` — multi-expiry `cbbo-1m` pull; reuses `osi()`, cost-gate, parquet writer; new `data/chain_capture/` layout + `expiry/dte/side/strike` columns + manifest |
| 2 | Calibration run (§9) — preview 1 day → 1 week; pick Tier A/B |
| 3 | `tools/enrich_chain_greeks.py` — parity-forward → BS IV/Greeks sidecar |
| 4 | Cron + `run_*` wrapper; `--skip-existing` daily pull of prior trading day |
| 5 | Loader helper in `analysis/` (or `tools/`) to read `chain_capture` by date/DTE/strike for backtests |

Phase 1 is a near-copy of the existing fetcher with the expiry loop and band
tiering added — low risk. No change to the live bot; this is purely additive,
runs as its own process with its own Databento client.

---

## 11. Open decisions (need a call before Phase 1)

1. **Tier A vs Tier B** to start — recommend A, widen after calibration.
2. **Session window** — full 09:31–16:00 ET (recommended) vs a narrower band to cut cost.
3. **`cbbo-1s` legs** — capture 1-second data for traded legs too (2025+ only),
   or rely on 1-minute for the corpus and pull 1s on demand per backtest?
4. **History backfill** — only capture *going forward*, or also backfill 0–14 DTE
   history to extend the corpus backwards (larger one-time cost)?
```
