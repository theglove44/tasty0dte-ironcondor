"""
Tests for strategy.validate_credit_sanity.

Guards the 2026-04-06 Iron Fly V1 phantom-fill bug:
  - Entry REST marks gave $10 credit on a $10-wide fly (arbitrage)
  - Short call/put of same strike violated put-call parity by ~$4
  - Trade "profited" $1.20 purely from mark normalization
"""
import unittest
import strategy


def _legs(sc_strike, sc_price, lc_strike, lc_price,
          sp_strike, sp_price, lp_strike, lp_price):
    return {
        'short_call': {'strike': sc_strike, 'price': sc_price},
        'long_call':  {'strike': lc_strike, 'price': lc_price},
        'short_put':  {'strike': sp_strike, 'price': sp_price},
        'long_put':   {'strike': lp_strike, 'price': lp_price},
    }


class TestValidateCreditSanity(unittest.TestCase):

    # ---- Max-credit / arbitrage guard ------------------------------------

    def test_rejects_credit_equal_to_wing_width(self):
        """Credit == wing width is a riskless arbitrage — impossible fill."""
        legs = _legs(6600, 20.25, 6610, 14.25,
                     6600, 17.35, 6590, 13.35)
        credit = 10.00
        valid, reason = strategy.validate_credit_sanity(
            legs, credit, wing_width=10, spx_spot=6607.19
        )
        self.assertFalse(valid)
        self.assertIn("arbitrage", reason)

    def test_rejects_credit_inside_cushion(self):
        """Credit within 0.25 of wing width is also rejected."""
        legs = _legs(6600, 15.0, 6610, 10.0,
                     6600, 10.0, 6590, 5.2)
        credit = 9.80  # 10 - 0.20 < cushion 0.25
        valid, _ = strategy.validate_credit_sanity(
            legs, credit, wing_width=10, spx_spot=6600
        )
        self.assertFalse(valid)

    def test_accepts_normal_atm_fly_credit(self):
        """A $5.90 credit on a $10 wing is the realistic ATM fly."""
        legs = _legs(6600, 10.0, 6610, 6.0,
                     6600, 4.0, 6590, 2.10)
        credit = 5.90
        valid, reason = strategy.validate_credit_sanity(
            legs, credit, wing_width=10, spx_spot=6607
        )
        self.assertTrue(valid, f"Expected valid, got: {reason}")

    # ---- Put-call parity guard -------------------------------------------

    def test_rejects_put_call_parity_violation(self):
        """
        Reproduces 2026-04-06 V1: SPX 6607, strike 6600.
          C - P = 20.25 - 17.35 = 2.90
          expected = spot - strike = 7.19
          drift = 4.29  > 2.00 tolerance
        """
        legs = _legs(6600, 20.25, 6610, 14.25,
                     6600, 17.35, 6590, 13.35)
        # Use a credit BELOW arbitrage to isolate the parity check
        credit = 5.00
        valid, reason = strategy.validate_credit_sanity(
            legs, credit, wing_width=10, spx_spot=6607.19
        )
        self.assertFalse(valid)
        self.assertIn("parity", reason)

    def test_accepts_parity_compliant_fly(self):
        """V2 marks from the same incident (7s later) — parity holds."""
        # C - P = 22.45 - 14.95 = 7.50; spot - strike = 8.00; drift 0.50 OK
        legs = _legs(6600, 22.45, 6610, 16.65,
                     6600, 14.95, 6590, 11.45)
        credit = 9.30
        valid, reason = strategy.validate_credit_sanity(
            legs, credit, wing_width=10, spx_spot=6608
        )
        self.assertTrue(valid, f"Expected valid, got: {reason}")

    def test_parity_check_skipped_for_asymmetric_strikes(self):
        """Iron condors have different short strikes — parity N/A."""
        legs = _legs(6645, 6.85, 6665, 2.45,
                     6565, 4.60, 6545, 2.90)
        credit = 6.10
        valid, _ = strategy.validate_credit_sanity(
            legs, credit, wing_width=20, spx_spot=6608
        )
        self.assertTrue(valid)

    def test_parity_check_skipped_when_spot_unknown(self):
        legs = _legs(6600, 20.25, 6610, 14.25,
                     6600, 17.35, 6590, 13.35)
        valid, _ = strategy.validate_credit_sanity(
            legs, credit=5.00, wing_width=10, spx_spot=None
        )
        self.assertTrue(valid)

    def test_parity_tolerance_edge(self):
        """Drift exactly at tolerance should pass; just over should fail."""
        # spot - strike = 5.00; at tolerance: C-P = 3.00 (drift=2.00)
        legs_ok = _legs(6600, 8.00, 6610, 4.00,
                        6600, 5.00, 6590, 3.00)
        valid, _ = strategy.validate_credit_sanity(
            legs_ok, credit=6.00, wing_width=10, spx_spot=6605
        )
        self.assertTrue(valid)

        # Just over: drift = 2.01
        legs_bad = _legs(6600, 8.00, 6610, 4.00,
                         6600, 5.01, 6590, 3.00)
        valid, _ = strategy.validate_credit_sanity(
            legs_bad, credit=5.99, wing_width=10, spx_spot=6605
        )
        self.assertFalse(valid)

    # ---- Defensive handling ----------------------------------------------

    def test_missing_leg_data_does_not_crash(self):
        legs = {'short_call': {}, 'long_call': {}, 'short_put': {}, 'long_put': {}}
        valid, reason = strategy.validate_credit_sanity(
            legs, credit=5.00, wing_width=10, spx_spot=6607
        )
        # Max-credit passes (credit < 10 - 0.25), parity skipped cleanly
        self.assertTrue(valid)

    def test_zero_wing_width_skips_max_credit_check(self):
        """Degenerate case — don't crash on zero-wide (shouldn't happen in prod)."""
        legs = _legs(6600, 1.0, 6600, 1.0, 6600, 1.0, 6600, 1.0)
        valid, _ = strategy.validate_credit_sanity(
            legs, credit=0.0, wing_width=0, spx_spot=6600
        )
        self.assertTrue(valid)


if __name__ == '__main__':
    unittest.main()
