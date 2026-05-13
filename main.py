"""Compatibility wrapper for the packaged bot entrypoint."""

from __future__ import annotations

import asyncio
import sys
from importlib import import_module

_impl = import_module("tasty0dte.main")

if __name__ == "__main__":
    try:
        asyncio.run(_impl.main())
    except KeyboardInterrupt:
        pass
else:
    sys.modules[__name__] = _impl

