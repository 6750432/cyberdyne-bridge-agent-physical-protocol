#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External LLM autonomy probe.

This is deliberately not part of the CBAP kernel. It is an independent
OpenAI-compatible client that talks to the local Qwen server, decides one
action per turn, and executes that action through the CBAP dashboard API.

The LLM is the planner. The dashboard/Kernel is the executor/supervisor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = "http://127.0.0.1:8123"
LLM = "http://127.0.0.1:8099/v1/chat/completions"


def post(url: str, obj: dict, timeout: float = 120.0):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code,
                "body": e.read().decode("utf-8", "replace")[:800]}


def get(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def dashboard_state():
    return get(DASH + "/api/state")


def observe(target: str, **kw):
    body = {"target": target}
    body.update(kw)
    return post(DASH + "/api/observe", body)


def act(frame: dict):
    return post(DASH + "/api/act", {"frame": frame}, timeout=120)


def call_llm(messages: list[dict], max_tokens: int = 220) -> tuple[str, str]:
    body = {
        "model": "local",
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    r = post(LLM, body, timeout=90)
    if "choices" not in r:
        raise RuntimeError(f"LLM call failed: {str(r)[:500]}")
    text = r["choices"][0]["message"].get("content") or ""
    model = str(r.get("model") or "local")
    return text, model


def parse_action(text: str) -> dict:
    t = text.strip()
    if "```" in t:
        t = t.split("```", 1)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.split("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        raise ValueError(f"no JSON object in: {text[:300]}")
    return json.loads(t[i:j + 1])


def compact_state() -> dict:
    s = dashboard_state()
    st = s.get("state") or {}
    logs = (observe("blocks", blockTypes=["oak_log"],
                    maxDistance=64, maxCount=10).get("result") or {}).get("blocks") or []
    ents = (observe("entities", maxDistance=24).get("result") or {}).get("entities") or []
    drops = [e for e in ents if e.get("type") == "item"]
    return {
        "goal": "collect at least 3 oak_log in inventory",
        "bot": {
            "pos": st.get("pos"),
            "items": st.get("items") or {},
            "hp": st.get("hp"),
            "food": st.get("food"),
        },
        "oak_logs": [
            {"pos": b.get("position"), "distance": b.get("distance")}
            for b in logs[:8]
        ],
        "item_drops": [
            {"pos": e.get("position"), "distance": e.get("distance")}
            for e in drops[:6]
        ],
    }


def system_prompt() -> str:
    return """You are an external autonomous Minecraft planner. You are NOT the executor.
The CBAP supervisor executes exactly one JSON action per turn.

Goal: get at least 3 oak_log items into the bot inventory.

Allowed actions (return exactly one JSON object, no markdown):
{"action":"move","p":[x,y,z],"reason":"..."}
{"action":"dig","p":[x,y,z],"reason":"..."}
{"action":"equip","name":"wooden_pickaxe","reason":"..."}
{"action":"chat","text":"...","reason":"..."}
{"action":"done","reason":"..."}

Rules:
- Read the state: inventory, oak_logs and item_drops.
- If a visible item_drop is close, move to it to pick it up.
- To mine a log, stand adjacent to its x/z at the log's y (or one below) and then dig the log position.
- Do not stand inside the log block. Choose a clear adjacent coordinate.
- Mine the lowest oak_log first, then the next one above it.
- Never repeat an action that just failed with air/out of reach; choose a different position.
- When inventory has at least 3 oak_log, chat a short report and then done.
- Return only JSON. Do not explain outside JSON.
"""


def planner_event(step: int, model: str, action: dict, ok: bool,
                  result: str = "", reason: str = "") -> None:
    post(DASH + "/api/planner", {
        "step": step,
        "model": model,
        "action": action.get("action"),
        "reason": reason or action.get("reason") or "",
        "ok": bool(ok),
        "result": result[:300],
    })


def execute(a: dict) -> tuple[bool, str, dict]:
    name = str(a.get("action") or "").lower()
    if name == "done":
        return True, "done", {}
    if name == "move":
        p = a.get("p")
        if not (isinstance(p, list) and len(p) == 3):
            return False, "bad p", {}
        r = act({"channel": "body", "op": "move", "args": {"p": p}})
    elif name == "dig":
        p = a.get("p")
        if not (isinstance(p, list) and len(p) == 3):
            return False, "bad p", {}
        r = act({"channel": "world", "op": "dig", "args": {"p": p}})
    elif name == "equip":
        n = str(a.get("name") or "")
        if not n:
            return False, "bad name", {}
        r = act({"channel": "inventory", "op": "equip", "args": {"name": n}})
    elif name == "chat":
        text = str(a.get("text") or "")
        if not text:
            return False, "bad text", {}
        r = act({"channel": "chat", "op": "say", "args": {"text": text}})
    else:
        return False, f"unknown action: {name}", {}
    res = r.get("result") or {}
    ok = bool(r.get("ok") and res.get("ok", True))
    why = ""
    if not ok:
        why = str(res.get("error") or r.get("error") or r.get("body") or "")[:500]
    return ok, (res.get("payload") or why or "ok"), res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=14)
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "llm-autonomy.jsonl"))
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fh = open(args.out, "a", encoding="utf-8")

    messages = [{"role": "system", "content": system_prompt()}]
    last = None
    model = "qwen3-4b-instruct"
    for step in range(1, args.steps + 1):
        state = compact_state()
        inv = (state.get("bot") or {}).get("items") or {}
        if inv.get("oak_log", 0) >= 3:
            print(f"[{step}] inventory target reached: {inv}", flush=True)
            # ask the planner for the final chat, but do not invent it ourselves
        user = {
            "step": step,
            "state": state,
            "last_action": last,
            "instruction": "Choose the single next JSON action.",
        }
        messages.append({"role": "user",
                         "content": json.dumps(user, ensure_ascii=False)})
        # keep context bounded
        if len(messages) > 9:
            messages = [messages[0]] + messages[-8:]
        try:
            text, model = call_llm(messages)
            a = parse_action(text)
        except Exception as e:
            print(f"[{step}] planner parse error: {e}", flush=True)
            planner_event(step, model, {"action": "parse_error"}, False,
                          str(e))
            messages.append({"role": "assistant", "content": "INVALID"})
            messages.append({"role": "user", "content":
                             "Return only a valid JSON action object."})
            last = {"action": "parse_error", "ok": False, "error": str(e)}
            continue
        print(f"[{step}] {json.dumps(a, ensure_ascii=False)}", flush=True)
        inv = (state.get("bot") or {}).get("items") or {}
        if inv.get("oak_log", 0) >= 3 and a.get("action") not in ("chat", "done"):
            # Supervisor-side goal gate: the external planner already met the
            # objective; do not let it keep consuming the world.
            gate = "GOAL_GATE: oak_log >= 3; send chat then done"
            print(f"[{step}] {gate}", flush=True)
            planner_event(step, model, a, False, gate, "supervisor goal gate")
            messages.append({"role": "assistant",
                             "content": json.dumps(a, ensure_ascii=False)})
            messages.append({"role": "user", "content": json.dumps({
                "goal_met": True, "instruction": gate}, ensure_ascii=False)})
            last = {"action": a, "ok": False, "result": gate}
            time.sleep(0.5)
            continue
        if a.get("action") == "done":
            planner_event(step, model, a, True, "done",
                          a.get("reason") or "")
            fh.write(json.dumps({"step": step, "model": model, "action": a,
                                 "state": state}, ensure_ascii=False) + "\n")
            fh.flush()
            break
        ok, result, _ = execute(a)
        planner_event(step, model, a, ok, str(result),
                      a.get("reason") or "")
        fh.write(json.dumps({"step": step, "model": model, "action": a,
                             "ok": ok, "result": result,
                             "state": state}, ensure_ascii=False) + "\n")
        fh.flush()
        last = {"action": a, "ok": ok, "result": result}
        messages.append({"role": "assistant",
                         "content": json.dumps(a, ensure_ascii=False)})
        messages.append({"role": "user", "content":
                         json.dumps({"executed": a, "ok": ok,
                                     "result": result}, ensure_ascii=False)})
        time.sleep(1.0)
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
