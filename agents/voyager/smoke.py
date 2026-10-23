#!/usr/bin/env python3
"""Local smoke test for the Voyager bridge subrepo."""
from __future__ import annotations

import json
from pathlib import Path

base = Path(__file__).resolve().parent
for p in [base / "adapter/adapter.mjs",
          base / "adapter/device.json",
          base / "adapter/mapping.json"]:
    if not p.exists():
        raise SystemExit(f"missing: {p}")
json.loads((base / "adapter/device.json").read_text())
json.loads((base / "adapter/mapping.json").read_text())
print("voyager smoke ok")
