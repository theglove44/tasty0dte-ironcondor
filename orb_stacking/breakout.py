"""Close-based breakout detection against a single locked ORB.

Slice 3 — Confirmation mode only: a breakout fires when a closed 5-minute
bar's CLOSE is strictly greater than orb.high (bull) or strictly less than
orb.low (bear). Equality is not a breakout. Wick/penetration modes are not
implemented in this slice.

One-shot semantics: the detector fires ONCE on the first qualifying bar
(whichever direction). Subsequent calls return None, including bars that
close in the opposite direction. Reversal handling belongs to exit logic
(Slice 10), not here.

This module imports only stdlib, orb_levels, and time_utils. It has no knowledge of
stacking, indicators, or the live trading bot.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from orb_stacking.orb_levels import OrbLevels
from orb_stacking.time_utils import to_utc, to_et


_BAR = timedelta(minutes=5)


@dataclass
class Breakout:
    """Immutable record of a single close-based breakout against one locked ORB."""
    orb: OrbLevels
    direction: str          # "bull" | "bear"
    bar: dict               # the bar that triggered
    timestamp: datetime     # bar["start"] + 5min (UTC-aware, close time)
    bars_since_lock: int    # 0 if the breakout bar IS the lock bar


class BreakoutDetector:
    """One-shot close-based breakout detector for a single locked ORB.

    Fires on the first bar whose close is strictly outside the ORB range.
    After firing, all subsequent check() calls return None (one-shot total).
    Pre-lock bars and cross-session bars are silently ignored.
    """
    def __init__(self, orb: OrbLevels) -> None:
        if orb is None:
            raise ValueError("orb cannot be None")
        self._orb = orb
        self._fired = False
        self._lock_bar_start = orb.locked_at - _BAR
        self._session_et_date = to_et(orb.locked_at).date()

    def check(self, bar: dict) -> Optional[Breakout]:
        if self._fired:
            return None

        bar_start = bar["start"]

        if to_et(bar_start).date() != self._session_et_date:
            return None

        if bar_start < self._lock_bar_start:
            return None

        close = float(bar["close"])

        if close > self._orb.high:
            direction = "bull"
        elif close < self._orb.low:
            direction = "bear"
        else:
            return None

        bars_since_lock = int((bar_start - self._lock_bar_start).total_seconds() // 300)

        bo = Breakout(
            orb=self._orb,
            direction=direction,
            bar=bar,
            timestamp=to_utc(bar_start) + _BAR,
            bars_since_lock=bars_since_lock,
        )
        self._fired = True
        return bo


def immediate_breakout(bo: Breakout) -> bool:
    """True if the breakout fired on the lock bar or the bar immediately after (bars_since_lock <= 1)."""
    return bo.bars_since_lock <= 1
