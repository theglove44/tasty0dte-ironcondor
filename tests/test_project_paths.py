"""Subprocess tests for deterministic private runtime path resolution."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PRIVATE_PATH_NAMES = (
    "PAPER_TRADES_CSV",
    "SKIP_EVENTS_CSV",
    "SPX_CACHE_JSON",
    "BOT_PID",
    "CRON_LOG",
    "TRADE_LOG",
    "STDOUT_LOG",
    "STDERR_LOG",
)

PATH_DUMP = """
import json
from pathlib import Path
import project_paths as paths

names = ['PROJECT_ROOT', 'PRIVATE_DATA_ROOT'] + %r
result = {name: str(getattr(paths, name)) for name in names}
result['HOME'] = str(Path.home())
print(json.dumps(result))
""" % (list(PRIVATE_PATH_NAMES),)


class TestProjectPaths(unittest.TestCase):
    """Import a copied module so tests never read or write private records."""

    def _import_paths(self, extra_env=None, create_legacy_ledger=False):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_root = Path(temp_dir)
            shutil.copy2(Path(__file__).parents[1] / "project_paths.py", module_root)
            if create_legacy_ledger:
                legacy_ledger = module_root / "data" / "paper_trades.csv"
                legacy_ledger.parent.mkdir()
                legacy_ledger.touch()

            env = os.environ.copy()
            env["HOME"] = str(module_root / "home")
            env["PYTHONPATH"] = str(module_root)
            env.pop("PYTHONHOME", None)
            for name in ("TASTY_PRIVATE_DATA_ROOT",) + tuple(
                f"TASTY_{name}" for name in PRIVATE_PATH_NAMES
            ):
                env[name] = ""
            env.update(extra_env or {})

            result = subprocess.run(
                [sys.executable, "-c", PATH_DUMP],
                cwd=module_root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            return {name: Path(value) for name, value in json.loads(result.stdout).items()}

    def test_default_uses_controlled_home_private_root(self):
        paths = self._import_paths()
        private_root = paths["HOME"] / "Private/ProjectsData/trading/tasty0dte-ironcondor"

        self.assertEqual(paths["PRIVATE_DATA_ROOT"], private_root)
        self.assertEqual(paths["PAPER_TRADES_CSV"], private_root / "data/paper_trades.csv")
        self.assertEqual(paths["SKIP_EVENTS_CSV"], private_root / "data/skip_events.csv")
        self.assertEqual(paths["SPX_CACHE_JSON"], private_root / "runtime/state/.spx_cache.json")
        self.assertEqual(paths["BOT_PID"], private_root / "runtime/state/bot.pid")
        self.assertEqual(paths["CRON_LOG"], private_root / "runtime/logs/cron.log")
        self.assertEqual(paths["TRADE_LOG"], private_root / "runtime/logs/trade.log")
        self.assertEqual(paths["STDOUT_LOG"], private_root / "runtime/logs/stdout.log")
        self.assertEqual(paths["STDERR_LOG"], private_root / "runtime/logs/stderr.log")

    def test_explicit_private_root_controls_every_private_path(self):
        paths = self._import_paths({"TASTY_PRIVATE_DATA_ROOT": "/tmp/tasty-private"})
        private_root = Path("/tmp/tasty-private")

        self.assertEqual(paths["PRIVATE_DATA_ROOT"], private_root)
        self.assertEqual(paths["PAPER_TRADES_CSV"], private_root / "data/paper_trades.csv")
        self.assertEqual(paths["SKIP_EVENTS_CSV"], private_root / "data/skip_events.csv")
        self.assertEqual(paths["SPX_CACHE_JSON"], private_root / "runtime/state/.spx_cache.json")
        self.assertEqual(paths["BOT_PID"], private_root / "runtime/state/bot.pid")
        self.assertEqual(paths["CRON_LOG"], private_root / "runtime/logs/cron.log")
        self.assertEqual(paths["TRADE_LOG"], private_root / "runtime/logs/trade.log")
        self.assertEqual(paths["STDOUT_LOG"], private_root / "runtime/logs/stdout.log")
        self.assertEqual(paths["STDERR_LOG"], private_root / "runtime/logs/stderr.log")

    def test_legacy_repository_ledger_never_changes_resolution(self):
        paths = self._import_paths(create_legacy_ledger=True)

        self.assertNotEqual(paths["PAPER_TRADES_CSV"], paths["PROJECT_ROOT"] / "data/paper_trades.csv")
        self.assertEqual(
            paths["PAPER_TRADES_CSV"],
            paths["HOME"] / "Private/ProjectsData/trading/tasty0dte-ironcondor/data/paper_trades.csv",
        )

    def test_relative_per_file_override_resolves_under_project_root(self):
        paths = self._import_paths(
            {
                "TASTY_PRIVATE_DATA_ROOT": "/tmp/tasty-private",
                "TASTY_PAPER_TRADES_CSV": "custom/paper_trades.csv",
            }
        )

        self.assertEqual(
            paths["PAPER_TRADES_CSV"],
            paths["PROJECT_ROOT"] / "custom/paper_trades.csv",
        )
