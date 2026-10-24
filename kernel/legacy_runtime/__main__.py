#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the CBAP-U gateway against the legacy Minecraft hand.

Usage:
    python3 -m kernel.legacy_runtime --hand-socket ./cyberdyne.sock \
        --cbap-socket ./cbap.sock

Do NOT run this and bridge.py against the same hand at the same time:
both are clients, and the legacy hand has no per-client arbitration.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

from drivers.mc.driver import McDriver
from .server import KernelServer


def main(argv: list[str] | None = None) -> int:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = argparse.ArgumentParser(description="CBAP v1 gateway for the legacy MC hand")
    p.add_argument("--hand-socket", default=os.path.join(root, "cyberdyne.sock"))
    p.add_argument("--cbap-socket", default=os.path.join(root, "cbap.sock"))
    p.add_argument("--device", default=os.path.join(root, "drivers", "mc", "device.json"))
    p.add_argument("--mapping", default=os.path.join(root, "drivers", "mc", "mapping.json"))
    p.add_argument("--token", default=None,
                   help="CBAP token; generated and written 0600 if omitted")
    p.add_argument("--policy", default=None,
                   help="per-agent capability policy JSON")
    p.add_argument("--allowed-uid", type=int, action="append", default=None,
                   help="allowed local peer uid (repeatable; default current uid)")
    p.add_argument("--max-sessions", type=int, default=64)
    p.add_argument("--max-connections", type=int, default=128)
    p.add_argument("--hello-timeout", type=float, default=2.0)
    p.add_argument("--max-inflight", type=int, default=4)
    p.add_argument("--rate-hz", type=int, default=10)
    p.add_argument("--uid-rate-hz", type=int, default=50)
    p.add_argument("--lease-ttl-ms", type=int, default=30000)
    p.add_argument("--audit", default=os.path.join(root, "logs", "cbap-audit.jsonl"))
    p.add_argument("--audit-mirror", default=None)
    p.add_argument("--audit-remote-url", default=None)
    p.add_argument("--require-independent-facts", action="store_true")
    p.add_argument("--check", action="store_true",
                   help="connect to the hand, print health, then exit")
    a = p.parse_args(argv)

    driver = McDriver(socket_path=a.hand_socket,
                      device_path=a.device,
                      mapping_path=a.mapping)
    try:
        driver.connect()
    except Exception as e:
        print(f"[cbap] cannot connect to hand: {e}", file=sys.stderr)
        return 2

    print(f"[cbap] hand connected: {a.hand_socket}")
    print(f"[cbap] device: {driver.describe().get('device_id')}")
    if a.check:
        print(f"[cbap] health: {driver.health()}")
        driver.close()
        return 0

    server = KernelServer(
        driver, socket_path=a.cbap_socket, token=a.token,
        lease_ttl_ms=a.lease_ttl_ms, audit_path=a.audit,
        policy=a.policy, allowed_uids=set(a.allowed_uid) if a.allowed_uid else None,
        max_sessions=a.max_sessions, max_connections=a.max_connections,
        hello_timeout=a.hello_timeout, max_inflight=a.max_inflight,
        rate_hz=a.rate_hz, uid_rate_hz=a.uid_rate_hz,
        audit_mirror_path=a.audit_mirror,
        audit_remote_url=a.audit_remote_url,
        require_independent_facts=a.require_independent_facts,
    )
    if not server.start():
        print("[cbap] cannot start CBAP server", file=sys.stderr)
        driver.close()
        return 3
    print(f"[cbap] listening: {a.cbap_socket}")
    print("[cbap] do not run bridge.py against the same hand while this is up")

    stop = {"v": False}

    def _sig(_signum, _frame):
        stop["v"] = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    try:
        while not stop["v"]:
            time.sleep(0.5)
    finally:
        server.stop()
        driver.close()
        print("[cbap] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
