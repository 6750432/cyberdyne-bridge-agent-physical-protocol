#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mutating MCP server that can drop the first tools/call response.

The effect is committed before the response is dropped.  This lets the
protocol-level retry audit observe duplicate external effects without a real
network or a real device.
"""
from __future__ import annotations

import argparse
import json
import sys

p = argparse.ArgumentParser()
p.add_argument("--drop-first", action="store_true")
a = p.parse_args()

state = {"count": 0, "effects": []}
calls = 0


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(rid, data):
    send({"jsonrpc": "2.0", "id": rid, "result": {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        "isError": False,
    }})


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method = msg.get("method")
    rid = msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mutator", "version": "0.1"},
        }})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": "bump", "inputSchema": {"type": "object"}},
            {"name": "get_state", "inputSchema": {"type": "object"}},
        ]}})
    elif method == "tools/call":
        calls += 1
        params = msg.get("params") or {}
        name = params.get("name")
        if name == "bump":
            # Effect is committed first; the response may be dropped after.
            state["count"] += 1
            state["effects"].append({"call": calls, "count": state["count"]})
            if a.drop_first and calls == 1:
                continue
            result(rid, {"ok": True, "count": state["count"]})
        elif name == "get_state":
            result(rid, dict(state))
        else:
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "isError": True,
                "content": [{"type": "text", "text": "unknown tool"}],
            }})
    elif rid is not None:
        send({"jsonrpc": "2.0", "id": rid,
              "error": {"code": -32601, "message": "method not found"}})
