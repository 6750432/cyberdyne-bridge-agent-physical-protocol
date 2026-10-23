#!/usr/bin/env python3
"""Local smoke test for the MCP Mineflayer subrepo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for p in [Path(__file__).parent / "driver/driver.py",
          Path(__file__).parent / "driver/device.json",
          Path(__file__).parent / "driver/mapping.json"]:
    if not p.exists():
        raise SystemExit(f"missing: {p}")
import importlib  # noqa: E402
MCPDriver = importlib.import_module(
    "agents.mcp-mineflayer.driver.driver").MCPDriver
assert MCPDriver.__name__ == "MCPDriver"
json.loads((Path(__file__).parent / "driver/device.json").read_text())
json.loads((Path(__file__).parent / "driver/mapping.json").read_text())
print("mcp-mineflayer smoke ok")
