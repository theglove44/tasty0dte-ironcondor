# tasty0dte-ironcondor

## Purpose and boundaries

- This is a Python paper-trading bot for scheduled SPX option strategies. It must never place live orders.
- Keep Tastytrade credentials in the local `.env` only. Treat the paper ledger, captures, runtime state, logs, and reports as private records.
- `project_paths.py` is the source of truth for filesystem locations. By default these private records live under `TASTY_PRIVATE_DATA_ROOT` (see `.env.example`); do not hardcode repository-local data or runtime paths.

## Read first

- Read `AI_GUIDE.md` before non-trivial work. It documents the architecture, active strategy configuration, validation guards, CSV schema, DST handling, log hierarchy, and operational hazards.
- Read `docs/PROJECT_GUIDE.md` for the plain-English system map and `docs/ARCHITECTURE.md` for component boundaries and data flow.
- Use `README.md` for setup and user-facing run instructions, and `analysis/README.md` for analysis workflows.

## Key code areas

- `tasty0dte/main.py` — scheduler, strategy configuration, and the single Tastytrade session.
- `tasty0dte/strategy.py` — option-chain/leg selection, pricing, and credit sanity checks.
- `tasty0dte/monitor.py` — quote monitoring, exits, and end-of-day settlement.
- `tasty0dte/logger.py` — paper-trade CSV persistence; root modules with matching names are compatibility wrappers.
- `tests/` and `orb_stacking/tests/` — `unittest` coverage for the bot and the separately tested ORB package.

## Verification and time-sensitive changes

- Before handover, run `venv/bin/python -m unittest discover -v`. Do not run bot tests while the live bot is running because tests share its log handler.
- For syntax-only verification, run `venv/bin/python -m py_compile main.py strategy.py monitor.py logger.py tasty0dte/*.py tools/*.py analysis/*.py`.
- All scheduling uses `Europe/London`. When changing a schedule or time window, audit US/UK daylight-saving changes and update `target_times` and matching `STRATEGY_CONFIGS.allowed_times` together in `tasty0dte/main.py`; also check cron/helper scripts and ORB time utilities.
