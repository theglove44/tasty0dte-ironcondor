import os
import unittest
from pathlib import Path

import project_paths


class TestProjectPaths(unittest.TestCase):
    def test_defaults_preserve_legacy_root_locations(self):
        root = Path(project_paths.PROJECT_ROOT)

        self.assertEqual(project_paths.PAPER_TRADES_CSV, root / "data" / "paper_trades.csv")
        self.assertEqual(project_paths.SKIP_EVENTS_CSV, root / "data" / "skip_events.csv")
        self.assertEqual(project_paths.SPX_CACHE_JSON, root / "runtime" / "state" / ".spx_cache.json")
        self.assertEqual(project_paths.TRADE_LOG, root / "runtime" / "logs" / "trade.log")
        self.assertEqual(project_paths.STDOUT_LOG, root / "runtime" / "logs" / "stdout.log")
        self.assertEqual(project_paths.STDERR_LOG, root / "runtime" / "logs" / "stderr.log")
        self.assertEqual(project_paths.CRON_LOG, root / "runtime" / "logs" / "cron.log")
        self.assertEqual(project_paths.BOT_PID, root / "runtime" / "state" / "bot.pid")

    def test_env_override_relative_paths_resolve_under_project_root(self):
        old_value = os.environ.get("TASTY_PAPER_TRADES_CSV")
        try:
            os.environ["TASTY_PAPER_TRADES_CSV"] = "data/paper_trades.csv"
            resolved = project_paths._path_from_env(
                "TASTY_PAPER_TRADES_CSV",
                project_paths.PROJECT_ROOT / "paper_trades.csv",
            )
            self.assertEqual(resolved, project_paths.PROJECT_ROOT / "data" / "paper_trades.csv")
        finally:
            if old_value is None:
                os.environ.pop("TASTY_PAPER_TRADES_CSV", None)
            else:
                os.environ["TASTY_PAPER_TRADES_CSV"] = old_value
