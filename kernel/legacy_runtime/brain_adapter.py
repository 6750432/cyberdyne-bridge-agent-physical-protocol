#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drop-in-ish adapter: legacy `bridge.py` 接线口 shape -> CBAP-U.

The legacy brain talks to `接线口` with:
    连() / 收() -> (messages, disconnected) / 发(dict) / 断()

This class implements the same four methods but speaks CBAP-U through
CBAPClient. It is intentionally not wired into bridge.py yet; that keeps the
main chain untouched. A future migration can swap:

    iface = 接线口(cfg, 说)
    # ->
    iface = CBAPHandAdapter(cfg, 说)

and keep the rest of the loop unchanged.

Not supported in v0: watch_items / furnace_watch / mode / friend / 变了 /
scan_clear. They fail closed (a cmdResult with ok:false) instead of silently
pretending to work.
"""

from __future__ import annotations

import json
import os
import socket
import time

from .client import CBAPClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_DEVICE = "mc://bot/DeepSeek"
DEFAULT_MAPPING = os.path.join(ROOT, "drivers", "mc", "mapping.json")
DEFAULT_CBAP_SOCKET = os.path.join(ROOT, "cbap.sock")


class CBAPHandAdapter:
    def __init__(self, cfg: dict | None = None, 说=None,
                 cbap_socket: str | None = None,
                 device_id: str = DEFAULT_DEVICE,
                 mapping_path: str = DEFAULT_MAPPING,
                 agent_id: str = "bridge-legacy"):
        self.cfg = cfg or {}
        self.说 = 说 or (lambda *a, **k: None)
        self.cbap_socket = cbap_socket or DEFAULT_CBAP_SOCKET
        self.device_id = device_id
        self.agent_id = agent_id
        with open(mapping_path, encoding="utf-8") as f:
            self.mapping = json.load(f)
        self.client: CBAPClient | None = None
        self.fd: str | None = None
        self._pending: dict[str, str] = {}
        self._outbox: list[dict] = []
        self._last_error = ""
        self.烂包数 = 0

    # ── 接线口-compatible API ─────────────────────────────────

    def 连(self, 重试: int = 3) -> bool:
        last = ""
        for i in range(1, max(1, 重试) + 1):
            c = CBAPClient(self.cbap_socket, agent_id=self.agent_id)
            try:
                c.connect(timeout=1.0)
                c.hello(timeout=3.0)
                r = c.open(self.device_id, mode="exclusive", timeout=3.0)
                if not r.get("ok"):
                    err = (r.get("error") or {}).get("code", "?")
                    why = (r.get("error") or {}).get("message", "")
                    raise RuntimeError(f"open failed: {err} {why}")
                self.client = c
                self.fd = r["payload"]["fd"]
                self._last_error = ""
                self.说(f"[CBAP] 接线口连上了 {self.cbap_socket}（fd={self.fd}）")
                return True
            except (OSError, TimeoutError, RuntimeError) as e:
                last = str(e)
                try:
                    c.close()
                except Exception:
                    pass
                if i == 1:
                    self.说(f"[CBAP] 接线口还没开 {self.cbap_socket}，我在门口等…")
                time.sleep(1)
        self._last_error = last
        self.说(f"[CBAP] 试了 {重试} 次都没连上（{last}）")
        return False

    def 收(self):
        """Return (legacy messages, disconnected). Mirrors 接线口.收()."""
        if not self.client:
            return [], True
        out: list[dict] = []
        if self._outbox:
            out, self._outbox = self._outbox, []
        # CBAP v1 delivers asynchronous events through poll(), not as a push.
        try:
            polled = self.client.poll(timeout_ms=0, timeout=1.0)
            for ev in (polled.get("payload") or {}).get("events") or []:
                out.append(self._event_to_legacy({
                    "type": "event",
                    "kind": ev.get("kind"),
                    "payload": ev.get("payload") or {},
                    "ts": ev.get("ts"),
                }))
        except (TimeoutError, OSError):
            pass
        for msg in self.client.drain_inbox():
            typ = msg.get("type")
            if typ == "state":
                out.append(self._state_to_legacy(msg))
            elif typ == "event":
                out.append(self._event_to_legacy(msg))
            elif typ in ("result", "error"):
                cmd = self._pending.pop(str(msg.get("id")), None)
                if cmd:
                    out.append(self._result_to_legacy(msg, cmd))
            elif typ == "pong":
                cmd = self._pending.pop(str(msg.get("id")), None)
                if cmd:
                    out.append({"type": "event", "kind": "cmdResult",
                                "cmd": cmd, "ok": True, "why": None,
                                "t": msg.get("ts") or int(time.time() * 1000)})
        if not self.client.connected and not out:
            return [], True
        return out, False

    def 发(self, obj: dict) -> bool:
        if not isinstance(obj, dict) or not self.client or not self.fd:
            return False
        cmd = obj.get("cmd") or obj.get("act")
        if not isinstance(cmd, str) or not cmd:
            return False
        try:
            if cmd == "scan_environment":
                rid = self.client.request("ioctl", {
                    "fd": self.fd, "request": "scan",
                    "args": {"radius": obj.get("半径", 12),
                             "step": obj.get("步长", 2)},
                })
                self._pending[rid] = "scan_environment"
                return True
            if cmd == "watch_blocks":
                rid = self.client.request("ioctl", {
                    "fd": self.fd, "request": "watch",
                    "args": {"blocks": obj.get("list") or []},
                })
                self._pending[rid] = "watch_blocks"
                return True
            if cmd == "ping":
                rid = "ping-" + str(int(time.time() * 1000))
                self.client.send({"v": "1.0", "type": "ping", "id": rid,
                                  "ts": int(time.time() * 1000)})
                self._pending[rid] = "ping"
                return True

            frame = self._frame_from_legacy(cmd, obj)
            if frame is None:
                self._outbox.append({
                    "type": "event", "kind": "cmdResult", "cmd": cmd,
                    "ok": False, "why": f"CBAP adapter v0 不支持「{cmd}」",
                    "t": int(time.time() * 1000),
                })
                return False
            deadline = obj.get("ms") or 5000
            try:
                deadline = max(1000, int(deadline) + 1000)
            except Exception:
                deadline = 5000
            rid = self.client.request(
                "write", {"fd": self.fd, "frame": frame},
                deadline_ms=deadline)
            self._pending[rid] = cmd
            return True
        except (OSError, TimeoutError) as e:
            self._last_error = str(e)
            return False

    def 断(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.fd = None

    # ── translations ─────────────────────────────────────────

    def _frame_from_legacy(self, cmd: str, obj: dict) -> dict | None:
        if cmd == "stop":
            return {"channel": "body", "op": "stop", "args": {}}
        if cmd == "eat":
            return {"channel": "body", "op": "eat", "args": {}}
        mapping = (self.mapping.get("ops") or {}).get(cmd)
        if not mapping:
            return None
        args: dict = {}
        for key, _typ in (mapping.get("args") or {}).items():
            optional = key.startswith("?")
            name = key[1:] if optional else key
            if name in obj:
                args[name] = obj[name]
            elif not optional:
                return None
        return {"channel": mapping["channel"],
                "op": mapping["op"],
                "args": args}

    def _state_to_legacy(self, msg: dict) -> dict:
        p = msg.get("payload") or {}
        body = p.get("body") or {}
        inv = p.get("inventory") or {}
        world = p.get("world") or {}
        stuck = p.get("stuck") or {}
        return {
            "type": "state",
            "t": msg.get("ts"),
            "seq": msg.get("seq"),
            "bot": self.cfg.get("bot_name", "DeepSeek"),
            "connected": True,
            "pos": body.get("pos"),
            "hp": body.get("hp"),
            "food": body.get("food"),
            "onGround": body.get("on_ground"),
            "look": {"yaw": 0.0, "pitch": 0.0},
            "near": p.get("near") or [],
            "threats": p.get("threats") or [],
            "foods": inv.get("foods") or [],
            "players": p.get("players") or [],
            "friends": [],
            "weapons": inv.get("weapons") or [],
            "held": body.get("held"),
            "drops": p.get("drops") or [],
            "hz": 5,
            "plugins": {"pathfinder": False, "body": True},
            "watched": None,
            "respawned": False,
            "deaths": 0,
            "scan": world.get("scan"),
            "durability": body.get("durability") or {"held": None, "armor": {}},
            "blocks": world.get("blocks") or [],
            "items": inv.get("items") or {},
            "furnace": world.get("furnace"),
            "stuck_count": stuck.get("count") or 0,
            "stuck_ms": stuck.get("ms"),
            "stuck_dir": stuck.get("dir"),
            "attacked_by": p.get("attacked_by"),
            "acting": body.get("acting") or "idle",
            "msg": None,
        }

    def _event_to_legacy(self, msg: dict) -> dict:
        kind = msg.get("kind") or "event"
        payload = msg.get("payload") or {}
        out = {"type": "event", "kind": kind, "t": msg.get("ts")}
        out.update(payload)
        return out

    def _result_to_legacy(self, msg: dict, cmd: str) -> dict:
        ok = bool(msg.get("ok"))
        err = msg.get("error") or {}
        out = {
            "type": "event",
            "kind": "cmdResult",
            "cmd": cmd,
            "ok": ok,
            "why": None if ok else (err.get("message") or err.get("code") or "CBAP error"),
            "t": msg.get("ts") or int(time.time() * 1000),
        }
        payload = msg.get("payload") or {}
        if isinstance(payload, dict):
            out.update(payload)
        return out
