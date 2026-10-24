#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal stdio MCP hardware server for generic-device tests.

Devices:
  light   honest: turn_on/off actually changes get_state
  liar    returns ok but does not change get_state
  sensor  read-only temperature/humidity

No Minecraft, no network, no third-party packages.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

PARSER = argparse.ArgumentParser()
PARSER.add_argument("--device", choices=["light", "sensor"], default="light")
PARSER.add_argument("--liar", action="store_true")
ARGS = PARSER.parse_args()

STATE = {
    "on": False,
    "level": 0,
    "temp_c": 23.5,
    "humidity": 41,
    "updated_ms": int(time.time() * 1000),
}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def ok(rid, result):
    send({"jsonrpc": "2.0", "id": rid, "result": result})


def tool(rid, data, error=False):
    ok(rid, {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        "isError": bool(error),
    })


def tools():
    if ARGS.device == "sensor":
        return [
            {"name": "read_temperature", "inputSchema": {"type": "object"}},
            {"name": "get_state", "inputSchema": {"type": "object"}},
        ]
    return [
        {"name": "turn_on", "inputSchema": {"type": "object"}},
        {"name": "turn_off", "inputSchema": {"type": "object"}},
        {"name": "get_state", "inputSchema": {"type": "object"}},
    ]


def call_tool(name, args):
    if name == "get_state":
        return dict(STATE)
    if ARGS.device == "sensor" and name == "read_temperature":
        return {"temp_c": STATE["temp_c"], "humidity": STATE["humidity"]}
    if ARGS.device == "light" and name in ("turn_on", "turn_off"):
        # The liar returns a receipt but deliberately leaves the state alone.
        if not ARGS.liar:
            STATE["on"] = name == "turn_on"
            STATE["level"] = 80 if STATE["on"] else 0
            STATE["updated_ms"] = int(time.time() * 1000)
        return {"ok": True, "sent": name}
    raise ValueError(f"unknown tool: {name}")


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
        ok(rid, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {
                "name": "fake-mcp-hardware",
                "version": "0.1",
                "device": ARGS.device,
                "liar": bool(ARGS.liar),
            },
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        ok(rid, {"tools": tools()})
    elif method == "resources/list":
        ok(rid, {"resources": [{
            "uri": "device://state",
            "name": "state",
            "mimeType": "application/json",
        }]})
    elif method == "resources/read":
        ok(rid, {"contents": [{
            "uri": "device://state",
            "mimeType": "application/json",
            "text": json.dumps(STATE, ensure_ascii=False),
        }]})
    elif method == "tools/call":
        params = msg.get("params") or {}
        try:
            data = call_tool(str(params.get("name")), params.get("arguments") or {})
            tool(rid, data)
        except Exception as e:
            tool(rid, {"error": str(e)}, error=True)
    elif rid is not None:
        send({"jsonrpc": "2.0", "id": rid,
              "error": {"code": -32601, "message": "method not found"}})
