# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11+ paper-trading bot for SPX 0DTE strategies. Core runtime code lives in `tasty0dte/`: `main.py` schedules trade cycles, `strategy.py` selects option legs, `monitor.py` handles exits, and `logger.py` writes CSV records. Root modules with the same names are compatibility wrappers for existing scripts and tests. Strategy modules include `tasty0dte/premium_popper.py`, `tasty0dte/jade_lizard.py`, and the packaged ORB system in `orb_stacking/`.

Tests live in `tests/`, with ORB package tests in `orb_stacking/tests/`. Manual probes and one-off operational helpers live in `tools/`; performance review scripts live in `analysis/`. The read-only Flask dashboard is under `dashboard/`; supporting docs live in `docs/` and `tastytrade-docs/`.

## Build, Test, and Development Commands

Set up the environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run the bot in the foreground:

```bash
./run_autotrader.sh
```

Manage the background macOS helper:

```bash
./start.sh
./status.sh
./stop.sh
```

Run tests and syntax checks:

```bash
venv/bin/python -m unittest discover -v
venv/bin/python -m py_compile main.py strategy.py monitor.py logger.py tasty0dte/*.py tools/*.py analysis/*.py
```

Run the dashboard locally:

```bash
python dashboard/app.py
```

Open `http://127.0.0.1:5050`.

## Coding Style & Naming Conventions

Use standard Python style: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and uppercase names for constants. Keep modules script-friendly; this repository is not yet packaged as an installable library. Prefer explicit inputs over hidden global state around market data, account state, and time windows.

No formatter or linter config is currently committed. Match nearby code style and avoid broad formatting-only diffs.

## Testing Guidelines

Use `unittest`; files should be named `test_*.py` and test methods should start with `test_`. Put general strategy, monitor, and path tests in `tests/`; keep ORB package tests in `orb_stacking/tests/`. Add focused coverage for strategy selection, exits, time handling, and CSV mutations before changing trading behavior.

## Commit & Pull Request Guidelines

Git history uses concise Conventional Commit prefixes such as `feat:`, `fix:`, `chore:`, and `docs:`. Follow that style, for example `fix: correct ORB exit threshold`.

Pull requests should describe behavior changes, list test commands run, and call out impact on logs, cron scripts, `.env` variables, or dashboard views. Include screenshots for dashboard UI changes and link related issues or research notes.

## Security & Configuration Tips

Do not commit real credentials, account IDs, refresh tokens, or webhook URLs. Use `.env.example` for configuration shape and keep `.env` local. Treat `data/paper_trades.csv`, `runtime/`, screenshots, and analysis outputs as operational artifacts; avoid changing them unless the task explicitly requires it.
