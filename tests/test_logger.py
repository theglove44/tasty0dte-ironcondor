"""Tests for tasty0dte.logger -- specifically the IV Rank scale normalisation.

These tests are fully self-contained: ``logger.LOG_FILE`` is repointed at a
temporary file in ``setUp`` so nothing here touches the real paper_trades.csv or
the bot's trade.log.
"""

import csv
import os
import shutil
import tempfile
import unittest

import tasty0dte.logger as logger


# Minimal legs dict in the shape log_trade_entry expects.
LEGS = {
    "short_call": {"symbol": ".SPXW260101C7000"},
    "long_call": {"symbol": ".SPXW260101C7010"},
    "short_put": {"symbol": ".SPXW260101P6900"},
    "long_put": {"symbol": ".SPXW260101P6890"},
}


class IVRankNormalisationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmpdir, "paper_trades.csv")
        self._orig_log_file = logger.LOG_FILE
        logger.LOG_FILE = self.csv_path

    def tearDown(self):
        logger.LOG_FILE = self._orig_log_file
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _log_iv(self, iv_rank):
        """Log one trade with the given iv_rank and return the stored string."""
        logger.log_trade_entry(
            LEGS, credit=1.00, buying_power=100.0, profit_target=0.25,
            iv_rank=iv_rank, strategy_name="Test", strategy_id="T-1",
        )
        with open(self.csv_path, newline="") as fh:
            rows = list(csv.DictReader(fh))
        return rows[-1]["IV Rank"]

    def test_percentage_is_scaled_down_to_ratio(self):
        # A 0-100 percentage (e.g. SDK/source that returns 37.15) is stored as 0.37.
        self.assertEqual(self._log_iv(37.15), "0.37")

    def test_ratio_is_left_unchanged(self):
        # A value already on the 0-1 ratio scale is stored as-is.
        self.assertEqual(self._log_iv(0.37), "0.37")

    def test_both_scales_converge(self):
        # The core invariant: the same underlying IV rank stores identically
        # whether it arrives as a ratio or as a percentage.
        self.assertEqual(self._log_iv(0.37), self._log_iv(37.15))

    def test_max_observed_percentage(self):
        # Highest value seen in the dataset (69.42) -> 0.69.
        self.assertEqual(self._log_iv(69.42), "0.69")

    def test_zero_sentinel_stays_zero(self):
        # 0.0 means "no IV fetched" (e.g. Jade Lizard); must not be rescaled.
        self.assertEqual(self._log_iv(0.0), "0.00")

    def test_full_ratio_boundary_kept(self):
        # A true 100th-percentile IV rank is ratio 1.0; must stay a ratio.
        self.assertEqual(self._log_iv(1.0), "1.00")

    def test_hundred_percent_scaled_down(self):
        # The same value expressed as a percentage (100.0) -> ratio 1.0.
        self.assertEqual(self._log_iv(100.0), "1.00")

    def test_guard_threshold(self):
        # The guard divides only when value > 1.5. 1.5 itself is kept; anything
        # clearly above (2.0) is treated as a percentage and divided by 100.
        self.assertEqual(self._log_iv(1.5), "1.50")
        self.assertEqual(self._log_iv(2.0), "0.02")


if __name__ == "__main__":
    unittest.main()
