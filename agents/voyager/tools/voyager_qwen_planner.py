#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local Qwen planner driving Voyager through CBAP. No paid API.

Task: move forward at least once, send a chat message, then done.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

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

LLM_URL = "http://127.0.0.1:8099/v1/chat/completions"
DEVICE = "mc://voyager/bot"
CHAT = "qwen controlled voyager"


def qwen(messages):
    body = {"model": "local", "messages": messages, "temperature": 0.1,
            "max_tokens": 180, "stream": False}
    req = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    text = data["choices"][0]["message"].get("content", "")
    # strip code fences / prose
    if "```" in text:
        text = text.split("```", 1)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```", 1)[0]
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        raise ValueError(text[:300])
    return json.loads(text[i:j + 1]), data.get("model")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "voyager-qwen.json"))
    ap.add_argument("--steps", type=int, default=8)
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-vq-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "model": "local Qwen3-4B",
              "task": f"forward once; say '{CHAT}'; done",
              "steps": []}
    driver = kernel = client = None

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:300]), flush=True)

    try:
        driver = McDriver("/tmp/voyager-cbap.sock",
                          device_path=os.path.join(ROOT, "agents/voyager/adapter/device.json"),
                          mapping_path=os.path.join(ROOT, "agents/voyager/adapter/mapping.json"),
                          connect_timeout=5, reconnect=True)
        driver.connect()
        kernel = KernelServer(drivers=[driver], socket_path=sock,
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        client = CBAPClient(sock, agent_id="qwen-planner")
        client.connect(); client.hello()
        fd = client.open(DEVICE)["payload"]["fd"]
        step("open device", True, fd)
        step("lease", client.lease(fd, ttl_ms=120000).get("ok"))
        r = client.read(fd, "body", 3000)
        body = (r.get("payload") or {}).get("frame", {}).get("body") or {}
        before = body.get("pos")
        step("initial state", bool(before), before)

        move_done = False
        chat_done = False
        history = []

        def current_state():
            r = client.read(fd, "body", 3000)
            b = (r.get("payload") or {}).get("frame", {}).get("body") or {}
            return {"pos": b.get("pos"), "hp": b.get("hp"),
                    "food": b.get("food"), "acting": b.get("acting")}

        for turn in range(1, args.steps + 1):
            st = current_state()
            messages = [
                {"role": "system", "content": f"""You are a strict JSON planner for one CBAP device.
Device: {DEVICE}
Goal: move forward at least once, then send exactly "{CHAT}", then done.
Allowed actions (one per turn):
{{"action":"forward"}}
{{"action":"say","text":"..."}}
{{"action":"done"}}
Never use another device. Do not explain. Return only one JSON object."""},
                {"role": "user", "content": json.dumps({
                    "state": st, "move_done": move_done,
                    "chat_done": chat_done, "history": history[-4:],
                }, ensure_ascii=False)}]
            try:
                a, model = qwen(messages)
            except Exception as e:
                history.append({"turn": turn, "error": str(e)})
                continue
            act = a.get("action")
            rec = {"turn": turn, "model": model, "action": a}
            if act == "done":
                if move_done and chat_done:
                    rec["ok"] = True
                    report["steps"].append(rec); history.append(rec)
                    step("Qwen chose done", True, rec)
                    break
                rec["ok"] = False; rec["error"] = "GOAL_GATE"
                report["steps"].append(rec); history.append(rec)
                step("Qwen done rejected by goal gate", False, rec)
                continue
            if act == "forward":
                _, _, res = client.write(fd, {"channel": "body", "op": "forward",
                                              "args": {}}, deadline_ms=30000, timeout=30)
                rec["ok"] = bool(res.get("ok"))
                rec["result"] = res.get("payload") or res.get("error")
                if rec["ok"]:
                    move_done = True
                report["steps"].append(rec); history.append(rec)
                step("Qwen forward", rec["ok"], rec)
                time.sleep(0.5)
                continue
            if act == "say":
                text = str(a.get("text") or CHAT)
                _, _, res = client.write(fd, {"channel": "chat", "op": "say",
                                              "args": {"text": text}},
                                         deadline_ms=30000, timeout=30)
                rec["ok"] = bool(res.get("ok"))
                rec["result"] = res.get("payload") or res.get("error")
                if rec["ok"]:
                    chat_done = True
                report["steps"].append(rec); history.append(rec)
                step("Qwen say", rec["ok"], rec)
                time.sleep(0.5)
                continue
            rec["ok"] = False; rec["error"] = "unknown action"
            report["steps"].append(rec); history.append(rec)
            step("unknown action", False, rec)

        final = current_state()
        after = final.get("pos")
        report["before"] = before
        report["after"] = after
        report["move_done"] = move_done
        report["chat_done"] = chat_done
        step("move observed", bool(before and after and before != after),
             {"before": before, "after": after})
        step("chat issued", chat_done, CHAT)
        report["ok"] = (move_done and chat_done and before != after
                        and any(x.get("ok") and x.get("action", {}).get("action") == "done"
                                for x in report["steps"] if isinstance(x, dict)))
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
                          "before": report.get("before"), "after": report.get("after"),
                          "move_done": report.get("move_done"),
                          "chat_done": report.get("chat_done")},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
