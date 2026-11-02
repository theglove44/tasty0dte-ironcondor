"""Private runtime paths for this retained legacy worktree."""
from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
raw_root = os.environ.get("TASTY_PRIVATE_DATA_ROOT")
PRIVATE_DATA_ROOT = Path(raw_root).expanduser() if raw_root else PROJECT_ROOT
if not PRIVATE_DATA_ROOT.is_absolute():
    PRIVATE_DATA_ROOT = PROJECT_ROOT / PRIVATE_DATA_ROOT

PAPER_TRADES_CSV = PRIVATE_DATA_ROOT / "paper_trades.csv"
SKIP_EVENTS_CSV = PRIVATE_DATA_ROOT / "skip_events.csv"
SPX_CACHE_JSON = PRIVATE_DATA_ROOT / ".spx_cache.json"
TRADE_LOG_FILE = PRIVATE_DATA_ROOT / "trade.log"
STDOUT_LOG = PRIVATE_DATA_ROOT / "runtime" / "logs" / "stdout.log"
STDERR_LOG = PRIVATE_DATA_ROOT / "runtime" / "logs" / "stderr.log"
PID_FILE = PRIVATE_DATA_ROOT / "runtime" / "state" / "bot.pid"
