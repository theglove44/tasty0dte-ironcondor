import unittest
from scoring import (
    score_v_pattern, score_macdv_light, score_pulse_strength,
    score_time_of_day, score_bb_depth, composite_score, get_tier,
)


class TestScoreVPattern(unittest.TestCase):
    def test_fast_v(self):
        self.assertEqual(score_v_pattern(1), 3)
        self.assertEqual(score_v_pattern(3), 3)
        self.assertEqual(score_v_pattern(5), 3)

    def test_medium_v(self):
        self.assertEqual(score_v_pattern(6), 2)
        self.assertEqual(score_v_pattern(10), 2)
        self.assertEqual(score_v_pattern(15), 2)

    def test_stale(self):
        self.assertEqual(score_v_pattern(16), 0)
        self.assertEqual(score_v_pattern(100), 0)

    def test_none(self):
        self.assertEqual(score_v_pattern(None), 0)


class TestScoreMACDVLight(unittest.TestCase):
    def test_short_red(self):
        self.assertEqual(score_macdv_light('RED', 'short'), -3)

    def test_short_amber(self):
        self.assertEqual(score_macdv_light('AMBER', 'short'), -1)

    def test_short_green(self):
        self.assertEqual(score_macdv_light('GREEN', 'short'), 1)

    def test_short_none(self):
        self.assertEqual(score_macdv_light('NONE', 'short'), 0)

    def test_long_always_zero(self):
        self.assertEqual(score_macdv_light('RED', 'long'), 0)
        self.assertEqual(score_macdv_light('AMBER', 'long'), 0)
        self.assertEqual(score_macdv_light('GREEN', 'long'), 0)

    def test_case_insensitive_direction(self):
        self.assertEqual(score_macdv_light('RED', 'Short'), -3)
        self.assertEqual(score_macdv_light('RED', 'SHORT'), -3)
        self.assertEqual(score_macdv_light('RED', 'Long'), 0)


class TestScorePulseStrength(unittest.TestCase):
    def test_sweet_spot(self):
        self.assertEqual(score_pulse_strength(1.0, 1.0), 1)
        self.assertEqual(score_pulse_strength(1.2, 1.0), 1)
        self.assertEqual(score_pulse_strength(1.5, 1.0), 1)

    def test_normal_low(self):
        self.assertEqual(score_pulse_strength(0.75, 1.0), 0)
        self.assertEqual(score_pulse_strength(0.9, 1.0), 0)

    def test_normal_high(self):
        self.assertEqual(score_pulse_strength(1.8, 1.0), 0)
        self.assertEqual(score_pulse_strength(2.0, 1.0), 0)

    def test_weak(self):
        self.assertEqual(score_pulse_strength(0.5, 1.0), -1)
        self.assertEqual(score_pulse_strength(0.1, 1.0), -1)

    def test_exhaustion(self):
        self.assertEqual(score_pulse_strength(2.5, 1.0), -1)
        self.assertEqual(score_pulse_strength(5.0, 1.0), -1)

    def test_zero_atr_returns_neutral(self):
        self.assertEqual(score_pulse_strength(1.0, 0.0), 0)

    def test_negative_atr_returns_neutral(self):
        self.assertEqual(score_pulse_strength(1.0, -1.0), 0)

    def test_with_real_atr(self):
        # body=7.5, atr=6.0 -> ratio=1.25 -> sweet spot
        self.assertEqual(score_pulse_strength(7.5, 6.0), 1)


class TestScoreTimeOfDay(unittest.TestCase):
    def test_sweet_spot(self):
        self.assertEqual(score_time_of_day(15, 30), 1)
        self.assertEqual(score_time_of_day(16, 0), 1)
        self.assertEqual(score_time_of_day(16, 30), 1)
        self.assertEqual(score_time_of_day(16, 59), 1)

    def test_neutral_early(self):
        self.assertEqual(score_time_of_day(14, 30), 0)
        self.assertEqual(score_time_of_day(15, 0), 0)
        self.assertEqual(score_time_of_day(15, 29), 0)

    def test_neutral_evening(self):
        self.assertEqual(score_time_of_day(19, 0), 0)
        self.assertEqual(score_time_of_day(20, 30), 0)
        self.assertEqual(score_time_of_day(20, 59), 0)

    def test_dead_zone(self):
        self.assertEqual(score_time_of_day(17, 0), -1)
        self.assertEqual(score_time_of_day(18, 0), -1)
        self.assertEqual(score_time_of_day(18, 59), -1)

    def test_boundary_17_is_dead_zone(self):
        self.assertEqual(score_time_of_day(17, 0), -1)

    def test_boundary_19_is_neutral(self):
        self.assertEqual(score_time_of_day(19, 0), 0)


class TestScoreBBDepth(unittest.TestCase):
    def test_deep_long(self):
        self.assertEqual(score_bb_depth(0.5, 'long'), 1)
        self.assertEqual(score_bb_depth(1.0, 'long'), 1)

    def test_shallow_long(self):
        self.assertEqual(score_bb_depth(0.3, 'long'), 0)
        self.assertEqual(score_bb_depth(0.0, 'long'), 0)

    def test_short_always_zero(self):
        self.assertEqual(score_bb_depth(1.0, 'short'), 0)
        self.assertEqual(score_bb_depth(0.0, 'short'), 0)

    def test_case_insensitive(self):
        self.assertEqual(score_bb_depth(0.5, 'Long'), 1)
        self.assertEqual(score_bb_depth(0.5, 'Short'), 0)


class TestGetTier(unittest.TestCase):
    def test_skip(self):
        self.assertEqual(get_tier(-5), ('SKIP', 0.0))
        self.assertEqual(get_tier(-2), ('SKIP', 0.0))

    def test_half(self):
        self.assertEqual(get_tier(-1), ('HALF', 0.5))
        self.assertEqual(get_tier(0), ('HALF', 0.5))

    def test_normal(self):
        self.assertEqual(get_tier(1), ('NORMAL', 1.0))
        self.assertEqual(get_tier(2), ('NORMAL', 1.0))

    def test_plus(self):
        self.assertEqual(get_tier(3), ('PLUS', 1.5))

    def test_double(self):
        self.assertEqual(get_tier(4), ('DOUBLE', 2.0))
        self.assertEqual(get_tier(10), ('DOUBLE', 2.0))


class TestCompositeScore(unittest.TestCase):
    def test_double_setup_all_positive(self):
        factors = {
            'v_pattern': 3,
            'macdv_light': 1,
            'pulse_strength': 1,
            'time_of_day': 1,
            'bb_depth': 0,
        }
        result = composite_score(factors)
        self.assertEqual(result['score'], 6)
        self.assertEqual(result['tier'], 'DOUBLE')
        self.assertEqual(result['sizing_mult'], 2.0)
        self.assertEqual(result['factors_breakdown'], factors)

    def test_skip_setup_all_negative(self):
        factors = {
            'v_pattern': 0,
            'macdv_light': -3,
            'pulse_strength': -1,
            'time_of_day': -1,
            'bb_depth': 0,
        }
        result = composite_score(factors)
        self.assertEqual(result['score'], -5)
        self.assertEqual(result['tier'], 'SKIP')
        self.assertEqual(result['sizing_mult'], 0.0)

    def test_typical_normal_short(self):
        factors = {
            'v_pattern': 2,
            'macdv_light': -1,
            'pulse_strength': 0,
            'time_of_day': 1,
            'bb_depth': 0,
        }
        result = composite_score(factors)
        self.assertEqual(result['score'], 2)
        self.assertEqual(result['tier'], 'NORMAL')
        self.assertEqual(result['sizing_mult'], 1.0)

    def test_plus_long_setup(self):
        factors = {
            'v_pattern': 2,
            'macdv_light': 0,
            'pulse_strength': 0,
            'time_of_day': 0,
            'bb_depth': 1,
        }
        result = composite_score(factors)
        self.assertEqual(result['score'], 3)
        self.assertEqual(result['tier'], 'PLUS')
        self.assertEqual(result['sizing_mult'], 1.5)

    def test_half_tier_mixed(self):
        factors = {
            'v_pattern': 0,
            'macdv_light': 0,
            'pulse_strength': 0,
            'time_of_day': -1,
            'bb_depth': 1,
        }
        result = composite_score(factors)
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['tier'], 'HALF')
        self.assertEqual(result['sizing_mult'], 0.5)


if __name__ == '__main__':
    unittest.main()
