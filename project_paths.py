"""Central filesystem paths for the 0DTE trading project."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


# One explicit private root controls records, captures, state, and logs.
# Per-file variables below remain available for exceptional local overrides.
PRIVATE_DATA_ROOT = _path_from_env(
    "TASTY_PRIVATE_DATA_ROOT",
    Path.home() / "Private/ProjectsData/trading/tasty0dte-ironcondor",
)
DATA_DIR = PRIVATE_DATA_ROOT / "data"
RUNTIME_DIR = PRIVATE_DATA_ROOT / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
STATE_DIR = RUNTIME_DIR / "state"
ARTIFACTS_DIR = PRIVATE_DATA_ROOT / "artifacts"
REPORTS_DIR = PRIVATE_DATA_ROOT / "reports"
BACKTEST_DATA_DIR = DATA_DIR / "v1_backtest"
CHAIN_CAPTURE_DIR = DATA_DIR / "chain_capture"
GENERAL_0DTE_DIR = DATA_DIR / "spxw_0dte_cbbo_1m"


PAPER_TRADES_CSV = _path_from_env(
    "TASTY_PAPER_TRADES_CSV",
    DATA_DIR / "paper_trades.csv",
)
SKIP_EVENTS_CSV = _path_from_env(
    "TASTY_SKIP_EVENTS_CSV",
    DATA_DIR / "skip_events.csv",
)
SPX_CACHE_JSON = _path_from_env(
    "TASTY_SPX_CACHE_JSON",
    STATE_DIR / ".spx_cache.json",
)

BOT_PID = _path_from_env("TASTY_BOT_PID", STATE_DIR / "bot.pid")
CRON_LOG = _path_from_env("TASTY_CRON_LOG", LOG_DIR / "cron.log")
TRADE_LOG = _path_from_env("TASTY_TRADE_LOG", LOG_DIR / "trade.log")
STDOUT_LOG = _path_from_env("TASTY_STDOUT_LOG", LOG_DIR / "stdout.log")
STDERR_LOG = _path_from_env("TASTY_STDERR_LOG", LOG_DIR / "stderr.log")

PUBLIC_SITE_DIR = _path_from_env("TASTY_PUBLIC_SITE_DIR", PROJECT_ROOT / "public_site")
DOCS_DIR = _path_from_env("TASTY_DOCS_DIR", PROJECT_ROOT / "docs")
