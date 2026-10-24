#!/usr/bin/env python3
"""Safety checks for the CBAP host-desktop test driver (no root required)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drivers.host_desktop.driver import HostDesktopDriver  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "desktop"
        drv = HostDesktopDriver(root)
        results = []

        def call(frame):
            results.clear()
            drv.on_result = lambda cmd, ok, why, extra: results.append((ok, why, extra))
            drv.send(drv.map_action(frame))
            return results[-1]

        ok, why, extra = call({"op": "write_file", "args": {
            "path": "hello.txt", "content": "hello"}})
        assert ok and extra["bytes"] == 5, (ok, why, extra)
        assert (root / "hello.txt").read_text() == "hello"

        ok, why, extra = call({"op": "stat", "args": {"path": "hello.txt"}})
        assert ok and extra["sha256"].startswith("2cf24dba"), (ok, extra)

        for bad in ("../escape.txt", "/etc/passwd", "a/../../escape"):
            ok, why, _ = call({"op": "write_file", "args": {"path": bad, "content": "x"}})
            assert not ok and any(code in (why or "") for code in ("E_PERM", "E_INVAL")), (bad, ok, why)

        # A symlink under the allowlist must not become an escape hatch.
        os.symlink("/etc", root / "link")
        ok, why, _ = call({"op": "write_file", "args": {
            "path": "link/passwd", "content": "x"}})
        assert not ok and "E_PERM" in (why or ""), (ok, why)

        ok, why, _ = call({"op": "write_file", "args": {
            "path": "big.txt", "content": "x" * (drv.MAX_BYTES + 1)}})
        assert not ok, (ok, why)
        assert drv.estop() is True
        ok, why, _ = call({"op": "ping", "args": {}})
        assert not ok and "E_SAFETY" in (why or ""), (ok, why)
    print("host-desktop safety tests: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
