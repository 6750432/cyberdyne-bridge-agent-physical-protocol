#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 wrapper boundary test."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "agents/cyberdyne/brain/bridge_cbap.py"


class BridgeCBAPWrapperTest(unittest.TestCase):
    def test_install_swaps_only_interface(self):
        spec = importlib.util.spec_from_file_location("bridge_cbap_test", WRAPPER)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        legacy = mod.legacy
        original = legacy.接线口
        try:
            mod.install()
            self.assertIs(legacy.接线口, mod.CBAPHandAdapter)
            self.assertEqual(legacy.ROOT, str(ROOT / "agents/cyberdyne"))
            self.assertTrue(WRAPPER.exists())
        finally:
            legacy.接线口 = original


if __name__ == "__main__":
    unittest.main()
