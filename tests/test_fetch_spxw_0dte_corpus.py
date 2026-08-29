import unittest
from datetime import date

from tools.fetch_spxw_0dte_corpus import (
    is_spxw_expiry_day,
    osi,
    strike_bounds,
    symbols_for_day,
)


class TestExpiryCalendar(unittest.TestCase):
    def test_thursday_starts_19_may_2022(self):
        self.assertFalse(is_spxw_expiry_day(date(2022, 5, 12)))
        self.assertTrue(is_spxw_expiry_day(date(2022, 5, 19)))

    def test_weekends_are_excluded(self):
        self.assertFalse(is_spxw_expiry_day(date(2022, 5, 21)))


class TestStrikeSelection(unittest.TestCase):
    def test_high_low_envelope_adds_ten_strikes(self):
        self.assertEqual(strike_bounds(5001.0, 5039.0), (4950, 5090))

    def test_symbols_include_calls_and_puts_at_every_strike(self):
        symbols = symbols_for_day(date(2026, 1, 2), 5000.0, 5000.0)
        self.assertEqual(len(symbols), 42)
        self.assertEqual(symbols[0], "SPXW  260102C04950000")
        self.assertEqual(symbols[-1], "SPXW  260102P05050000")

    def test_osi_format(self):
        self.assertEqual(osi(date(2026, 8, 21), "P", 7665),
                         "SPXW  260821P07665000")


if __name__ == "__main__":
    unittest.main()
