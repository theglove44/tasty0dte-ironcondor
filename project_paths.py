"""Central filesystem paths for the 0DTE trading project."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _relocated_path(name: str, target: Path, legacy: Path) -> Path:
    """Resolve a relocated runtime path while preserving old-root fallback."""
    value = os.getenv(name)
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path
    if target.exists() or not legacy.exists():
        return target
    return legacy


# One explicit private root controls records, captures, state, and logs. With
# no setting, the historical project-relative layout remains the fallback.
PRIVATE_DATA_ROOT = _path_from_env("TASTY_PRIVATE_DATA_ROOT", PROJECT_ROOT)
DATA_DIR = PRIVATE_DATA_ROOT / "data"
RUNTIME_DIR = PRIVATE_DATA_ROOT / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
STATE_DIR = RUNTIME_DIR / "state"
ARTIFACTS_DIR = PRIVATE_DATA_ROOT / "artifacts"
REPORTS_DIR = PRIVATE_DATA_ROOT / "reports"
BACKTEST_DATA_DIR = DATA_DIR / "v1_backtest"
CHAIN_CAPTURE_DIR = DATA_DIR / "chain_capture"


PAPER_TRADES_CSV = _relocated_path(
    "TASTY_PAPER_TRADES_CSV",
    DATA_DIR / "paper_trades.csv",
    PROJECT_ROOT / "data" / "paper_trades.csv",
)
SKIP_EVENTS_CSV = _relocated_path(
    "TASTY_SKIP_EVENTS_CSV",
    DATA_DIR / "skip_events.csv",
    PROJECT_ROOT / "data" / "skip_events.csv",
)
SPX_CACHE_JSON = _relocated_path(
    "TASTY_SPX_CACHE_JSON",
    STATE_DIR / ".spx_cache.json",
    PROJECT_ROOT / ".spx_cache.json",
)

BOT_PID = _relocated_path("TASTY_BOT_PID", STATE_DIR / "bot.pid", PROJECT_ROOT / "runtime" / "state" / "bot.pid")
CRON_LOG = _relocated_path("TASTY_CRON_LOG", LOG_DIR / "cron.log", PROJECT_ROOT / "runtime" / "logs" / "cron.log")
TRADE_LOG = _relocated_path("TASTY_TRADE_LOG", LOG_DIR / "trade.log", PROJECT_ROOT / "runtime" / "logs" / "trade.log")
STDOUT_LOG = _relocated_path("TASTY_STDOUT_LOG", LOG_DIR / "stdout.log", PROJECT_ROOT / "runtime" / "logs" / "stdout.log")
STDERR_LOG = _relocated_path("TASTY_STDERR_LOG", LOG_DIR / "stderr.log", PROJECT_ROOT / "runtime" / "logs" / "stderr.log")

PUBLIC_SITE_DIR = _path_from_env("TASTY_PUBLIC_SITE_DIR", PROJECT_ROOT / "public_site")
DOCS_DIR = _path_from_env("TASTY_DOCS_DIR", PROJECT_ROOT / "docs")
