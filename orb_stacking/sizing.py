"""Slice 9 — Sizing combiner (ROADMAP §A1).

Pure function combining stack tier, base tier, and calendar score into a
final contract count. No I/O, no SDK, no async. stdlib only.

Formula (ROADMAP §A1):
    raw = BASE_UNIT × stack_mult × base_mult × calendar_mult
    calendar_mult = 1.0 + CALENDAR_MULT_PER_POINT × clamp(calendar_score, -2, +2)

    contracts = 0                                         if stack_tier == "EXITED"
    contracts = 0                                         if raw < RAW_ZERO_THRESHOLD (0.5)
    contracts = max(1, min(MAX_CONTRACTS, round(raw)))    otherwise

Note: Python's built-in round() uses banker's rounding (half-to-even).
"""
from __future__ import annotations

BASE_UNIT: int = 1
MAX_CONTRACTS: int = 4
CALENDAR_MULT_PER_POINT: float = 0.25
CALENDAR_SCORE_MIN: int = -2
CALENDAR_SCORE_MAX: int = 2
RAW_ZERO_THRESHOLD: float = 0.5

STACK_MULT: dict[str, float] = {
    "HALF":   0.5,
    "NORMAL": 1.0,
    "PLUS":   1.5,
    "DOUBLE": 2.0,
}

BASE_MULT: dict[str, float] = {
    "HALF":   0.5,
    "NORMAL": 1.0,
    "PLUS":   1.25,
    "DOUBLE": 1.5,
}

_VALID_STACK_TIERS: frozenset[str] = frozenset(STACK_MULT) | {"EXITED"}


def compute_contracts(
    stack_tier: str,
    base_tier: str,
    calendar_score: int,
) -> dict:
    """Combine stack tier, base tier, and calendar score into a contract count.

    Args:
        stack_tier: One of {"HALF","NORMAL","PLUS","DOUBLE","EXITED"}.
            "FLAT" is rejected — caller is in a pre-breakout state.
        base_tier: One of {"HALF","NORMAL","PLUS","DOUBLE"}.
        calendar_score: Integer in [-2, +2]. Values outside this range are
            clamped internally (not rejected).

    Returns:
        Dict with keys:
          contracts     (int)
          stack_mult    (float)
          base_mult     (float)
          calendar_mult (float)
          raw           (float)
          clamped       (int)

    Raises:
        ValueError: If stack_tier is "FLAT" or unrecognised, or base_tier is unrecognised.
    """
    if stack_tier == "FLAT":
        raise ValueError(
            "stack_tier 'FLAT' is not a valid sizing tier; "
            "compute_contracts must be called only after ORB20_BREAK"
        )
    if stack_tier not in _VALID_STACK_TIERS:
        raise ValueError(
            f"stack_tier {stack_tier!r} is not one of {sorted(_VALID_STACK_TIERS)}"
        )
    if base_tier not in BASE_MULT:
        raise ValueError(
            f"base_tier {base_tier!r} is not one of {sorted(BASE_MULT)}"
        )

    stack_mult: float = 0.0 if stack_tier == "EXITED" else STACK_MULT[stack_tier]
    base_mult: float = BASE_MULT[base_tier]
    score_clamped = max(CALENDAR_SCORE_MIN, min(CALENDAR_SCORE_MAX, int(calendar_score)))
    calendar_mult: float = 1.0 + CALENDAR_MULT_PER_POINT * score_clamped

    raw: float = float(BASE_UNIT) * stack_mult * base_mult * calendar_mult

    clamped: int = max(1, min(MAX_CONTRACTS, int(round(raw))))

    if stack_tier == "EXITED":
        contracts = 0
    elif raw < RAW_ZERO_THRESHOLD:
        contracts = 0
    else:
        contracts = clamped

    return {
        "contracts":     contracts,
        "stack_mult":    stack_mult,
        "base_mult":     base_mult,
        "calendar_mult": calendar_mult,
        "raw":           raw,
        "clamped":       clamped,
    }
