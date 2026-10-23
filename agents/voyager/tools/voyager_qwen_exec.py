#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask local Qwen to generate a small JS snippet, run it via CBAP exec."""

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
CHAT = "qwen exec works"


def qwen(messages):
    body = {"model": "local", "messages": messages, "temperature": 0.1,
            "max_tokens": 260, "stream": False}
    req = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    text = data["choices"][0]["message"].get("content", "")
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
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "voyager-qwen-exec.json"))
    ap.add_argument("--tries", type=int, default=3)
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-vqe-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "model": "local Qwen3-4B", "task": f"jump once and say '{CHAT}'",
              "steps": []}
    driver = kernel = client = None

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("OK  " if ok else "FAIL") + " " + name +
              ("" if detail is None else " :: " + str(detail)[:400]), flush=True)

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
        client = CBAPClient(sock, agent_id="qwen-exec")
        client.connect(); client.hello()
        fd = client.open(DEVICE)["payload"]["fd"]
        step("open", True, fd)
        step("lease", client.lease(fd, ttl_ms=120000).get("ok"))
        r = client.read(fd, "body", 3000)
        body = (r.get("payload") or {}).get("frame", {}).get("body") or {}
        step("initial state", bool(body.get("pos")), body)

        feedback = []
        got_chat = []
        for attempt in range(1, args.tries + 1):
            messages = [
                {"role": "system", "content": f"""You are a strict JSON code planner for one CBAP device.
Return exactly one JSON object:
{{"action":"exec","code":"<javascript>"}}
The code runs inside an async function with `bot` available. It MUST:
1. set jump true,
2. set jump false,
3. call bot.chat("{CHAT}").
Do NOT use waitForTicks, await, loops, or imports.
Allowed: bot.setControlState, bot.chat, JSON.stringify.
Example:
{{"action":"exec","code":"bot.setControlState('jump', true); bot.setControlState('jump', false); bot.chat('qwen exec works');"}}
Return only JSON."""},
                {"role": "user", "content": json.dumps({
                    "state": body, "feedback": feedback[-2:],
                    "attempt": attempt})}]
            try:
                a, model = qwen(messages)
            except Exception as e:
                feedback.append({"error": str(e)})
                continue
            code = str(a.get("code") or "")
            bad = [w for w in ("require", "process", "fs.", "bot.end", "bot.quit", "for(", "while(")
                   if w in code]
            if "waitForTicks" in code or "await " in code:
                bad.append("waitForTicks/await not allowed in this spike")
            if "bot.chat" not in code:
                bad.append("missing bot.chat")
            if a.get("action") != "exec" or not code or bad:
                rec = {"attempt": attempt, "model": model, "action": a,
                       "ok": False, "why": "rejected", "bad": bad}
                report["steps"].append(rec); feedback.append(rec)
                step("Qwen exec rejected", False, rec)
                continue
            rec = {"attempt": attempt, "model": model, "action": a, "code": code}
            _, _, res = client.write(fd, {"channel": "body", "op": "exec",
                                          "args": {"code": code}},
                                     deadline_ms=60000, timeout=60)
            payload = res.get("payload") or {}
            rec["ok"] = bool(res.get("ok"))
            rec["result"] = payload or res.get("error")
            got_chat = payload.get("onChat") or []
            rec["onChat"] = got_chat
            report["steps"].append(rec)
            step("Qwen exec", rec["ok"], rec)
            if CHAT in got_chat:
                break
            feedback.append({"error": "chat not observed", "onChat": got_chat})
            time.sleep(0.5)
        step("exact chat observed", CHAT in got_chat, got_chat)
        report["ok"] = (CHAT in got_chat and
                        any(x.get("ok") and x.get("action", {}).get("action") == "exec"
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
                          "attempts": sum(1 for x in report["steps"] if "attempt" in x),
                          "errors": [x for x in report["steps"] if not x.get("ok")]},
                         ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
