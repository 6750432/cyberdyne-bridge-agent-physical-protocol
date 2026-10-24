#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe one generic MCP device with an independent fact check.

Usage:
  python3 tools/mcp_device_probe.py manifest.json
  python3 tools/mcp_device_probe.py manifest.json \
    --op turn_on --expect '{"on":true}'
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drivers.mcp_device.driver import MCPDeviceDriver  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--op")
    ap.add_argument("--args", default="{}")
    ap.add_argument("--expect")
    ap.add_argument("--tolerance", type=float)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    try:
        driver = MCPDeviceDriver(ns.manifest)
        driver.connect()
    except Exception as e:
        print(json.dumps({"ok": False, "status": "transport_error",
                          "error": str(e)}, ensure_ascii=False))
        return 4
    try:
        tool_ok = None
        if ns.op:
            cmd = {"op": ns.op, "args": json.loads(ns.args)}
            if ns.tolerance is not None:
                cmd["tolerance"] = ns.tolerance
            if ns.expect is not None:
                cmd["expect"] = json.loads(ns.expect)
            tool_ok = driver.send(cmd)
        result = driver.last_verification()
        if result is None:
            result = driver.verify(
            json.loads(ns.expect) if ns.expect else None,
            ns.tolerance,
        )
        result = dict(result)
        result["tool_ok"] = tool_ok
        result["device_id"] = driver.device_id
        result["facts_source"] = driver.facts_spec or None
        print(json.dumps(result, ensure_ascii=False))
        if not ns.json:
            pass
        if result.get("status") == "mismatch":
            return 2
        if result.get("status") == "unverifiable":
            return 3
        return 0 if result.get("ok") else 2
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
