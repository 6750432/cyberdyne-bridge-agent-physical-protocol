#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal Alice bridge probe: state -> walk_to -> server reconciliation -> stop."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request


def call(base, path, payload=None, timeout=10):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.load(r)


def pos_of(state):
    p = ((state or {}).get("bot") or {}).get("pos")
    if not p:
        return None
    # BotStateReport renders BlockPos.toShortString(): "x, y, z"
    vals = [float(x) for x in str(p).replace("(", "").replace(")", "").split(",")]
    return vals[:3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8745")
    ap.add_argument("--dx", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=30)
    args = ap.parse_args()
    report = {"ok": False, "steps": []}

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:400]), flush=True)

    try:
        st, health = call(args.base, "/health")
        step("health", st == 200 and health.get("ok"), health)
        st, state = call(args.base, "/state")
        if st == 409:
            step("spawn bot", False, "no bot; POST /spawn first")
            return 1
        before = pos_of(state)
        step("read server state", st == 200 and before is not None,
             {"pos": before, "task": (state.get("task") or {}).get("current")})
        target = [before[0] + args.dx, before[1], before[2]]
        st, task = call(args.base, "/task", {"type": "walk_to", "target": target})
        step("submit walk_to", st in (200, 202) and task.get("accepted"), task)

        after = None
        end = time.time() + args.timeout
        while time.time() < end:
            _, state = call(args.base, "/state")
            after = pos_of(state)
            if after:
                d = math.dist(after, target)
                if d <= 1.5:
                    break
            time.sleep(0.5)
        dist = math.dist(after, target) if after else 999
        step("server fact reached target", dist <= 1.5,
             {"before": before, "after": after, "target": target, "distance": round(dist, 2)})

        st, stop = call(args.base, "/stop", {})
        step("stop", st == 200 and stop.get("ok"), stop)
        _, final = call(args.base, "/state")
        step("final reconciliation", bool(final.get("bot")),
             {"pos": pos_of(final), "task": (final.get("task") or {}).get("current")})
        report["ok"] = all(x["ok"] for x in report["steps"])
    except Exception as e:
        report["error"] = str(e)
        step("exception", False, str(e))
    finally:
        print(json.dumps({"ok": report["ok"], "steps": len(report["steps"]),
                          "errors": [x for x in report["steps"] if not x["ok"]]},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
