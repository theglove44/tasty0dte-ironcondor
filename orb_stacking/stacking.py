"""Slice 4 ORB stacking engine.

This module connects the locked ORB windows from ``OrbBuilder`` to three
``BreakoutDetector`` instances and emits session-level stacking events.

The engine is deliberately narrow in scope for Slice 4:
  - ORB20 establishes the initial direction and moves the stack to ``HALF``
  - ORB30 can confirm that direction to reach ``NORMAL`` or oppose without exit
  - ORB60 can confirm to reach ``PLUS``/``DOUBLE`` or oppose to force ``EXITED``
  - a session can also emit ``ORB60_NO_BREAKOUT`` and ``TIMEOUT_NOON``

**Bar ordering contract:** ``on_closed_bar()`` expects bars delivered in
monotonically non-decreasing time order (matching live DXLink streaming).
Out-of-order delivery after an ORB window locks may produce contradictory
event sequences (e.g. ``ORB60_NO_BREAKOUT`` followed by a later ``ORB20_BREAK``
from a delayed bar). The caller is responsible for ensuring order; this engine
does not validate timestamps against previously seen bars.

The engine is per-session state. Call ``reset_for_new_session()`` between
trading days.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from orb_stacking.orb_levels import OrbBuilder, OrbLevels, ORB_NAMES
from orb_stacking.breakout import Breakout, BreakoutDetector
from orb_stacking.time_utils import to_utc, entry_window_closed


logger = logging.getLogger(__name__)


# Exported for downstream consumers (Slice 8 SkipEvent, Slice 9 sizing, etc.)
VALID_KINDS = frozenset(
    {
        "ORB20_BREAK",
        "ORB30_CONFIRM",
        "ORB30_OPPOSE",
        "ORB60_CONFIRM",
        "ORB60_OPPOSE",
        "ORB60_NO_BREAKOUT",
        "TIMEOUT_NOON",
    }
)

# Exported for downstream consumers; order reflects progression (no regression allowed).
TIERS = ("FLAT", "HALF", "NORMAL", "PLUS", "DOUBLE", "EXITED")

LOCK_TOLERANCE_MS = 3000

_TIER_ORDER = {"FLAT": 0, "HALF": 1, "NORMAL": 2, "PLUS": 3, "DOUBLE": 4}


@dataclass
class StackingEvent:
    kind: str
    direction: Optional[str]
    orb: Optional[OrbLevels]
    bar: dict
    timestamp: datetime
    state_snapshot: dict


class StackingEngine:
    def __init__(self) -> None:
        self._orb_builder = OrbBuilder()
        self._detectors = {}
        self._tier = "FLAT"
        self._direction = None
        self._orb20_breakout = None
        self._orb30_breakout = None
        self._orb60_breakout = None
        self._orb60_no_breakout_emitted = False
        self._timeout_noon_emitted = False
        self._closes_aligned = 0

    def reset_for_new_session(self) -> None:
        self._orb_builder.reset_for_new_session()
        self._detectors = {}
        self._tier = "FLAT"
        self._direction = None
        self._orb20_breakout = None
        self._orb30_breakout = None
        self._orb60_breakout = None
        self._orb60_no_breakout_emitted = False
        self._timeout_noon_emitted = False
        self._closes_aligned = 0

    @property
    def current_tier(self) -> str:
        return self._tier

    @property
    def direction(self) -> Optional[str]:
        return self._direction

    @property
    def orb_builder(self) -> OrbBuilder:
        return self._orb_builder

    @property
    def orb20_breakout(self) -> Optional[Breakout]:
        return self._orb20_breakout

    @property
    def orb30_breakout(self) -> Optional[Breakout]:
        return self._orb30_breakout

    @property
    def orb60_breakout(self) -> Optional[Breakout]:
        return self._orb60_breakout

    def on_closed_bar(self, bar: dict) -> list[StackingEvent]:
        events: list[StackingEvent] = []

        newly_locked = self._orb_builder.update(bar)
        orb60_just_locked = False

        for orb in newly_locked:
            self._check_stale_lock_bar(orb, bar)
            self._detectors[orb.name] = BreakoutDetector(orb)
            if orb.name == "ORB60":
                orb60_just_locked = True

        for orb_name in ORB_NAMES:
            detector = self._detectors.get(orb_name)
            if detector is None:
                continue

            fire = detector.check(bar)
            if fire is None:
                continue

            if orb_name == "ORB20":
                self._handle_orb20_break(fire, events)
            elif orb_name == "ORB30":
                self._handle_orb30_fire(fire, events)
            elif orb_name == "ORB60":
                self._handle_orb60_fire(fire, events)

        if orb60_just_locked and self._orb60_breakout is None:
            self._check_orb60_no_breakout(bar, events)

        self._check_timeout_noon(bar, events)
        return events

    def _check_stale_lock_bar(self, orb: OrbLevels, bar: dict) -> None:
        expected_lock_bar_start = orb.locked_at - timedelta(minutes=5)
        expected_lock_bar_start_ms = int(to_utc(expected_lock_bar_start).timestamp() * 1000)
        observed_ms = int(bar["time"])
        delta_ms = abs(observed_ms - expected_lock_bar_start_ms)

        if delta_ms > LOCK_TOLERANCE_MS:
            logger.warning("STALE_LOCK_BAR: %s arrived %dms late", orb.name, delta_ms)

    def _check_orb60_no_breakout(self, bar: dict, events: list[StackingEvent]) -> None:
        if self._orb60_no_breakout_emitted:
            return

        self._orb60_no_breakout_emitted = True
        events.append(
            StackingEvent(
                kind="ORB60_NO_BREAKOUT",
                direction=self._direction,
                orb=self._orb_builder.locked("ORB60"),
                bar=bar,
                timestamp=self._bar_close_utc(bar),
                state_snapshot=self._make_state_snapshot(),
            )
        )

    def _handle_orb20_break(self, fire: Breakout, events: list[StackingEvent]) -> None:
        if self._orb20_breakout is not None:
            return

        self._direction = fire.direction
        self._orb20_breakout = fire

        if self._is_close_aligned(fire.orb, fire.direction):
            self._closes_aligned += 1

        self._set_tier("HALF")
        events.append(
            StackingEvent(
                kind="ORB20_BREAK",
                direction=fire.direction,
                orb=fire.orb,
                bar=fire.bar,
                timestamp=fire.timestamp,
                state_snapshot=self._make_state_snapshot(),
            )
        )

    def _handle_orb30_fire(self, fire: Breakout, events: list[StackingEvent]) -> None:
        if self._orb20_breakout is None or self._orb30_breakout is not None:
            return

        self._orb30_breakout = fire

        if fire.direction == self._direction:
            if self._is_close_aligned(fire.orb, fire.direction):
                self._closes_aligned += 1

            self._set_tier("NORMAL")
            kind = "ORB30_CONFIRM"
        else:
            kind = "ORB30_OPPOSE"

        events.append(
            StackingEvent(
                kind=kind,
                direction=fire.direction,
                orb=fire.orb,
                bar=fire.bar,
                timestamp=fire.timestamp,
                state_snapshot=self._make_state_snapshot(),
            )
        )

    def _handle_orb60_fire(self, fire: Breakout, events: list[StackingEvent]) -> None:
        if self._orb20_breakout is None or self._orb60_breakout is not None:
            return

        self._orb60_breakout = fire

        if fire.direction == self._direction:
            if self._is_close_aligned(fire.orb, fire.direction):
                self._closes_aligned += 1

            if self._closes_aligned >= 3:
                self._set_tier("DOUBLE")
            else:
                self._set_tier("PLUS")
            kind = "ORB60_CONFIRM"
        else:
            self._set_tier("EXITED")
            kind = "ORB60_OPPOSE"

        events.append(
            StackingEvent(
                kind=kind,
                direction=fire.direction,
                orb=fire.orb,
                bar=fire.bar,
                timestamp=fire.timestamp,
                state_snapshot=self._make_state_snapshot(),
            )
        )

    def _check_timeout_noon(self, bar: dict, events: list[StackingEvent]) -> None:
        if self._timeout_noon_emitted or self._tier != "FLAT":
            return

        if entry_window_closed(bar["start"]):
            self._timeout_noon_emitted = True
            events.append(
                StackingEvent(
                    kind="TIMEOUT_NOON",
                    direction=None,
                    orb=None,
                    bar=bar,
                    timestamp=self._bar_close_utc(bar),
                    state_snapshot=self._make_state_snapshot(),
                )
            )

    def _is_close_aligned(self, orb: OrbLevels, direction: str) -> bool:
        if orb.close_pct is None:
            return False
        if direction == "bull":
            return orb.close_pct >= 0.80
        if direction == "bear":
            return orb.close_pct <= 0.20
        return False

    def _make_state_snapshot(self) -> dict:
        return {
            "stack_tier": self._tier,
            "closes_aligned": self._closes_aligned,
            "direction": self._direction,
        }

    def _bar_close_utc(self, bar: dict) -> datetime:
        return to_utc(bar["start"]) + timedelta(minutes=5)

    def _set_tier(self, new_tier: str) -> None:
        if new_tier == "EXITED":
            self._tier = "EXITED"
            return

        if _TIER_ORDER[new_tier] > _TIER_ORDER.get(self._tier, -1):
            self._tier = new_tier
