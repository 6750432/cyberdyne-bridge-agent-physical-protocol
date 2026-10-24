#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host-side CBAP test bridge for the CBAP OS VM.

It exposes one allowlisted device, host://desktop, over:
  - a local UDS (for host-side checks)
  - TCP 127.0.0.1:8765 (for QEMU user-net guest reaching 10.0.2.2:8765)

The only write action is write_file under ~/Desktop/CBAP-Host-Test. No shell,
no arbitrary path, no executable creation.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drivers.host_desktop.driver import HostDesktopDriver  # noqa: E402
from drivers.host_desktop.devices import (  # noqa: E402
    HostDisplayDriver, HostFilesystemDriver, HostKeyboardDriver, HostMouseDriver,
)
from kernel.legacy_runtime.server import KernelServer  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CBAP host desktop test bridge")
    ap.add_argument("--root", default=str(Path.home() / "Desktop" / "CBAP-Host-Test"))
    ap.add_argument("--socket", default="/tmp/cbap-host-test/cbap.sock")
    ap.add_argument("--tcp-host", default="127.0.0.1")
    ap.add_argument("--tcp-port", type=int, default=8765)
    ap.add_argument("--no-tcp", action="store_true")
    ap.add_argument("--token", default=os.environ.get("CBAP_HOST_TOKEN", "cbap-host-test-2026"))
    ap.add_argument("--audit", default="/tmp/cbap-host-test/audit.jsonl")
    ap.add_argument("--no-display", action="store_true",
                    help="do not expose host://display screenshot capture")
    ap.add_argument("--enable-input", action="store_true",
                    help="opt in to X11/XWayland mouse/keyboard devices")
    a = ap.parse_args(argv)

    Path(a.socket).parent.mkdir(parents=True, exist_ok=True)
    Path(a.audit).parent.mkdir(parents=True, exist_ok=True)
    driver = HostDesktopDriver(a.root)
    drivers = [
        driver,
        HostFilesystemDriver(a.root),
        HostDisplayDriver(a.root, enable=not a.no_display),
        HostMouseDriver(enable=a.enable_input),
        HostKeyboardDriver(enable=a.enable_input),
    ]
    server = KernelServer(
        drivers=drivers,
        socket_path=a.socket,
        kernel_id="cbap-host-desktop",
        token=a.token,
        audit_path=a.audit,
        allowed_uids={os.getuid()},
        tcp_host=None if a.no_tcp else a.tcp_host,
        tcp_port=None if a.no_tcp else a.tcp_port,
        max_sessions=8,
        max_connections=16,
        max_inflight=2,
        rate_hz=5,
        uid_rate_hz=10,
    )
    if not server.start():
        print("cannot start host bridge", file=sys.stderr)
        return 2
    status = {
        "ready": True,
        "devices": [d.describe().get("device_id") for d in drivers],
        "root": str(driver.root),
        "socket": str(Path(a.socket).resolve()),
        "tcp": None if a.no_tcp else f"{a.tcp_host}:{server.tcp_port}",
        "token": a.token,
    }
    Path("/tmp/cbap-host-test/status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False), flush=True)

    stop = {"v": False}

    def _sig(_s, _f):
        stop["v"] = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    try:
        while not stop["v"]:
            time.sleep(0.5)
    finally:
        server.stop()
        driver.close()
        print("host bridge stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
