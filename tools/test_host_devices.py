#!/usr/bin/env python3
"""Safety tests for the additional host CBAP devices."""
from __future__ import annotations
import sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drivers.host_desktop.devices import (  # noqa: E402
    HostDisplayDriver, HostFilesystemDriver, HostKeyboardDriver, HostMouseDriver,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fs = HostFilesystemDriver(root)
        out = []
        fs.on_result = lambda c, ok, why, extra: out.append((c, ok, why, extra))
        fs.send(fs.map_action({"op": "write_file", "args": {"path": "a.txt", "content": "a"}}))
        assert out[-1][1] and out[-1][3]["bytes"] == 1, out[-1]
        assert fs.describe()["device_id"] == "host://fs"
        assert fs.describe()["type"] == "filesystem"

        for drv, action in (
            (HostMouseDriver(False), "position"),
            (HostKeyboardDriver(False), "type"),
        ):
            calls = []
            drv.on_result = lambda c, ok, why, extra: calls.append((ok, why))
            drv.send(drv.map_action({"op": action, "args": {"text": "x"}}))
            assert calls and not calls[-1][0] and "E_SAFETY" in (calls[-1][1] or ""), calls

        disp = HostDisplayDriver(root, enable=False)
        calls = []
        disp.on_result = lambda c, ok, why, extra: calls.append((ok, why))
        disp.send(disp.map_action({"op": "screenshot", "args": {}}))
        assert calls and not calls[-1][0] and "E_SAFETY" in (calls[-1][1] or ""), calls
    print("host-device safety tests: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
