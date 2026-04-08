import unittest
from orb_stacking.indicators import ATR


class TestATR(unittest.TestCase):

    def _bar(self, o, h, l, c):
        return {'open': o, 'high': h, 'low': l, 'close': c}

    def test_not_ready_before_period(self):
        atr = ATR(14)
        for i in range(13):
            result = atr.update(self._bar(100, 101, 99, 100))
            self.assertIsNone(result)
        self.assertFalse(atr.is_ready())

    def test_ready_at_period(self):
        atr = ATR(14)
        for i in range(14):
            result = atr.update(self._bar(100, 102, 98, 100))
        self.assertIsNotNone(result)
        self.assertTrue(atr.is_ready())

    def test_sma_seed_value(self):
        atr = ATR(14)
        for i in range(14):
            result = atr.update(self._bar(100, 102, 98, 100))
        self.assertAlmostEqual(result, 4.0)

    def test_wilder_smoothing_after_seed(self):
        atr = ATR(14)
        for _ in range(14):
            atr.update(self._bar(100, 102, 98, 100))
        # ATR = 4.0. Next: H=120, L=100, prev_close=100 -> TR = max(20, 20, 0) = 20
        result = atr.update(self._bar(100, 120, 100, 110))
        expected = ((4.0 * 13) + 20) / 14
        self.assertAlmostEqual(result, expected, places=6)

    def test_first_bar_uses_high_minus_low(self):
        atr = ATR(3)
        result = atr.update(self._bar(100, 110, 100, 105))
        self.assertIsNone(result)
        atr.update(self._bar(100, 110, 100, 105))
        result = atr.update(self._bar(100, 110, 100, 105))
        self.assertAlmostEqual(result, 10.0)

    def test_reset(self):
        atr = ATR(3)
        for _ in range(5):
            atr.update(self._bar(100, 102, 98, 100))
        atr.reset()
        self.assertFalse(atr.is_ready())
        self.assertIsNone(atr.value)

    def test_serialization_roundtrip(self):
        atr = ATR(14)
        for i in range(20):
            atr.update(self._bar(100 + i, 102 + i, 98 + i, 100 + i))
        d = atr.to_dict()
        atr2 = ATR.from_dict(d)
        self.assertAlmostEqual(atr.value, atr2.value, places=10)
        bar = self._bar(130, 135, 128, 132)
        r1 = atr.update(bar)
        r2 = atr2.update(bar)
        self.assertAlmostEqual(r1, r2, places=10)

    def test_value_property_matches_update(self):
        atr = ATR(3)
        for _ in range(3):
            result = atr.update(self._bar(100, 105, 95, 100))
        self.assertAlmostEqual(atr.value, result)


if __name__ == '__main__':
    unittest.main()
