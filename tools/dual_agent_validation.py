#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two independent external-LLM planners on two real CBAP devices.

A: real MCP Minecraft agent
B: real legacy node/server.js hand

Each planner has its own CBAP session/fd. They run concurrently and must:
  - send a unique chat message
  - move one block east
  - finish without touching the other device
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drivers.mc.driver import McDriver
import importlib
MCPDriver = importlib.import_module(
    "agents.mcp-mineflayer.driver.driver").MCPDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer

LLM_URL = "http://127.0.0.1:8099/v1/chat/completions"
MCP_ID = "mcp://mc/MCPBody"
LEGACY_ID = "mc://bot/DeepSeek"


def llm(messages, max_tokens=180):
    body = {"model": "local", "messages": messages, "temperature": 0.1,
            "max_tokens": max_tokens, "stream": False}
    req = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.load(r)
    return data["choices"][0]["message"].get("content", ""), data.get("model")


def action(text):
    t = text.strip()
    if "```" in t:
        t = t.split("```", 1)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.split("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        raise ValueError(text[:300])
    return json.loads(t[i:j + 1])


class Planner:
    def __init__(self, name, device_id, chat_text, barrier, report):
        self.name = name
        self.device_id = device_id
        self.chat_text = chat_text
        self.barrier = barrier
        self.report = report
        self.client = None
        self.fd = None
        self.chat_done = False
        self.move_done = False
        self.history = []

    def state(self):
        r = self.client.read(self.fd, "body", 3000)
        st = ((r.get("payload") or {}).get("frame") or {}).get("body") or {}
        items = self.client.read(self.fd, "inventory", 3000)
        inv = ((items.get("payload") or {}).get("frame") or {}).get("inventory") or {}
        return {"pos": st.get("pos"), "hp": st.get("hp"),
                "items": inv.get("items") or {}}

    def prompt(self, st):
        return [{"role": "system", "content": f"""You are external planner {self.name}.
You control exactly one real CBAP device: {self.device_id}.
Goal: send chat message "{self.chat_text}" and move one block east (+x), then done.
One JSON action per turn:
{{"action":"chat","text":"{self.chat_text}"}}
{{"action":"move","dir":[1,0],"ms":500}}
{{"action":"done"}}
Never target another device. Return only JSON."""},
                {"role": "user", "content": json.dumps({
                    "state": st,
                    "chat_done": self.chat_done,
                    "move_done": self.move_done,
                    "history": self.history[-4:],
                }, ensure_ascii=False)}]

    def run(self):
        self.client = CBAPClient(self.report["socket"], agent_id=f"planner-{self.name}")
        self.client.connect(); self.client.hello()
        r = self.client.open(self.device_id)
        if not r.get("ok"):
            raise RuntimeError(r)
        self.fd = r["payload"]["fd"]
        if not self.client.lease(self.fd).get("ok"):
            raise RuntimeError("lease failed")
        self.report["agents"][self.name] = {
            "device_id": self.device_id, "fd": self.fd,
            "initial": self.state(), "steps": []
        }
        self.barrier.wait(timeout=30)
        for step in range(1, 9):
            st = self.state()
            msgs = self.prompt(st)
            try:
                text, model = llm(msgs)
                a = action(text)
            except Exception as e:
                self.history.append({"step": step, "error": str(e)})
                continue
            rec = {"step": step, "model": model, "action": a,
                   "reason": a.get("reason", "")}
            if a.get("action") == "done":
                rec["ok"] = True
                self.report["agents"][self.name]["steps"].append(rec)
                break
            if a.get("action") == "chat":
                frame = {"channel": "chat", "op": "say",
                         "args": {"text": a.get("text") or self.chat_text}}
            elif a.get("action") == "move":
                frame = {"channel": "body", "op": "move",
                         "args": {"dir": [1, 0], "ms": 500}}
            else:
                rec["ok"] = False
                rec["error"] = "unknown action"
                self.report["agents"][self.name]["steps"].append(rec)
                self.history.append(rec)
                continue
            _, _, res = self.client.write(self.fd, frame, deadline_ms=30000)
            rec["result_id"] = res.get("id")
            rec["ok"] = bool(res.get("ok"))
            rec["result"] = res.get("payload") or res.get("error")
            if rec["ok"]:
                if a["action"] == "chat":
                    self.chat_done = True
                if a["action"] == "move":
                    self.move_done = True
            self.report["agents"][self.name]["steps"].append(rec)
            self.history.append(rec)
            if self.chat_done and self.move_done:
                # still ask the model for done on the next turn
                pass
            time.sleep(0.3)
        self.report["agents"][self.name]["final"] = self.state()
        self.report["agents"][self.name]["chat_done"] = self.chat_done
        self.report["agents"][self.name]["move_done"] = self.move_done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-path", default="/home/bzys17mintstart/external/mineflayer-mcp")
    ap.add_argument("--node", default="/home/bzys17mintstart/.local/node/bin/node")
    ap.add_argument("--out", default=os.path.join(ROOT, "logs", "dual-agent.json"))
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="cbap-dual-")
    sock = os.path.join(tmp, "cbap.sock")
    report = {"ok": False, "socket": sock, "agents": {}}
    mcp = legacy = kernel = None
    try:
        mcp = MCPDriver(server_path=args.server_path, node_bin=args.node,
                        username="MCPBody", version="1.21.1",
                        lock_path="/tmp/cbap-mcp-dual.lock",
                        poll_interval=0.5, connect_timeout=45)
        mcp.connect()
        legacy = McDriver(os.path.join(ROOT, "cyberdyne.sock"),
                          device_path=os.path.join(ROOT, "drivers", "mc", "device.json"),
                          mapping_path=os.path.join(ROOT, "drivers", "mc", "mapping.json"),
                          connect_timeout=5, reconnect=True)
        legacy.connect()
        kernel = KernelServer(drivers=[mcp, legacy], socket_path=sock,
                              audit_path=os.path.join(tmp, "audit.jsonl"))
        if not kernel.start():
            raise RuntimeError("kernel did not start")
        # Probe before starting planners
        c = CBAPClient(sock, agent_id="probe")
        c.connect(); c.hello()
        devices = c.device_list()["payload"]["devices"]
        report["devices"] = devices
        c.close()
        barrier = threading.Barrier(2)
        a = Planner("alpha", MCP_ID, "alpha online", barrier, report)
        b = Planner("beta", LEGACY_ID, "beta online", barrier, report)
        errors = []

        def wrap(fn):
            try:
                fn()
            except Exception as e:
                errors.append(str(e))

        ta = threading.Thread(target=wrap, args=(a.run,), name="planner-alpha")
        tb = threading.Thread(target=wrap, args=(b.run,), name="planner-beta")
        ta.start(); tb.start()
        ta.join(timeout=150); tb.join(timeout=150)
        report["thread_errors"] = errors
        # Validate isolation and both goals
        aa = report["agents"].get("alpha") or {}
        bb = report["agents"].get("beta") or {}
        report["ok"] = (
            not errors
            and aa.get("chat_done") and aa.get("move_done")
            and bb.get("chat_done") and bb.get("move_done")
            and (aa.get("initial") or {}).get("pos") != (bb.get("initial") or {}).get("pos")
        )
    except Exception as e:
        report["error"] = str(e)
    finally:
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
                          "agents": {k: {"chat": v.get("chat_done"),
                                        "move": v.get("move_done"),
                                        "steps": len(v.get("steps") or [])}
                                     for k, v in report["agents"].items()},
                          "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
