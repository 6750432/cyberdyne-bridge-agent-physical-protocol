#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Same-device contention + MCP crash fault injection."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib
MCPDriver = importlib.import_module(
    "agents.mcp-mineflayer.driver.driver").MCPDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer

DEVICE = "mcp://mc/MCPBody"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-path", default="/home/bzys17mintstart/external/mineflayer-mcp")
    ap.add_argument("--node", default="/home/bzys17mintstart/.local/node/bin/node")
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "contention-fault.json"))
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-contend-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "steps": []}
    driver = kernel = a = b = None

    def step(name, ok, detail=None):
        rec = {"name": name, "ok": bool(ok), "detail": detail}
        report["steps"].append(rec)
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)

    try:
        driver = MCPDriver(server_path=args.server_path, node_bin=args.node,
                           username="MCPBody", version="1.21.1",
                           lock_path="/tmp/cbap-mcp-contend.lock",
                           poll_interval=0.4, connect_timeout=45)
        driver.connect()
        kernel = KernelServer(drivers=[driver], socket_path=sock,
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        a = CBAPClient(sock, agent_id="contender-A")
        b = CBAPClient(sock, agent_id="contender-B")
        for c in (a, b):
            c.connect(); c.hello()
        fa = a.open(DEVICE)["payload"]["fd"]
        fb = b.open(DEVICE)["payload"]["fd"]
        step("both sessions open same device", True, {"A": fa, "B": fb})

        la = a.lease(fa, ttl_ms=1500)
        step("A gets lease", la.get("ok"), la.get("payload") or la.get("error"))
        lb = b.lease(fb, ttl_ms=1500)
        step("B gets E_BUSY while A owns lease", lb.get("error", {}).get("code") == "E_BUSY",
             lb.get("error"))
        _, _, ra = a.write(fa, {"channel": "chat", "op": "say",
                                "args": {"text": "contention: A owns"}},
                           deadline_ms=30000)
        step("A write under lease", ra.get("ok"), ra.get("payload") or ra.get("error"))
        rb = b.call("write", {"fd": fb, "frame": {
            "channel": "chat", "op": "say",
            "args": {"text": "contention: B illegal"}}})
        step("B write blocked (no lease)", rb.get("error", {}).get("code") == "E_BUSY",
             rb.get("error"))

        got = {}
        def wait_for_lease():
            got["r"] = b.lease(fb, ttl_ms=30000, wait_ms=5000, timeout=8)

        t = threading.Thread(target=wait_for_lease, daemon=True)
        t.start()
        time.sleep(0.3)
        step("B is queued for lease", t.is_alive(), "wait_ms=5000")
        rel = a.release(fa)
        step("A releases lease voluntarily", rel.get("ok") and rel.get("payload", {}).get("released"),
             rel.get("payload") or rel.get("error"))
        t.join(timeout=5)
        step("B wakes and acquires after release", not t.is_alive() and got.get("r", {}).get("ok"),
             got.get("r", {}).get("payload") if got.get("r") else "timeout")
        _, _, rb2 = b.write(fb, {"channel": "chat", "op": "say",
                                 "args": {"text": "contention: B owns"}},
                            deadline_ms=30000)
        step("B write after fair handoff", rb2.get("ok"), rb2.get("payload") or rb2.get("error"))
        ra2 = a.call("write", {"fd": fa, "frame": {
            "channel": "chat", "op": "say",
            "args": {"text": "contention: A stale"}}})
        step("A write blocked after handoff", ra2.get("error", {}).get("code") == "E_BUSY",
             ra2.get("error"))

        # Crash injection: queue a long move, kill the MCP process, expect E_IO.
        rid = b.request("write", {"fd": fb, "frame": {
            "channel": "body", "op": "move",
            "args": {"p": [200, 68, -200]}}}, deadline_ms=30000)
        ack = b.wait_ack(rid, 5)
        step("pending long move accepted", ack.get("state") == "accepted", ack)
        proc = getattr(driver.client, "proc", None) if driver.client else None
        if proc and proc.poll() is None:
            proc.kill()
            step("killed MCP process", True, {"pid": proc.pid})
        else:
            step("killed MCP process", False, "MCP process not running")
        res = b.wait(rid, 8)
        step("pending write fails after MCP crash",
             res.get("error", {}).get("code") in ("E_IO", "E_TIMEOUT"),
             res.get("error") or res.get("payload"))
        time.sleep(1.5)
        h = driver.health()
        step("driver reports unhealthy after crash", h.get("ok") is False, h)
        report["ok"] = all(x["ok"] for x in report["steps"])
    except Exception as e:
        report["error"] = str(e)
        step("exception", False, str(e))
    finally:
        for c in (a, b):
            try:
                if c: c.close()
            except Exception: pass
        try:
            if kernel: kernel.stop()
        except Exception: pass
        try:
            if driver: driver.close()
        except Exception: pass
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({"ok": report["ok"], "out": args.out,
                          "steps": len(report["steps"]),
                          "errors": [x for x in report["steps"] if not x["ok"]]},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
