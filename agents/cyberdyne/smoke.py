#!/usr/bin/env python3
"""Local smoke test for the Cyberdyne agent subrepo.

Checks physical layout and the M4 CBAP wrapper. Does not start Minecraft,
the Kernel, or the old direct brain service.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = [
    ROOT / "agents/cyberdyne/brain/bridge.py",
    ROOT / "agents/cyberdyne/brain/bridge_cbap.py",
    ROOT / "agents/cyberdyne/hand/node/server.js",
    ROOT / "agents/cyberdyne/plugins",
    ROOT / "agents/cyberdyne/config.json",
    ROOT / "agents/cyberdyne/tools/启动大脑.sh",
    ROOT / "agents/cyberdyne/tools/启动大脑-cbap.sh",
    ROOT / "agents/cyberdyne/tools/启动手.sh",
]
for p in checks:
    if not p.exists():
        raise SystemExit(f"missing: {p}")
out = subprocess.run(
    [sys.executable, str(ROOT / "agents/cyberdyne/brain/bridge_cbap.py"), "--help"],
    cwd=ROOT, capture_output=True, text=True, timeout=20,
)
if out.returncode != 0:
    raise SystemExit(f"bridge_cbap.py --help failed: {out.stderr[-500:]}")
# The direct root shims must not come back.
for legacy in ("bridge.py", "node", "外挂", "config.json"):
    if (ROOT / legacy).exists():
        raise SystemExit(f"legacy root shim still present: {legacy}")
print("cyberdyne smoke ok")
