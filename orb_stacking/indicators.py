"""
Technical indicators for ORB Stacking strategy.

Streaming-friendly: feed bars one at a time via update().
No external dependencies beyond stdlib math.
"""
import math


class ATR:
    """Average True Range using Wilder smoothing."""

    def __init__(self, period: int = 14):
        self.period = period
        self._prev_close: float | None = None
        self._tr_values: list[float] = []
        self._atr: float | None = None
        self._count: int = 0

    def update(self, bar: dict) -> float | None:
        """Process one OHLC bar. Returns current ATR or None if < period bars."""
        h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])

        if self._prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - self._prev_close), abs(l - self._prev_close))

        self._prev_close = c
        self._count += 1

        if self._atr is None:
            self._tr_values.append(tr)
            if len(self._tr_values) == self.period:
                self._atr = sum(self._tr_values) / self.period
                self._tr_values = []
                return self._atr
            return None
        else:
            self._atr = ((self._atr * (self.period - 1)) + tr) / self.period
            return self._atr

    def is_ready(self) -> bool:
        return self._atr is not None

    @property
    def value(self) -> float | None:
        return self._atr

    def reset(self):
        self.__init__(self.period)

    def to_dict(self) -> dict:
        return {
            'period': self.period,
            'prev_close': self._prev_close,
            'tr_values': list(self._tr_values),
            'atr': self._atr,
            'count': self._count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ATR':
        obj = cls(d['period'])
        obj._prev_close = d['prev_close']
        obj._tr_values = d['tr_values']
        obj._atr = d['atr']
        obj._count = d['count']
        return obj
