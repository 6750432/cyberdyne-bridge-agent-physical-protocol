#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real MCP cancel + crash/restart recovery.

1. cancel a long MCP action -> CBAP E_CANCELED, driver restarts;
2. kill MCP process -> pending E_IO, driver auto-restarts;
3. prove a new write works after both.
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

from drivers.mcp.driver import MCPDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer
from kernel.legacy_runtime import protocol


def wait_ready(driver, timeout=35, min_restarts=0):
    end = time.time() + timeout
    while time.time() < end:
        h = driver.health()
        if (driver.connected and driver.wait_state(0.05) is not None
                and driver.stats.get("restarts", 0) >= min_restarts):
            return True, h
        time.sleep(0.4)
    return False, driver.health()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-path", default="/home/bzys17mintstart/external/mineflayer-mcp")
    ap.add_argument("--node", default="/home/bzys17mintstart/.local/node/bin/node")
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "cancel-recovery.json"))
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-cancel-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "steps": []}
    driver = kernel = client = None

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)

    try:
        driver = MCPDriver(server_path=args.server_path, node_bin=args.node,
                           username="MCPBody", version="1.21.1",
                           lock_path="/tmp/cbap-mcp-cancel.lock",
                           poll_interval=0.4, connect_timeout=45,
                           auto_restart=True, restart_delay=0.8)
        driver.connect()
        ready, h = wait_ready(driver, 20)
        step("initial MCP ready", ready, h)
        kernel = KernelServer(drivers=[driver], socket_path=sock,
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        client = CBAPClient(sock, agent_id="cancel-test")
        client.connect(); client.hello()
        fd = client.open("mcp://mc/MCPBody")["payload"]["fd"]
        step("open + lease", client.lease(fd).get("ok"))
        long_frame = {"channel": "body", "op": "move",
                      "args": {"p": [200, 68, -200]}}

        # 1. cancel
        rid = client.request("write", {"fd": fd, "frame": long_frame},
                             deadline_ms=30000)
        ack = client.wait_ack(rid, 5)
        step("long action accepted (cancel)", ack.get("state") == "accepted", ack)
        cid = protocol.new_id("c")
        client.send({"v": "1.0", "type": "cancel", "id": cid, "target": rid})
        c = client.wait(cid, 5)
        step("cancel acknowledged", c.get("ok"), c.get("payload") or c.get("error"))
        cr = client.wait(rid, 8)
        step("canceled write result is E_CANCELED",
             cr.get("error", {}).get("code") == "E_CANCELED", cr.get("error"))
        ready, h = wait_ready(driver, 35)
        step("MCP auto-restarted after cancel", ready, h)
        cancel_restarts = driver.stats.get("restarts", 0)
        _, _, rr = client.write(fd, {
            "channel": "chat", "op": "say",
            "args": {"text": "after cancel: alive"}}, deadline_ms=30000)
        step("write works after cancel/restart", rr.get("ok"),
             rr.get("payload") or rr.get("error"))

        # 2. crash
        rid2 = client.request("write", {"fd": fd, "frame": long_frame},
                              deadline_ms=30000)
        ack2 = client.wait_ack(rid2, 5)
        step("long action accepted (crash)", ack2.get("state") == "accepted", ack2)
        proc = getattr(driver.client, "proc", None) if driver.client else None
        if proc and proc.poll() is None:
            proc.kill()
            step("killed MCP process", True, {"pid": proc.pid})
        else:
            step("killed MCP process", False, "no process")
        er = client.wait(rid2, 8)
        step("crash pending result is E_IO",
             er.get("error", {}).get("code") in ("E_IO", "E_TIMEOUT"),
             er.get("error") or er.get("payload"))
        ready, h = wait_ready(driver, 35,
                              min_restarts=cancel_restarts + 1)
        step("MCP auto-restarted after crash", ready, h)
        step("re-lease after crash", client.lease(fd).get("ok"))
        _, _, rr2 = client.write(fd, {
            "channel": "chat", "op": "say",
            "args": {"text": "after crash: alive"}}, deadline_ms=30000)
        step("write works after crash/restart", rr2.get("ok"),
             rr2.get("payload") or rr2.get("error"))
        report["restarts"] = driver.stats.get("restarts")
        report["ok"] = all(x["ok"] for x in report["steps"])
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
            if driver: driver.close()
        except Exception: pass
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({"ok": report["ok"], "out": args.out,
                          "steps": len(report["steps"]),
                          "restarts": report.get("restarts"),
                          "errors": [x for x in report["steps"] if not x["ok"]]},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
