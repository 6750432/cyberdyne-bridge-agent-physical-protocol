#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe the Voyager 1.19.2 bridge through CBAP (no LLM)."""

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

DEVICE = "mc://voyager/bot"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="/tmp/voyager-cbap.sock")
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "voyager-cbap.json"))
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-voyager-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "steps": []}
    driver = kernel = client = None

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)

    try:
        driver = McDriver(args.adapter,
                          device_path=os.path.join(ROOT, "agents/voyager/adapter/device.json"),
                          mapping_path=os.path.join(ROOT, "agents/voyager/adapter/mapping.json"),
                          connect_timeout=5, reconnect=True)
        driver.connect()
        kernel = KernelServer(drivers=[driver], socket_path=sock,
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        client = CBAPClient(sock, agent_id="voyager-probe")
        client.connect(); client.hello()
        devices = client.device_list()["payload"]["devices"]
        step("Voyager device visible", devices[0]["device_id"] == DEVICE, devices)
        fd = client.open(DEVICE)["payload"]["fd"]
        r = client.read(fd, "body", 3000)
        before = ((r.get("payload") or {}).get("frame") or {}).get("body", {}).get("pos")
        step("read state", bool(before), before)
        step("lease", client.lease(fd).get("ok"))

        _, _, rf = client.write(fd, {"channel": "body", "op": "forward",
                                     "args": {}}, deadline_ms=30000, timeout=30)
        step("forward under lease", rf.get("ok"), rf.get("payload") or rf.get("error"))
        after = None
        end = time.time() + 10
        while time.time() < end:
            r = client.read(fd, "body", 3000)
            after = ((r.get("payload") or {}).get("frame") or {}).get("body", {}).get("pos")
            if after and before and after != before:
                break
            time.sleep(0.4)
        step("position changed", bool(before and after and before != after),
             {"before": before, "after": after})

        _, _, rs = client.write(fd, {"channel": "chat", "op": "say",
                                     "args": {"text": "voyager cbap works"}},
                                deadline_ms=30000, timeout=30)
        step("say under lease", rs.get("ok"), rs.get("payload") or rs.get("error"))
        est = client.estop(fd, reason="voyager-probe")
        step("estop", est.get("ok"), est.get("payload") or est.get("error"))
        time.sleep(1.5)
        step("offline after estop", driver.health().get("ok") is False, driver.health())
        report["before"] = before
        report["after"] = after
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
                          "before": report.get("before"), "after": report.get("after"),
                          "errors": [x for x in report["steps"] if not x["ok"]]},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
