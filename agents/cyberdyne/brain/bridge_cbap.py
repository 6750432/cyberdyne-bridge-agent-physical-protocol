#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Legacy Cyberdyne brain, executing through CBAP instead of the direct hand.

This is the M4 migration bridge, not the old `bridge.py` main chain:

    legacy brain classes in bridge.py
              |
        CBAPHandAdapter
              |
          CBAP Kernel
              |
          McDriver / hand

The original `bridge.py` remains byte-for-byte pinned.  This wrapper replaces
only its `接线口` class at runtime, then calls the normal `主()` loop.  It is
intentionally explicit: the old direct path is not silently changed.

Usage:
    python3 agents/cyberdyne/brain/bridge_cbap.py [bridge args...]

Environment:
    CBAP_SOCKET   default <repo>/cbap.sock
    CBAP_DEVICE   default mc://bot/DeepSeek
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bridge as legacy  # noqa: E402
from kernel.legacy_runtime.brain_adapter import CBAPHandAdapter  # noqa: E402


def install() -> None:
    # bridge.py uses its own __file__ when imported from the physical subrepo;
    # point its config/log paths at the repository root, matching the shim.
    legacy.ROOT = str(ROOT)
    legacy.接线口 = CBAPHandAdapter


def main() -> None:
    install()
    legacy.主()


if __name__ == "__main__":
    main()
