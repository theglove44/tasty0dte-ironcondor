"""
Composite scoring for Tag N Turn trade qualification.

Pure functions: no state, no side effects, easily testable.
"""

TIERS = {
    'SKIP': 0.0,
    'HALF': 0.5,
    'NORMAL': 1.0,
    'PLUS': 1.5,
    'DOUBLE': 2.0,
}


def score_v_pattern(bars_to_completion: int | None) -> int:
    if bars_to_completion is None:
        return 0
    if bars_to_completion <= 5:
        return 3
    if bars_to_completion <= 15:
        return 2
    return 0


def score_macdv_light(extreme_status: str, direction: str) -> int:
    if direction.lower() != 'short':
        return 0
    mapping = {'RED': -3, 'AMBER': -1, 'GREEN': 1, 'NONE': 0}
    return mapping.get(extreme_status, 0)


def score_pulse_strength(body: float, atr: float) -> int:
    if atr <= 0:
        return 0
    ratio = body / atr
    if 1.0 <= ratio <= 1.5:
        return 1
    if 0.75 <= ratio < 1.0 or 1.5 < ratio <= 2.0:
        return 0
    return -1


def score_time_of_day(et_hour: int, et_minute: int) -> int:
    t = et_hour * 60 + et_minute
    if 15 * 60 + 30 <= t < 17 * 60:
        return 1
    if 17 * 60 <= t < 19 * 60:
        return -1
    if (14 * 60 + 30 <= t < 15 * 60 + 30
            or 19 * 60 <= t < 21 * 60):
        return 0
    return 0


def score_bb_depth(penetration_atr: float, direction: str) -> int:
    if direction.lower() != 'long':
        return 0
    if penetration_atr >= 0.5:
        return 1
    return 0


def get_tier(score: int) -> tuple[str, float]:
    if score <= -2:
        return ('SKIP', 0.0)
    if score <= 0:
        return ('HALF', 0.5)
    if score <= 2:
        return ('NORMAL', 1.0)
    if score == 3:
        return ('PLUS', 1.5)
    return ('DOUBLE', 2.0)


def composite_score(factors: dict) -> dict:
    """Combine individual factor scores into a composite result.

    factors: dict with keys matching factor names, values are int scores.
    """
    total = sum(factors.values())
    tier_name, sizing_mult = get_tier(total)
    return {
        'score': total,
        'tier': tier_name,
        'sizing_mult': sizing_mult,
        'factors_breakdown': dict(factors),
    }
