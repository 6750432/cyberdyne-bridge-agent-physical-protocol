#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real heterogeneous concurrency check.

Device A: real MCP Mineflayer agent (external MCP stdio)
Device B: real legacy node/server.js hand (different transport/dialect)

Asserts:
  - both devices visible in one Kernel
  - state and leases are per-device
  - result IDs do not cross devices
  - estop(safe) is per-device
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drivers.mc.driver import McDriver
import importlib
MCPDriver = importlib.import_module(
    "agents.mcp-mineflayer.driver.driver").MCPDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer

MCP_ID = "mcp://mc/MCPBody"
LEGACY_ID = "mc://bot/DeepSeek"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-path", default="/home/bzys17mintstart/external/mineflayer-mcp")
    ap.add_argument("--node", default="/home/bzys17mintstart/.local/node/bin/node")
    ap.add_argument("--legacy-socket", default=os.path.join(ROOT, "cyberdyne.sock"))
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "cbap-concurrency.json"))
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-concurrency-")
    report = {"ok": False, "steps": [], "devices": {}}

    def step(name, ok, detail=None):
        rec = {"name": name, "ok": bool(ok), "detail": detail}
        report["steps"].append(rec)
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)
        return bool(ok)

    mcp = legacy = kernel = client = None
    try:
        step("connect MCP driver", True)
        mcp = MCPDriver(server_path=args.server_path, node_bin=args.node,
                        username="MCPBody", version="1.21.1",
                        lock_path="/tmp/cbap-mcp-concurrency.lock",
                        poll_interval=0.5, connect_timeout=45)
        mcp.connect()
        step("MCP driver connected", mcp.health().get("ok"), mcp.health())

        step("connect legacy driver", True)
        legacy = McDriver(args.legacy_socket,
                          device_path=os.path.join(ROOT, "drivers", "mc", "device.json"),
                          mapping_path=os.path.join(ROOT, "drivers", "mc", "mapping.json"),
                          connect_timeout=5.0, reconnect=True)
        legacy.connect()
        step("legacy driver connected", legacy.health().get("ok"), legacy.health())

        kernel = KernelServer(drivers=[mcp, legacy],
                              socket_path=os.path.join(tmp, "cbap.sock"),
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        client = CBAPClient(os.path.join(tmp, "cbap.sock"), agent_id="concurrency")
        client.connect(); client.hello()
        step("kernel hello", True)

        devices = client.device_list()["payload"]["devices"]
        ids = {d["device_id"] for d in devices}
        report["devices"] = {d["device_id"]: d for d in devices}
        step("two real devices visible", ids == {MCP_ID, LEGACY_ID}, sorted(ids))

        mcp_fd = client.open(MCP_ID)["payload"]["fd"]
        leg_fd = client.open(LEGACY_ID)["payload"]["fd"]
        step("open both devices", True, {"mcp": mcp_fd, "legacy": leg_fd})

        m = client.read(mcp_fd, "body", 3000)
        l = client.read(leg_fd, "body", 3000)
        mp = ((m.get("payload") or {}).get("frame") or {}).get("body", {}).get("pos")
        lp = ((l.get("payload") or {}).get("frame") or {}).get("body", {}).get("pos")
        step("distinct real states", bool(mp) and bool(lp) and mp != lp,
             {"mcp": mp, "legacy": lp})

        step("lease MCP", client.lease(mcp_fd).get("ok"))
        r = client.call("write", {"fd": leg_fd, "frame": {
            "channel": "chat", "op": "say", "args": {"text": "must be blocked"}}})
        step("legacy write blocked while MCP leased", r.get("error", {}).get("code") == "E_BUSY",
             r.get("error"))
        step("lease legacy", client.lease(leg_fd).get("ok"))

        _, _, rm = client.write(mcp_fd, {
            "channel": "chat", "op": "say",
            "args": {"text": "concurrency: MCP side"}}, deadline_ms=30000)
        _, _, rl = client.write(leg_fd, {
            "channel": "chat", "op": "say",
            "args": {"text": "concurrency: legacy side"}}, deadline_ms=30000)
        step("MCP side write", rm.get("ok"), rm.get("payload") or rm.get("error"))
        step("legacy side write", rl.get("ok"), rl.get("payload") or rl.get("error"))
        step("result ids are distinct", rm.get("id") != rl.get("id"),
             {"mcp": rm.get("id"), "legacy": rl.get("id")})

        # per-device safety: estop the legacy fd; MCP must remain writable.
        e = client.estop(leg_fd, reason="concurrency-isolation")
        step("legacy estop", e.get("ok"), e.get("payload"))
        r2 = client.call("write", {"fd": leg_fd, "frame": {
            "channel": "chat", "op": "say", "args": {"text": "blocked"}}})
        step("legacy safe after estop", r2.get("error", {}).get("code") == "E_SAFETY",
             r2.get("error"))
        _, _, rm2 = client.write(mcp_fd, {
            "channel": "chat", "op": "say",
            "args": {"text": "concurrency: MCP still alive"}}, deadline_ms=30000)
        step("MCP unaffected by legacy estop", rm2.get("ok"),
             rm2.get("payload") or rm2.get("error"))

        report["ok"] = all(s["ok"] for s in report["steps"])
    except Exception as e:
        report["error"] = str(e)
        step("exception", False, str(e))
    finally:
        try:
            if client: client.close()
        except Exception: pass
        try:
            if kernel: kernel.stop()
        except Exception: pass
        try:
            if legacy: legacy.close()
        except Exception: pass
        try:
            if mcp: mcp.close()
        except Exception: pass
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({"ok": report["ok"], "out": args.out,
                          "steps": len(report["steps"])}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
