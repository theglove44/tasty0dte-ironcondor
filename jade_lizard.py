"""Compatibility wrapper for :mod:`tasty0dte.jade_lizard`."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tasty0dte.jade_lizard")

