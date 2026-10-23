#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe Mindcraft through the line-JSON CBAP adapter.

Assumes Mindcraft is running with MindServer on 8080 and the adapter on
/tmp/mindcraft-cbap.sock. The adapter exposes state, prompt (delivered to
Mindcraft's autonomous planner), and stop.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(ROOT, "kernel")):
    _parent = os.path.dirname(ROOT)
    if _parent == ROOT:
        break
    ROOT = _parent
sys.path.insert(0, ROOT)

from drivers.mc.driver import McDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer

DEVICE = "mc://mind/Mindy"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="/tmp/mindcraft-cbap.sock")
    ap.add_argument("--target", default="18,67,-54")
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "mindcraft-cbap.json"))
    args = ap.parse_args()
    xyz = [float(v) for v in args.target.split(",")]
    tmp = tempfile.mkdtemp(prefix="cbap-mind-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "steps": []}
    driver = kernel = client = None

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)

    try:
        driver = McDriver(args.adapter,
                          device_path=os.path.join(ROOT, "agents/mindcraft/adapter/device.json"),
                          mapping_path=os.path.join(ROOT, "agents/mindcraft/adapter/mapping.json"),
                          connect_timeout=5, reconnect=True)
        driver.connect()
        kernel = KernelServer(drivers=[driver], socket_path=sock,
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        client = CBAPClient(sock, agent_id="mindcraft-probe")
        client.connect(); client.hello()
        devices = client.device_list()["payload"]["devices"]
        step("Mindcraft device visible", devices[0]["device_id"] == DEVICE, devices)
        fd = client.open(DEVICE)["payload"]["fd"]
        step("open", True, fd)
        r = client.read(fd, "body", 3000)
        body = (r.get("payload") or {}).get("frame", {}).get("body") or {}
        before = body.get("pos")
        step("read real Mindcraft state", bool(before), body)
        step("lease", client.lease(fd).get("ok"))

        command = f"!goToCoordinates({xyz[0]:g}, {xyz[1]:g}, {xyz[2]:g}, 1)"
        _, _, res = client.write(fd, {
            "channel": "chat", "op": "prompt",
            "args": {"text": command}}, deadline_ms=30000)
        step("prompt delivered to Mindcraft", res.get("ok"),
             res.get("payload") or res.get("error"))
        moved = None
        end = time.time() + 10
        while time.time() < end:
            r = client.read(fd, "body", 3000)
            body = (r.get("payload") or {}).get("frame", {}).get("body") or {}
            moved = body.get("pos")
            if moved and before and moved != before:
                break
            time.sleep(0.5)
        step("Mindcraft state changed after command",
             bool(moved and before and moved != before),
             {"before": before, "after": moved, "command": command})
        # Estop is a real stop-agent on the adapter. Do not close with a lease
        # held; release first, otherwise Kernel cleanup estops by design.
        est = client.estop(fd, reason="mindcraft-probe")
        step("estop accepted", est.get("ok"), est.get("payload") or est.get("error"))
        time.sleep(2)
        step("Mindcraft offline after estop", driver.health().get("ok") is False,
             driver.health())
        report["before"] = before
        report["after"] = moved
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
                          "before": report.get("before"),
                          "after": report.get("after"),
                          "errors": [x for x in report["steps"] if not x["ok"]]},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
