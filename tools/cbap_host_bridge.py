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
import secrets
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


def _is_loopback_host(host: str) -> bool:
    h = str(host).strip().lower()
    if h in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        import ipaddress
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CBAP host desktop test bridge")
    ap.add_argument("--root", default=str(Path.home() / "Desktop" / "CBAP-Host-Test"))
    ap.add_argument("--socket", default="/tmp/cbap-host-test/cbap.sock")
    ap.add_argument("--tcp-host", default="127.0.0.1")
    ap.add_argument("--tcp-port", type=int, default=8765)
    ap.add_argument("--no-tcp", action="store_true")
    ap.add_argument("--token", default=os.environ.get("CBAP_HOST_TOKEN"),
                    help="test token; if omitted a random token is generated")
    ap.add_argument("--audit", default="/tmp/cbap-host-test/audit.jsonl")
    ap.add_argument("--no-display", action="store_true",
                    help="do not expose host://display screenshot capture")
    ap.add_argument("--enable-input", action="store_true",
                    help="opt in to mouse/keyboard devices")
    ap.add_argument("--input-backend", choices=("x11", "portal"),
                    default="x11",
                    help="input backend: X11/XWayland or native Wayland portal")
    ap.add_argument("--allow-unisolated-input", action="store_true",
                    help="explicitly allow bare X11 input (high risk)")
    ap.add_argument("--require-isolated-input", action="store_true",
                    help="refuse unisolated X11 input; use with --input-backend portal")
    ap.add_argument("--allow-public", action="store_true",
                    help="explicitly allow a non-loopback TCP bind (high risk)")
    ap.add_argument("--strict-contracts", action="store_true",
                    help="refuse legacy descriptors without declared contracts")
    a = ap.parse_args(argv)

    if a.enable_input and a.input_backend == "x11" and not a.allow_unisolated_input:
        ap.error("bare X11 input requires --allow-unisolated-input; "
                 "use --input-backend portal --require-isolated-input "
                 "for the native-Wayland path")
    if not a.no_tcp and not _is_loopback_host(a.tcp_host) and not a.allow_public:
        ap.error("non-loopback --tcp-host requires --allow-public")
    a.token = a.token or secrets.token_urlsafe(32)

    Path(a.socket).parent.mkdir(parents=True, exist_ok=True)
    Path(a.audit).parent.mkdir(parents=True, exist_ok=True)
    driver = HostDesktopDriver(a.root)
    drivers = [
        driver,
        HostFilesystemDriver(a.root),
        HostDisplayDriver(a.root, enable=not a.no_display),
        HostMouseDriver(enable=a.enable_input, backend=a.input_backend),
        HostKeyboardDriver(enable=a.enable_input, backend=a.input_backend),
    ]
    allowed = ["host://desktop", "host://fs", "host://display"]
    approvals = {"devices": [], "ops": []}
    if a.enable_input:
        allowed += ["host://input/mouse", "host://input/keyboard"]
        approvals = {
            "devices": ["host://input/*"],
            "ops": ["click", "type", "key"],
            "required_approvals": 1,
            "ttl_ms": 30000,
        }
    server = KernelServer(
        drivers=drivers,
        socket_path=a.socket,
        kernel_id="cbap-host-desktop",
        token=a.token,
        audit_path=a.audit,
        allowed_uids={os.getuid()},
        tcp_host=None if a.no_tcp else a.tcp_host,
        tcp_port=None if a.no_tcp else a.tcp_port,
        allow_public_bind=a.allow_public,
        max_sessions=8,
        max_connections=16,
        max_inflight=2,
        rate_hz=5,
        uid_rate_hz=10,
        require_isolated_input=a.require_isolated_input,
        strict_contracts=a.strict_contracts,
        policy={
            "default": {
                "devices": allowed,
                "capabilities": ["read", "write", "lease", "estop"],
            },
            "agents": {},
            "approvals": approvals,
        },
    )
    if not server.start():
        print("cannot start host bridge", file=sys.stderr)
        return 2
    token_file = Path(str(Path(a.socket).resolve()) + ".token")
    status = {
        "ready": True,
        "devices": [d.describe().get("device_id") for d in drivers],
        "root": str(driver.root),
        "socket": str(Path(a.socket).resolve()),
        "tcp": None if a.no_tcp else f"{a.tcp_host}:{server.tcp_port}",
        # Never print or persist the token in a world-readable status file.
        "token_file": str(token_file),
        "input_backend": a.input_backend if a.enable_input else None,
        "public_bind": bool(a.allow_public),
    }
    status_path = Path(a.socket).parent / "status.json"
    tmp = status_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, status_path)
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
