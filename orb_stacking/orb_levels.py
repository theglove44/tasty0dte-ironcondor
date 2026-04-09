"""ORB level computation for ORB20 / ORB30 / ORB60.

Given a stream of closed 5-minute bars on a single trading day, OrbBuilder
computes the high/low/range/midpoint/close and close_pct for each of the three
ORB windows, locking them at the correct moments.

Lock semantics (per roadmap Slice 2 + SoT §2.2):
  - ORB20 locks on the bar whose START is 09:45 ET (that bar closes at 09:50 ET).
    It spans the 4 bars 09:30, 09:35, 09:40, 09:45 ET.
  - ORB30 locks on the bar whose START is 09:55 ET (closes at 10:00 ET).
    It spans the 6 bars 09:30 .. 09:55 ET.
  - ORB60 locks on the bar whose START is 10:25 ET (closes at 10:30 ET).
    It spans the 12 bars 09:30 .. 10:25 ET.

close_pct is computed as (lock_bar.close - orb.low) / orb.range for the ORB's
final (lock) bar, per SoT §2.2. Undefined (None) when range == 0.

This module has zero dependency on indicators, signals, or any future module.
It is a pure data transformation and imports only stdlib + time_utils.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

from orb_stacking.time_utils import to_et, to_utc


ORB_NAMES = ("ORB20", "ORB30", "ORB60")

# The ET start time of the FIRST bar included in each ORB window.
# All ORBs begin at the opening bar (09:30 ET start).
_WINDOW_START_ET = time(9, 30)

# The ET start time of the LAST (lock) bar for each ORB.
_LOCK_BAR_START_ET = {
    "ORB20": time(9, 45),
    "ORB30": time(9, 55),
    "ORB60": time(10, 25),
}


def _required_starts(lock_start: time) -> frozenset:
    """The exact set of 5-min bar start times that make up an ORB window,
    from 09:30 ET through the lock bar inclusive."""
    out = []
    cur_minutes = 9 * 60 + 30
    end_minutes = lock_start.hour * 60 + lock_start.minute
    while cur_minutes <= end_minutes:
        out.append(time(cur_minutes // 60, cur_minutes % 60))
        cur_minutes += 5
    return frozenset(out)


# Exact required bar-start set per ORB. A lock is only emitted if ALL of
# these timestamps are present in the in-window store at lock time. This
# is stronger than a simple count check — it catches both gaps (missing
# required bar) and early-arriving out-of-window bars that could otherwise
# make the count coincidentally match.
_REQUIRED_STARTS = {
    name: _required_starts(_LOCK_BAR_START_ET[name]) for name in ORB_NAMES
}

GAP_REASON = "bar_gap_during_lock"


@dataclass
class OrbLevels:
    name: str                    # "ORB20" | "ORB30" | "ORB60"
    high: float
    low: float
    range: float
    midpoint: float
    close: float                 # close of the lock bar
    close_pct: Optional[float]   # None if range == 0
    locked_at: datetime          # UTC, = lock_bar.start + 5min


class OrbBuilder:
    """Per-session accumulator that locks ORB20/30/60 at the correct bars.

    Contract:
      - Instances are per trading session. Feeding a bar from a different ET
        date raises ValueError; call reset_for_new_session() first.
      - Arrival order is NOT enforced. Bars may be delivered out-of-order
        (network reorder, gap recovery) or redelivered (DXLink reconnect
        replay, exchange late correction). Same-timestamp redeliveries
        overwrite earlier versions of that bar ("latest wins") as long as
        the ORB owning that bar has not yet locked. The contiguity check
        at lock time is the sole correctness gate.
      - update(bar) returns the list of ORBs that locked on THIS bar (0 or
        1 in practice; the list is for API symmetry with future multi-lock
        edge cases).
    """

    def __init__(self) -> None:
        self._session_et_date = None  # date | None
        self._locked: dict[str, OrbLevels] = {}
        # Per-timestamp store of in-window bars keyed by ET time-of-day.
        # DXLink can redeliver a candle after a reconnect or send a late
        # correction with updated OHLC; we keep the MOST RECENT version
        # for each start time (matching bar_fetcher's dedup semantics) and
        # compute ORB high/low from this store at lock time. The len of
        # this dict also serves as the contiguity count.
        self._in_window_bars: dict[time, dict] = {}
        # Map orb_name -> reason when a lock was skipped due to a gap.
        # Slice 8 reads this when translating into SkipEvent objects.
        self._gap_reasons: dict[str, str] = {}

    # ---- public API ------------------------------------------------------

    def update(self, bar: dict) -> list[OrbLevels]:
        """Feed a closed bar. Returns any ORBs that locked on this bar."""
        bar_start = bar["start"]
        bar_start_et = to_et(bar_start)
        bar_date = bar_start_et.date()

        # Session binding
        if self._session_et_date is None:
            self._session_et_date = bar_date
        elif bar_date != self._session_et_date:
            raise ValueError(
                f"OrbBuilder is per-session: got bar for {bar_date} but "
                f"session is {self._session_et_date}. "
                f"Call reset_for_new_session() first."
            )

        bar_tod = time(bar_start_et.hour, bar_start_et.minute)

        # Arrival order is NOT enforced. Bars may arrive out-of-order
        # (network reorder, gap recovery) or be redelivered as corrections
        # (DXLink reconnect replay, exchange late correction). The only
        # thing that matters for correctness is the state of _in_window_bars
        # at lock time — which is enforced by the contiguity check below.
        # "Latest version wins" semantics for duplicate timestamps match
        # bar_fetcher's dedup behavior.

        # Only bars inside the ORB60 window (09:30 .. 10:25 ET start) are
        # stored for ORB computation. Bars outside are ignored but do not
        # raise — the engine feeds us every closed bar.
        #
        # Same-timestamp redeliveries OVERWRITE the earlier version: late
        # corrections and reconnect-replayed candles must update the OHLC
        # used at lock time, not be dropped. High/low are computed at lock
        # time by scanning this store, so a correction that arrives before
        # the lock bar is fully reflected in the locked ORB.
        if _WINDOW_START_ET <= bar_tod <= _LOCK_BAR_START_ET["ORB60"]:
            self._in_window_bars[bar_tod] = bar

        # Resolve the state of each ORB given the new bar. Two cases mark
        # an ORB as skipped with a gap reason:
        #   (a) bar_tod == lock-bar start, but the required bar set is
        #       incomplete — the classic in-window-gap case.
        #   (b) bar_tod > lock-bar start AND the ORB has not yet locked or
        #       been marked — the lock bar itself never arrived (feed drop
        #       across the lock boundary). Without this, an ORB would sit
        #       in permanent "pending" state and downstream code couldn't
        #       tell "not yet" from "missed forever".
        # Any other state leaves the ORB pending.
        locks: list[OrbLevels] = []
        for name in ORB_NAMES:
            if name in self._locked or name in self._gap_reasons:
                continue

            lock_start = _LOCK_BAR_START_ET[name]
            required = _REQUIRED_STARTS[name]

            if bar_tod == lock_start:
                present = required & self._in_window_bars.keys()
                if len(present) != len(required):
                    missing = sorted(t.strftime("%H:%M") for t in (required - present))
                    self._gap_reasons[name] = (
                        f"{GAP_REASON}: {name} missing bars at ET "
                        f"{','.join(missing)} at lock time"
                    )
                    continue
                level = self._build_level(name, bar, required)
                self._locked[name] = level
                locks.append(level)
            elif bar_tod > lock_start:
                # The lock bar's start time has passed without locking.
                # Either the lock bar is in the store (late arrival — we
                # missed the lock window but the data is there; still a
                # gap from the engine's perspective since no lock event
                # was emitted at the right moment) or it is genuinely
                # missing. Report the most informative reason.
                present = required & self._in_window_bars.keys()
                if len(present) == len(required):
                    self._gap_reasons[name] = (
                        f"{GAP_REASON}: {name} lock bar arrived late "
                        f"(past {lock_start.strftime('%H:%M')} ET)"
                    )
                else:
                    missing = sorted(t.strftime("%H:%M") for t in (required - present))
                    self._gap_reasons[name] = (
                        f"{GAP_REASON}: {name} missing bars at ET "
                        f"{','.join(missing)} (lock window passed)"
                    )

        return locks

    def locked(self, name: str) -> Optional[OrbLevels]:
        """Return the locked ORB, or None if not yet locked (or skipped)."""
        return self._locked.get(name)

    def gap_reason(self, name: str) -> Optional[str]:
        """Return the gap-skip reason for an ORB, or None if no gap.

        Slice 8 will translate these reasons into SkipEvent objects.
        """
        return self._gap_reasons.get(name)

    def all_locked(self) -> bool:
        return all(n in self._locked for n in ORB_NAMES)

    def reset_for_new_session(self) -> None:
        self._session_et_date = None
        self._locked = {}
        self._in_window_bars = {}
        self._gap_reasons = {}

    # ---- internals -------------------------------------------------------

    def _build_level(
        self,
        name: str,
        lock_bar: dict,
        required: frozenset,
    ) -> OrbLevels:
        # Compute high/low across EXACTLY the ORB's required bar set.
        # Early-arriving bars for later ORBs (e.g. 10:00 before ORB20 locks)
        # live in _in_window_bars but must not leak into ORB20's levels, so
        # we filter by the required timestamps the caller passed in.
        bars = [self._in_window_bars[t] for t in required]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        high = max(highs)
        low = min(lows)
        rng = high - low
        midpoint = (high + low) / 2.0
        close = float(lock_bar["close"])
        close_pct: Optional[float]
        if rng == 0:
            close_pct = None
        else:
            close_pct = (close - low) / rng

        locked_at = to_utc(lock_bar["start"]) + timedelta(minutes=5)

        return OrbLevels(
            name=name,
            high=high,
            low=low,
            range=rng,
            midpoint=midpoint,
            close=close,
            close_pct=close_pct,
            locked_at=locked_at,
        )
