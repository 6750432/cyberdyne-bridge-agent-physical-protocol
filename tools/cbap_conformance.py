#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the executable CBAP v1 conformance suite against the fake hand.

Usage:
  python3 tools/cbap_conformance.py
  python3 tools/cbap_conformance.py --target fake
  python3 tools/cbap_conformance.py --target fake --list

v0 only supports the fake target; a real-hand target is deliberately not
claimed until the legacy cmdResult id / verification gaps are closed.
"""

from __future__ import annotations

import argparse
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MODULES = [
    "tests.cbap.test_data",
    "tests.cbap.test_gateway",
    "tests.cbap.test_brain_adapter",
    "tests.cbap.test_conformance",
]


def load_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in MODULES:
        suite.addTests(loader.loadTestsFromName(name))
    return suite


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="fake",
                    help="target: fake (only supported in v0)")
    ap.add_argument("--list", action="store_true", help="list cases")
    args = ap.parse_args()
    if args.target not in ("fake", "all"):
        print(f"unsupported target: {args.target} (v0 supports fake only)",
              file=sys.stderr)
        return 2
    suite = load_suite()
    if args.list:
        def walk(x):
            if isinstance(x, unittest.TestSuite):
                for y in x:
                    yield from walk(y)
            else:
                yield x
        for test in walk(suite):
            print(test.id())
        return 0
    print(f"CBAP v1 conformance · target={args.target} · cases={suite.countTestCases()}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"\nCBAP conformance: run={result.testsRun} "
          f"failures={len(result.failures)} errors={len(result.errors)} "
          f"skipped={len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
