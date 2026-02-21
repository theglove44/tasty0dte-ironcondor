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

- Only trade during market hours (14:30-21:00 UK)
- Max 3 day trades per 5 days (PDT rule)
- Use paper_trades.csv for all tracking
- Credit-only strategies (no debit spreads)

## Key Files

- `main.py` — Entry point, CLI args
- `strategy.py` — Entry logic, strike selection
- `monitor.py` — Position monitoring, profit targets, EOD
- `paper_trades.csv` — Trade history
- `.spx_cache.json` — SPX price cache for EOD settlement

## Memory

- Update `memory/projects/0dte-bot.md` with lessons
- Document API issues, timeouts, rate limits
- Track strategy performance (win rate, P/L by strategy)
- Note gap filter decisions and outcomes
