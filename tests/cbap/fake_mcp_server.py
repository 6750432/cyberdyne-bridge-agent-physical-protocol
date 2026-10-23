#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal stdio MCP server for adapter tests (no Minecraft, no external deps)."""

from __future__ import annotations

import json
import sys
import time

POS = [10.0, 64.0, 10.0]
ITEMS = {"oak_log": 4}
CHAT: list[dict] = []


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(rid, payload):
    send({"jsonrpc": "2.0", "id": rid, "result": payload})


def tool_result(rid, data, ok=True):
    result(rid, {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        "isError": not ok,
    })


def main():
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
            result(rid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "0.1"},
            })
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            result(rid, {"tools": [
                {"name": "status", "inputSchema": {"type": "object"}},
                {"name": "observe", "inputSchema": {"type": "object"}},
                {"name": "inventory", "inputSchema": {"type": "object"}},
                {"name": "move", "inputSchema": {"type": "object"}},
                {"name": "chat", "inputSchema": {"type": "object"}},
                {"name": "dig", "inputSchema": {"type": "object"}},
            ]})
        elif method == "tools/call":
            name = (msg.get("params") or {}).get("name")
            args = (msg.get("params") or {}).get("arguments") or {}
            if name == "status":
                tool_result(rid, {"position": {"x": POS[0], "y": POS[1],
                                               "z": POS[2],
                                               "dimension": "overworld"},
                                  "health": 20, "food": 20, "saturation": 5,
                                  "alive": True})
            elif name == "observe":
                target = args.get("target")
                if target == "position":
                    tool_result(rid, {"x": POS[0], "y": POS[1], "z": POS[2],
                                      "dimension": "overworld", "yaw": 0,
                                      "pitch": 0})
                elif target == "blocks":
                    tool_result(rid, {"count": 1, "blocks": [
                        {"name": "oak_log", "position": {"x": 12, "y": 64, "z": 10},
                         "distance": 2.0}]})
                elif target == "chat":
                    tool_result(rid, {"count": len(CHAT), "messages": CHAT[-20:]})
                else:
                    tool_result(rid, {})
            elif name == "inventory":
                tool_result(rid, {"count": len(ITEMS),
                                  "items": [{"name": k, "count": v}
                                            for k, v in ITEMS.items()]})
            elif name == "move":
                if args.get("mode") == "relative":
                    POS[0] += float(args.get("dx") or 0)
                    POS[1] += float(args.get("dy") or 0)
                    POS[2] += float(args.get("dz") or 0)
                else:
                    POS[0] = float(args.get("x", POS[0]))
                    POS[1] = float(args.get("y", POS[1]))
                    POS[2] = float(args.get("z", POS[2]))
                tool_result(rid, {"reached": True, "position": {
                    "x": POS[0], "y": POS[1], "z": POS[2]}})
            elif name == "chat":
                CHAT.append({"timestamp": int(time.time() * 1000),
                             "username": "FakeMCP",
                             "message": str(args.get("message") or "")})
                tool_result(rid, {"ok": True, "sent": args.get("message")})
            elif name == "dig":
                ITEMS["oak_log"] = ITEMS.get("oak_log", 0) + 1
                tool_result(rid, {"ok": True, "block": "oak_log"})
            else:
                tool_result(rid, {"error": "unknown tool"}, ok=False)
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
