"""
Technical indicators for Tag N Turn strategy.

Streaming-friendly: feed bars one at a time via update().
No external dependencies beyond stdlib math/collections.
"""
import math
from collections import deque


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


class BollingerBands:
    """Bollinger Bands with rolling SMA and population standard deviation."""

    def __init__(self, period: int = 30, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std
        self._closes: deque = deque(maxlen=period)

    def update(self, bar: dict) -> dict | None:
        """Process one bar. Returns {upper, lower, middle, width} or None."""
        self._closes.append(float(bar['close']))

        if len(self._closes) < self.period:
            return None

        closes = list(self._closes)
        middle = sum(closes) / self.period
        variance = sum((c - middle) ** 2 for c in closes) / self.period
        std = math.sqrt(variance)

        upper = middle + self.num_std * std
        lower = middle - self.num_std * std

        return {
            'upper': upper,
            'lower': lower,
            'middle': middle,
            'width': upper - lower,
        }

    def is_ready(self) -> bool:
        return len(self._closes) >= self.period

    @property
    def value(self) -> dict | None:
        if not self.is_ready():
            return None
        closes = list(self._closes)
        middle = sum(closes) / self.period
        variance = sum((c - middle) ** 2 for c in closes) / self.period
        std = math.sqrt(variance)
        upper = middle + self.num_std * std
        lower = middle - self.num_std * std
        return {'upper': upper, 'lower': lower, 'middle': middle, 'width': upper - lower}

    def reset(self):
        self.__init__(self.period, self.num_std)

    def to_dict(self) -> dict:
        return {
            'period': self.period,
            'num_std': self.num_std,
            'closes': list(self._closes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'BollingerBands':
        obj = cls(d['period'], d['num_std'])
        for c in d['closes']:
            obj._closes.append(c)
        return obj


class MACDV:
    """MACD-V: volatility-normalized MACD.

    Formula: (EMA_fast - EMA_slow) / ATR * 100
    Tracks extreme zones (|value| >= 140) and traffic light status
    based on bars since last exit from the extreme zone.
    """

    def __init__(self, fast: int = 12, slow: int = 26, atr_period: int = 14):
        self.fast = fast
        self.slow = slow
        self.atr_period = atr_period
        self._k_fast = 2.0 / (fast + 1)
        self._k_slow = 2.0 / (slow + 1)
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._atr = ATR(atr_period)
        self._count: int = 0

        self._fast_seed: list[float] = []
        self._slow_seed: list[float] = []

        self._was_extreme: bool = False
        self._bars_since_extreme_exit: int | None = None
        self._extreme_ever: bool = False

    def update(self, bar: dict) -> dict | None:
        """Process one bar. Returns result dict or None if not ready."""
        close = float(bar['close'])
        self._count += 1

        atr_val = self._atr.update(bar)

        if self._ema_fast is None:
            self._fast_seed.append(close)
            if len(self._fast_seed) == self.fast:
                self._ema_fast = sum(self._fast_seed) / self.fast
                self._fast_seed = []
        else:
            self._ema_fast = close * self._k_fast + self._ema_fast * (1 - self._k_fast)

        if self._ema_slow is None:
            self._slow_seed.append(close)
            if len(self._slow_seed) == self.slow:
                self._ema_slow = sum(self._slow_seed) / self.slow
                self._slow_seed = []
        else:
            self._ema_slow = close * self._k_slow + self._ema_slow * (1 - self._k_slow)

        if self._ema_fast is None or self._ema_slow is None or atr_val is None or atr_val == 0:
            return None

        value = ((self._ema_fast - self._ema_slow) / atr_val) * 100
        is_extreme = abs(value) >= 140

        if is_extreme:
            self._was_extreme = True
            self._extreme_ever = True
            self._bars_since_extreme_exit = 0
        else:
            if self._was_extreme:
                self._was_extreme = False
                self._bars_since_extreme_exit = 1
            elif self._bars_since_extreme_exit is not None:
                self._bars_since_extreme_exit += 1

        extreme_status = self._compute_traffic_light(is_extreme)

        return {
            'value': value,
            'is_extreme': is_extreme,
            'bars_since_extreme_exit': self._bars_since_extreme_exit,
            'extreme_status': extreme_status,
        }

    def _compute_traffic_light(self, is_extreme: bool) -> str:
        if not self._extreme_ever:
            return 'NONE'
        if is_extreme:
            return 'RED'
        if self._bars_since_extreme_exit is not None:
            if self._bars_since_extreme_exit <= 10:
                return 'RED'
            elif self._bars_since_extreme_exit <= 15:
                return 'AMBER'
            elif self._bars_since_extreme_exit <= 30:
                return 'GREEN'
        return 'NONE'

    def is_ready(self) -> bool:
        return (self._ema_fast is not None
                and self._ema_slow is not None
                and self._atr.is_ready())

    @property
    def value(self) -> float | None:
        if not self.is_ready() or self._atr.value == 0:
            return None
        return ((self._ema_fast - self._ema_slow) / self._atr.value) * 100

    def reset(self):
        self.__init__(self.fast, self.slow, self.atr_period)

    def to_dict(self) -> dict:
        return {
            'fast': self.fast,
            'slow': self.slow,
            'atr_period': self.atr_period,
            'ema_fast': self._ema_fast,
            'ema_slow': self._ema_slow,
            'fast_seed': self._fast_seed,
            'slow_seed': self._slow_seed,
            'atr': self._atr.to_dict(),
            'count': self._count,
            'was_extreme': self._was_extreme,
            'bars_since_extreme_exit': self._bars_since_extreme_exit,
            'extreme_ever': self._extreme_ever,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'MACDV':
        obj = cls(d['fast'], d['slow'], d['atr_period'])
        obj._ema_fast = d['ema_fast']
        obj._ema_slow = d['ema_slow']
        obj._fast_seed = d['fast_seed']
        obj._slow_seed = d['slow_seed']
        obj._atr = ATR.from_dict(d['atr'])
        obj._count = d['count']
        obj._was_extreme = d['was_extreme']
        obj._bars_since_extreme_exit = d['bars_since_extreme_exit']
        obj._extreme_ever = d['extreme_ever']
        return obj
