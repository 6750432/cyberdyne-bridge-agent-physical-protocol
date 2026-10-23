#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP-D driver for an external data-flow MC agent.

The external agent owns the Minecraft body. This driver only translates
CBAP frames into the agent's line-JSON data-flow protocol:

  driver -> agent: {"type":"action","id","channel","op","args"}
  agent -> driver: {"type":"state","seq","state":{...}}
                   {"type":"result","id","ok","why","data","facts"}
                   {"type":"event","kind","data"}

This is deliberately not mineflayer-specific: any agent that can expose the
same state/action stream can be registered as a CBAP peripheral.
"""

from __future__ import annotations

import copy
import json
import os
import socket
import threading
import time
from typing import Any

from drivers.mc.driver import McDriver, ActionError
from kernel.legacy_runtime import protocol

HERE = os.path.dirname(os.path.abspath(__file__))


class DataFlowDriver(McDriver):
    """A CBAP-D peripheral driver for an external data-flow agent."""

    def __init__(self, socket_path: str,
                 device_path: str | None = None,
                 mapping_path: str | None = None,
                 device_id: str | None = None,
                 connect_timeout: float = 3.0,
                 reconnect: bool = True):
        super().__init__(
            socket_path=socket_path,
            device_path=device_path or os.path.join(HERE, "device.json"),
            mapping_path=mapping_path or os.path.join(HERE, "mapping.json"),
            connect_timeout=connect_timeout,
            reconnect=reconnect,
        )
        if device_id:
            self.device["device_id"] = str(device_id)
            self.mapping["device_id"] = str(device_id)
        self._inflight: dict[str, str] = {}
        self._inflight_lock = threading.Lock()

    # ── transport ─────────────────────────────────────────────

    def _open_socket(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(self.socket_path)
        with self._state_lock:
            self._sock = s
            self._connected = True
            self._buffer = b""
            self._last_state_at = time.time()
        try:
            s.sendall(protocol.encode({
                "type": "cbap_hello", "v": "1.0", "driver": "dataflow",
                "device_id": self.device.get("device_id"),
            }))
        except OSError:
            pass
        if self.on_connect:
            try:
                self.on_connect()
            except Exception:
                pass

    def _dispatch(self, msg: dict) -> None:
        typ = msg.get("type")
        if typ == "state":
            state = msg.get("state") if isinstance(msg.get("state"), dict) else msg
            state_msg = copy.deepcopy(state)
            state_msg.setdefault("type", "state")
            state_msg.setdefault("seq", msg.get("seq", int(time.time() * 1000)))
            state_msg.setdefault("t", msg.get("t", int(time.time() * 1000)))
            with self._state_lock:
                self._state_seq += 1
                self._latest_state = copy.deepcopy(state_msg)
                self._last_state_at = time.time()
                self._state_cond.notify_all()
            if self.on_state:
                try:
                    self.on_state(copy.deepcopy(state_msg))
                except Exception:
                    pass
            return
        if typ in ("result", "action_result"):
            rid = str(msg.get("id") or "")
            with self._inflight_lock:
                cmd = self._inflight.pop(rid, None)
            if cmd is None:
                return
            extra = msg.get("data") or msg.get("payload") or {}
            if not isinstance(extra, dict):
                extra = {"data": extra}
            if msg.get("facts"):
                extra.setdefault("facts", msg.get("facts"))
            if self.on_result:
                try:
                    self.on_result(cmd, bool(msg.get("ok")), msg.get("why"), extra)
                except Exception:
                    pass
            return
        if typ in ("event", "state_event"):
            if self.on_event:
                try:
                    self.on_event(msg)
                except Exception:
                    pass

    def send(self, command: dict) -> bool:
        if not isinstance(command, dict):
            return False
        cmd = str(command.get("cmd") or "")
        rid = protocol.new_id("a")
        if cmd in ("scan_environment", "watch_blocks", "watch_items", "furnace_watch"):
            payload = {"type": "ioctl", "id": rid, "op": cmd}
            payload.update({k: v for k, v in command.items() if k != "cmd"})
        else:
            args = command.get("args")
            if not isinstance(args, dict):
                args = {k: v for k, v in command.items()
                        if k not in ("cmd", "channel")}
            payload = {
                "type": "action", "id": rid, "op": cmd,
                "channel": command.get("channel"),
                "args": args,
            }
        with self._inflight_lock:
            self._inflight[rid] = cmd
        data = protocol.encode(payload)
        with self._send_lock:
            sock = self._sock
            if not sock or not self._connected:
                return False
            try:
                sock.sendall(data)
                return True
            except OSError as e:
                self._drop(f"send: {e}")
                return False

    def estop(self) -> bool:
        rid = protocol.new_id("e")
        payload = {"type": "estop", "id": rid,
                   "device_id": self.device.get("device_id")}
        with self._send_lock:
            sock = self._sock
            if not sock or not self._connected:
                return False
            try:
                sock.sendall(protocol.encode(payload))
                return True
            except OSError:
                return False

    def map_action(self, frame: dict) -> dict:
        checked = super().map_action(frame)
        return {
            "cmd": checked.get("cmd"),
            "channel": frame.get("channel"),
            "args": {k: v for k, v in checked.items() if k != "cmd"},
        }
