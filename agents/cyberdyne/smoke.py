#!/usr/bin/env python3
"""Local smoke test for the Cyberdyne agent subrepo.

Checks the physical layout and the root compatibility shim. Does not start
Minecraft or the old brain/service.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = [
    ROOT / "agents/cyberdyne/brain/bridge.py",
    ROOT / "agents/cyberdyne/hand/node/server.js",
    ROOT / "agents/cyberdyne/plugins",
    ROOT / "bridge.py",
    ROOT / "node",
    ROOT / "外挂",
    ROOT / "agents/cyberdyne/tools/启动大脑.sh",
    ROOT / "agents/cyberdyne/tools/启动手.sh",
]
for p in checks:
    if not p.exists():
        raise SystemExit(f"missing: {p}")
out = subprocess.run(
    [sys.executable, str(ROOT / "bridge.py"), "--help"],
    cwd=ROOT, capture_output=True, text=True, timeout=20,
)
if out.returncode != 0:
    raise SystemExit(f"bridge.py --help failed: {out.stderr[-500:]}")
print("cyberdyne smoke ok")
