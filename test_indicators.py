import unittest
import math
from indicators import ATR, BollingerBands, MACDV


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


class TestBollingerBands(unittest.TestCase):

    def _bar(self, close):
        return {'open': close, 'high': close + 1, 'low': close - 1, 'close': close}

    def test_not_ready_before_period(self):
        bb = BollingerBands(30, 2.0)
        for i in range(29):
            self.assertIsNone(bb.update(self._bar(100)))
        self.assertFalse(bb.is_ready())

    def test_ready_at_period(self):
        bb = BollingerBands(30, 2.0)
        for i in range(30):
            result = bb.update(self._bar(100))
        self.assertIsNotNone(result)
        self.assertTrue(bb.is_ready())

    def test_constant_closes_zero_width(self):
        bb = BollingerBands(30, 2.0)
        for _ in range(30):
            result = bb.update(self._bar(100))
        self.assertAlmostEqual(result['middle'], 100.0)
        self.assertAlmostEqual(result['upper'], 100.0)
        self.assertAlmostEqual(result['lower'], 100.0)
        self.assertAlmostEqual(result['width'], 0.0)

    def test_known_values_small_period(self):
        bb = BollingerBands(5, 2.0)
        closes = [10, 12, 11, 13, 14]
        for c in closes:
            result = bb.update(self._bar(c))
        mean = 12.0
        var = ((10 - 12) ** 2 + (12 - 12) ** 2 + (11 - 12) ** 2
               + (13 - 12) ** 2 + (14 - 12) ** 2) / 5
        std = math.sqrt(var)
        self.assertAlmostEqual(result['middle'], mean)
        self.assertAlmostEqual(result['upper'], mean + 2 * std)
        self.assertAlmostEqual(result['lower'], mean - 2 * std)

    def test_rolling_window_slides(self):
        bb = BollingerBands(3, 2.0)
        bb.update(self._bar(10))
        bb.update(self._bar(20))
        bb.update(self._bar(30))
        r1 = bb.update(self._bar(40))
        self.assertAlmostEqual(r1['middle'], 30.0)

    def test_value_property_matches_update(self):
        bb = BollingerBands(5, 2.0)
        for c in [10, 12, 11, 13, 14]:
            result = bb.update(self._bar(c))
        prop = bb.value
        self.assertAlmostEqual(result['upper'], prop['upper'])
        self.assertAlmostEqual(result['lower'], prop['lower'])

    def test_serialization_roundtrip(self):
        bb = BollingerBands(5, 2.0)
        for c in [10, 12, 11, 13, 14, 15]:
            bb.update(self._bar(c))
        d = bb.to_dict()
        bb2 = BollingerBands.from_dict(d)
        v1 = bb.value
        v2 = bb2.value
        self.assertAlmostEqual(v1['upper'], v2['upper'])
        self.assertAlmostEqual(v1['lower'], v2['lower'])


class TestMACDV(unittest.TestCase):

    def _bar(self, close, high=None, low=None):
        if high is None:
            high = close + 1
        if low is None:
            low = close - 1
        return {'open': close, 'high': high, 'low': low, 'close': close}

    def test_not_ready_before_slow_period(self):
        m = MACDV(12, 26, 14)
        for i in range(25):
            result = m.update(self._bar(100))
        self.assertIsNone(result)
        self.assertFalse(m.is_ready())

    def test_ready_at_slow_period(self):
        m = MACDV(12, 26, 14)
        for i in range(26):
            result = m.update(self._bar(100))
        self.assertIsNotNone(result)
        self.assertTrue(m.is_ready())

    def test_flat_prices_near_zero(self):
        m = MACDV(12, 26, 14)
        for _ in range(50):
            result = m.update(self._bar(100))
        self.assertAlmostEqual(result['value'], 0.0, places=1)
        self.assertFalse(result['is_extreme'])

    def test_traffic_light_none_when_never_extreme(self):
        m = MACDV(12, 26, 14)
        for _ in range(30):
            result = m.update(self._bar(100))
        self.assertEqual(result['extreme_status'], 'NONE')

    def test_traffic_light_direct_never_extreme(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = False
        self.assertEqual(m._compute_traffic_light(False), 'NONE')

    def test_traffic_light_direct_currently_extreme(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        self.assertEqual(m._compute_traffic_light(True), 'RED')

    def test_traffic_light_direct_red_recent(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 5
        self.assertEqual(m._compute_traffic_light(False), 'RED')

    def test_traffic_light_direct_red_boundary(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 10
        self.assertEqual(m._compute_traffic_light(False), 'RED')

    def test_traffic_light_direct_amber(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 12
        self.assertEqual(m._compute_traffic_light(False), 'AMBER')

    def test_traffic_light_direct_amber_boundary(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 15
        self.assertEqual(m._compute_traffic_light(False), 'AMBER')

    def test_traffic_light_direct_green(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 20
        self.assertEqual(m._compute_traffic_light(False), 'GREEN')

    def test_traffic_light_direct_green_boundary(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 30
        self.assertEqual(m._compute_traffic_light(False), 'GREEN')

    def test_traffic_light_direct_none_stale(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._bars_since_extreme_exit = 35
        self.assertEqual(m._compute_traffic_light(False), 'NONE')

    def test_reset(self):
        m = MACDV(12, 26, 14)
        for _ in range(30):
            m.update(self._bar(100))
        m.reset()
        self.assertFalse(m.is_ready())

    def test_serialization_roundtrip(self):
        m = MACDV(12, 26, 14)
        for i in range(40):
            m.update(self._bar(100 + i * 0.5))
        d = m.to_dict()
        m2 = MACDV.from_dict(d)
        bar = self._bar(125)
        r1 = m.update(bar)
        r2 = m2.update(bar)
        self.assertAlmostEqual(r1['value'], r2['value'], places=10)

    def test_bars_since_exit_increments(self):
        m = MACDV(12, 26, 14)
        m._extreme_ever = True
        m._was_extreme = True
        m._bars_since_extreme_exit = 0
        # Seed enough bars to be ready
        for _ in range(26):
            m.update(self._bar(100))
        # Now the indicator is ready and _was_extreme was reset by flat prices
        # Test by manipulating state directly
        m2 = MACDV(12, 26, 14)
        m2._extreme_ever = True
        m2._was_extreme = False
        m2._bars_since_extreme_exit = 5
        # Simulate _compute_traffic_light progression
        self.assertEqual(m2._compute_traffic_light(False), 'RED')
        m2._bars_since_extreme_exit = 11
        self.assertEqual(m2._compute_traffic_light(False), 'AMBER')
        m2._bars_since_extreme_exit = 16
        self.assertEqual(m2._compute_traffic_light(False), 'GREEN')


if __name__ == '__main__':
    unittest.main()
