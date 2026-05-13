# CLAUDE.md — 0DTE Iron Condor Bot

## Workflow

### Plan Mode Default
- Enter plan mode for new strategies, entry/exit rules, significant changes
- Write specs before implementing
- If something breaks, stop and re-plan

### Self-Improvement Loop
- After any bug or issue: update `memory/projects/0dte-bot.md`
- Document what went wrong, the fix, and prevention steps
- Review lessons before trading sessions

### Verification Before Done
- Never deploy without testing
- Verify P/L calculations match actual outcomes
- Check EOD settlement works

### Demand Elegance
- If code feels hacky, find the cleaner solution
- Simple > Complex for reliability

## Task Management

1. **Plan**: What's the change?
2. **Implement**: Build it
3. **Test**: Run it, check logs
4. **Document**: Update memory with learnings

## Core Principles

- **Simplicity First**: Bot reliability > features
- **Never Break Running System**: Test before deploying
- **Log Everything**: Trade decisions, errors, P/L
- **Cron-Based**: Start/stop at scheduled times, not aggressive guards

## Trading Rules

- Only trade during market hours (13:30-20:00 UK while US DST active, revert to 14:30-21:00 when UK clocks change)
- Max 3 day trades per 5 days (PDT rule)
- Use paper_trades.csv for all tracking
- Credit-only strategies (no debit spreads)

## DST / Time Change Checklist

When updating times for DST shifts, audit **every** hardcoded time in the codebase — not just the obvious entry points. Use:
1. `grep -rn "time(" *.py` — all `time()` objects (especially `STRATEGY_CONFIGS.allowed_times` vs `target_times`)
2. `grep -rn "hour ==" *.py` — all hour comparisons (e.g. Premium Popper launch)
3. Crontab (`crontab -l`), shell scripts, dashboard configs
4. Cross-reference: if one time moves, all corresponding times must move together
5. **Lesson (2026-03-30)**: `target_times` was updated but `allowed_times` in `STRATEGY_CONFIGS` was missed — silently skipped all Iron Fly + Dynamic trades for a full day

## Key Files

- `main.py` — Entry point, CLI args
- `strategy.py` — Entry logic, strike selection
- `monitor.py` — Position monitoring, profit targets, EOD
- `paper_trades.csv` — Trade history
- `.spx_cache.json` — SPX price cache for EOD settlement

## Analysis Scripts

The `analysis/` directory contains reusable scripts for working with `paper_trades.csv` and the public research site at `public_site/`. **Use these instead of re-implementing analysis logic inline.** See `analysis/README.md` for full docs.

- `analysis/common.py` — shared filters, DST normalisation, stat helpers (`load_trades`, `streaks`, `drawdown_episodes`, etc.). Import from here.
- `analysis/regenerate_site_data.py` — rebuild `public_site/data.js`. Run after any CSV change.
- `analysis/dedup_trades.py` — find and remove duplicate trade rows (Discord double-fires, etc.).
- `analysis/strategy_metrics.py` — deep per-strategy metrics: streaks, drawdowns, IV regime, day-move sensitivity, exit clustering, autocorrelation.
- `analysis/exit_analysis.py` — exit-reason breakdown (profit-target / time-stop / settled).

Default filters applied by every script: closed-only trades, private strategies excluded (`Premium Popper`, `ORB-STACK-*`, `JadeLizard_*`), anomalous-credit outliers excluded (Credit Collected > $30). Override with `--include-private` / `--keep-outliers` for ad-hoc personal analysis.

Typical weekly update flow:
```bash
python3 analysis/dedup_trades.py --apply        # if any duplicates
python3 analysis/regenerate_site_data.py        # rebuild data.js
# then drag public_site/ to Cloudflare Pages
```

## Log Hierarchy (READ THIS BEFORE DIAGNOSING)

**Before making any claim about bot health, read sources in this order and stop at the first one that answers the question. Do not guess from log filenames — most of them are noisy or unrelated to the trading bot.**

### 1. Is the bot running?
```
ps aux | grep "main.py" | grep -v grep
```
PID + start time is ground truth. A running process means the bot is alive regardless of what any log says.

### 2. What is it doing right now? (trusted, bot-owned)
- **`stdout.log`** — live monitor loop; every ~16s prints open trades, current debit, P/L, target. If updating, the bot is streaming live quotes and healthy.
- **`trade.log`** — structured INFO log from the bot itself: trade entries/exits, IV Rank, chain fetches, Greeks subscriptions, profit-target closes. **This is the authoritative bot log.** If trading logic broke, it's here.

### 3. Did anything break today?
```
grep "^YYYY-MM-DD" trade.log | grep -iE "error|warning|exception|traceback|failed"
```
Always scope grep to today's date. Empty result = clean session.

### 4. Persistent state
- **`paper_trades.csv`** — source of truth for all trades (open + closed), P/L, strikes, credits
- **`.spx_cache.json`** — last-known SPX spot (only used as EOD fallback per the 2026-03-28 fix)

### 5. Logs to IGNORE or heavily discount
These files look scary but are not the trading bot. Do not cite errors from them without first checking their mtime and purpose.

- **`guard_stderr.log`** — raw unstamped curl errors from `market_session_guard.sh`, a 5-min cron watchdog that polls tastytrade's `/market-time` endpoint. **No timestamps**, so stale errors from days/weeks ago look "current". Not the bot. Transient Mac DNS/network hiccups accumulate here and are harmless — the guard retries on the next tick.
- **`guard_stdout.log`** — the watchdog's heartbeat. Use THIS (not guard_stderr) to verify the guard sees the market as Open. Has timestamps.
- **`stderr.log`** — historically duplicates trade.log INFO plus old warnings. Noisy, partially unstamped. Prefer `trade.log`.
- **`cron.log`** — cron wrapper output, not bot logic.

**Rule of thumb: if a log has no timestamps, treat it as untrusted context, not evidence.**

### 6. Architecture layers (what talks to what)
- `main.py` → schedules strategies, owns the SDK Session
- `strategy.py` → fetches chain/Greeks/SPX spot, picks legs
- `monitor.py` → the live-quote streaming loop that writes to `stdout.log`
- `market_session_guard.sh` → independent shell watchdog, uses `curl` (NOT the bot's SDK session). Its failures do not affect the running bot.

The bot uses the tastytrade Python SDK over a persistent authenticated HTTPS session — completely independent of the watchdog's curl polling. A curl timeout in the guard does not mean the bot lost its feed.

## Memory

- Update `memory/projects/0dte-bot.md` with lessons
- Document API issues, timeouts, rate limits
- Track strategy performance (win rate, P/L by strategy)
- Note gap filter decisions and outcomes
