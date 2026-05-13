"""Compatibility wrapper for :mod:`tasty0dte.monitor`."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tasty0dte.monitor")

