#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voyager minimal spike: Python 3.10 -> Voyager HTTP bridge -> MC 1.19.2.

No GPT-4, no curriculum, no skill library. Only:
  /start  hard reset with a small starting inventory
  /step   one hand-written JavaScript task
  /stop
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request


def post(base: str, path: str, payload: dict, timeout: float = 60.0):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    data = json.loads(body)
    # Voyager's bridge res.json(bot.observe()) is sometimes double-encoded
    # (a JSON string containing the event array).
    if isinstance(data, str):
        data = json.loads(data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:3000")
    ap.add_argument("--mc-port", type=int, default=25565)
    ap.add_argument("--out", default="logs/voyager-spike.json")
    args = ap.parse_args()
    code = (
        "await bot.waitForTicks(10);\n"
        "bot.setControlState('forward', true);\n"
        "await bot.waitForTicks(20);\n"
        "bot.setControlState('forward', false);\n"
        "bot.chat('voyager spike: manual task OK');"
    )
    report = {"ok": False, "python": __import__("sys").version.split()[0],
              "bridge": args.bridge, "mc_port": args.mc_port,
              "code": code, "steps": []}

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)

    try:
        t0 = time.time()
        started = post(args.bridge, "/start", {
            "port": args.mc_port,
            "reset": "hard",
            "inventory": {"oak_log": 3},
            "waitTicks": 20,
        }, timeout=60)
        obs = started[0][1] if started and started[0][0] == "observe" else {}
        st = obs.get("status") or {}
        start_pos = st.get("position")
        step("bridge /start connected", bool(st.get("name")), {
            "name": st.get("name"), "position": start_pos,
            "health": st.get("health"), "inventory": obs.get("inventory"),
            "elapsed_s": round(time.time() - t0, 2),
        })

        events = post(args.bridge, "/step", {"code": code, "programs": ""},
                      timeout=60)
        chats = [e[1].get("onChat") for e in events if e and e[0] == "onChat"]
        last = events[-1][1] if events else {}
        last_pos = (last.get("status") or {}).get("position")
        step("manual JS /step executed", bool(events),
             {"onChat": chats, "elapsedTime": (last.get("status") or {}).get("elapsedTime")})
        step("manual movement changed position",
             bool(start_pos and last_pos and start_pos != last_pos),
             {"before": start_pos, "after": last_pos})
        step("manual chat observed", "voyager spike: manual task OK" in chats, chats)
        report["events"] = events[-2:]
        report["ok"] = all(x["ok"] for x in report["steps"])
    except Exception as e:
        report["error"] = str(e)
        step("exception", False, str(e))
    finally:
        try:
            post(args.bridge, "/stop", {}, timeout=10)
            step("bridge /stop", True)
        except Exception as e:
            step("bridge /stop", False, str(e))
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps({"ok": report["ok"], "out": args.out,
                          "steps": len(report["steps"]),
                          "python": report["python"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
