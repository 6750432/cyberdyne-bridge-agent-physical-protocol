#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MC driver for the legacy hand protocol.

This is the first CBAP-D-shaped driver. It does NOT import bridge.py:
it speaks the existing `node/server.js` line-JSON protocol directly.

Boundary:
  - driver knows Minecraft commands (`move`, `dig`, `place`, `craft`, ...)
  - kernel does not
  - no main-chain file is modified
"""

from __future__ import annotations

import copy
import json
import os
import socket
import threading
import time
from typing import Any, Callable

from kernel.legacy_runtime import protocol

HERE = os.path.dirname(os.path.abspath(__file__))


class ActionError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def as_error(self) -> dict:
        return protocol.error(self.code, self.message, self.retryable)


class McDriver:
    """A CBAP-D driver for a Minecraft hand.

    The hand is the existing `node/server.js`; this class only wraps its
    line-JSON protocol. It can be used by the CBAP gateway or by tests.
    """

    def __init__(self, socket_path: str | None = None,
                 device_path: str | None = None,
                 mapping_path: str | None = None,
                 connect_timeout: float = 3.0,
                 reconnect: bool = True):
        self.socket_path = socket_path or os.path.join(
            os.path.dirname(HERE), "..", "cyberdyne.sock")
        self.socket_path = os.path.abspath(self.socket_path)
        self.device_path = device_path or os.path.join(HERE, "device.json")
        self.mapping_path = mapping_path or os.path.join(HERE, "mapping.json")
        with open(self.device_path, encoding="utf-8") as f:
            self.device = json.load(f)
        with open(self.mapping_path, encoding="utf-8") as f:
            self.mapping = json.load(f)

        self.connect_timeout = float(connect_timeout)
        self.reconnect = bool(reconnect)

        self._sock: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state_cond = threading.Condition(self._state_lock)
        self._latest_state: dict | None = None
        self._state_seq = 0
        self._last_state_at = 0.0
        self._connected = False
        self._buffer = b""

        # Callbacks are invoked from the reader thread.
        self.on_state: Callable[[dict], None] | None = None
        self.on_event: Callable[[dict], None] | None = None
        self.on_result: Callable[[str, bool, str | None, dict], None] | None = None
        self.on_connect: Callable[[], None] | None = None
        self.on_disconnect: Callable[[str], None] | None = None

    # ── lifecycle ──────────────────────────────────────────────

    def connect(self) -> bool:
        if self._reader and self._reader.is_alive():
            return self._connected
        deadline = time.monotonic() + max(0.1, self.connect_timeout)
        last_err = ""
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                self._open_socket()
                break
            except OSError as e:
                last_err = str(e)
                time.sleep(0.1)
        else:
            raise ConnectionError(
                f"cannot connect to hand at {self.socket_path}: {last_err}")
        self._reader = threading.Thread(
            target=self._read_loop, name="mc-driver-reader", daemon=True)
        self._reader.start()
        return True

    def _open_socket(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(self.socket_path)
        with self._state_lock:
            self._sock = s
            self._connected = True
            self._buffer = b""
            self._last_state_at = time.time()
        # MC legacy quirk: inventory is complete only if someone watches "*".
        # This is driver-specific handshake, not a kernel concern.
        try:
            s.sendall(protocol.encode({"cmd": "watch_items", "list": ["*"]}))
        except OSError:
            pass
        if self.on_connect:
            try:
                self.on_connect()
            except Exception:
                pass

    def close(self) -> None:
        self._stop.set()
        sock = self._sock
        self._sock = None
        with self._state_lock:
            self._connected = False
            self._state_cond.notify_all()
        try:
            if sock:
                sock.close()
        except OSError:
            pass
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=1.0)

    # ── callbacks / state ─────────────────────────────────────

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            if not self._connected:
                if not self.reconnect:
                    break
                time.sleep(0.5)
                try:
                    self._open_socket()
                except OSError:
                    continue
            sock = self._sock
            if sock is None:
                time.sleep(0.1)
                continue
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            except OSError as e:
                self._drop(f"recv: {e}")
                continue
            if not chunk:
                self._drop("hand closed")
                continue
            self._buffer += chunk
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = protocol.parse_line(line)
                except (ValueError, UnicodeDecodeError) as e:
                    self._emit_event({
                        "type": "event", "kind": "bad_frame",
                        "why": str(e)[:120], "t": protocol.now_ms(),
                    })
                    continue
                self._dispatch(msg)

    def _drop(self, reason: str) -> None:
        sock = self._sock
        self._sock = None
        with self._state_lock:
            self._connected = False
            self._state_cond.notify_all()
        try:
            if sock:
                sock.close()
        except OSError:
            pass
        if self.on_disconnect:
            try:
                self.on_disconnect(reason)
            except Exception:
                pass

    def _dispatch(self, msg: dict) -> None:
        typ = msg.get("type")
        if typ == "state":
            with self._state_lock:
                self._state_seq += 1
                self._latest_state = copy.deepcopy(msg)
                self._last_state_at = time.time()
                self._state_cond.notify_all()
            if self.on_state:
                try:
                    self.on_state(copy.deepcopy(msg))
                except Exception:
                    pass
            return
        if typ == "event" and msg.get("kind") == "cmdResult":
            cmd = str(msg.get("cmd") or "unknown")
            ok = bool(msg.get("ok"))
            why = msg.get("why")
            extra = {
                k: v for k, v in msg.items()
                if k not in ("type", "kind", "cmd", "ok", "why", "t", "bot")
            }
            if self.on_result:
                try:
                    self.on_result(cmd, ok, why, extra)
                except Exception:
                    pass
            return
        if typ == "event":
            self._emit_event(msg)

    def _emit_event(self, msg: dict) -> None:
        if self.on_event:
            try:
                self.on_event(msg)
            except Exception:
                pass

    # ── queries ───────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    def describe(self) -> dict:
        desc = copy.deepcopy(self.device)
        ops = self.mapping.get("ops") or {}
        actions = {}
        for name, spec in ops.items():
            actions[str(name)] = {
                "args": copy.deepcopy((spec or {}).get("args") or {}),
                "result": {},
                "danger": ("high" if name in
                           {"attack", "dig", "place", "use", "give"} else "normal"),
                "idempotent": False,
            }
        limits = desc.get("limits") or {}
        desc.update({
            "contract": "cbap-device-v1",
            "class": "actuator",
            "version": str(desc.get("cbap") or "1.0"),
            "legacy": False,
            "actions": actions,
            "capabilities": ["read", "write", "lease", "estop"],
            "trust": {
                "source": "minecraft-server",
                "independent": True,
                "attestation": "none",
                "level": 2,
            },
            "isolation": {
                "process": "mc-hand",
                "uid": os.getuid(),
                "sandbox": "none",
                "network": "unix",
            },
            "resources": {
                "max_inflight": int(limits.get("max_inflight") or 1),
                "rate_hz": max(20, int(limits.get("rate_hz") or 5)),
                "max_bytes": int(limits.get("max_frame") or 65536),
                "max_sessions": 4,
            },
        })
        return desc

    def latest_state(self) -> dict | None:
        with self._state_lock:
            return copy.deepcopy(self._latest_state)

    def state_age_ms(self) -> int | None:
        with self._state_lock:
            if not self._last_state_at:
                return None
            return int((time.time() - self._last_state_at) * 1000)

    def wait_state(self, timeout_s: float) -> dict | None:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._state_cond:
            while self._latest_state is None and not self._stop.is_set():
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._state_cond.wait(min(left, 0.1))
            return copy.deepcopy(self._latest_state)

    def health(self) -> dict:
        age = self.state_age_ms()
        ok = bool(self._connected) and (age is not None and age < 5000)
        return {
            "ok": ok,
            "connected": bool(self._connected),
            "state_age_ms": age,
            "device_id": self.device.get("device_id"),
        }

    # ── commands ─────────────────────────────────────────────

    def send(self, command: dict) -> bool:
        data = protocol.encode(command)
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
        return self.send({"cmd": "stop"})

    def map_action(self, frame: dict) -> dict:
        """CBAP frame -> legacy hand command. Raises ActionError."""
        if not isinstance(frame, dict):
            raise ActionError("E_INVAL", "frame must be an object")
        channel = frame.get("channel")
        op = frame.get("op")
        args = frame.get("args") or {}
        if not isinstance(op, str) or not op:
            raise ActionError("E_INVAL", "frame.op must be a string")
        if not isinstance(args, dict):
            raise ActionError("E_INVAL", "frame.args must be an object")

        if op == "stop":
            return {"cmd": "stop"}
        if op == "eat" and not args:
            return {"cmd": "eat"}

        mapping = (self.mapping.get("ops") or {}).get(op)
        if not mapping:
            raise ActionError("E_NOTSUP", f"op not supported by mc-driver: {op}")
        if channel and mapping.get("channel") and channel != mapping["channel"]:
            raise ActionError(
                "E_INVAL",
                f"channel mismatch: frame={channel} mapping={mapping['channel']}")

        legacy: dict[str, Any] = {"cmd": mapping["op"]}
        schema = mapping.get("args") or {}
        rename = mapping.get("legacy_args") or {}
        if not isinstance(rename, dict):
            rename = {}
        for key, typ in schema.items():
            optional = key.startswith("?")
            name = key[1:] if optional else key
            if name not in args:
                if optional:
                    continue
                raise ActionError("E_INVAL", f"missing arg: {name}")
            # CBAP 的通用字段名 -> legacy hand 的方言字段名
            legacy[str(rename.get(name, name))] = _check_arg(name, typ, args[name])
        return legacy


def _check_arg(name: str, typ: str, value: Any) -> Any:
    if typ == "vec2":
        if not isinstance(value, (list, tuple)) or len(value) != 2 \
                or not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                           for x in value):
            raise ActionError("E_INVAL", f"{name} must be vec2")
        return [float(value[0]), float(value[1])]
    if typ == "vec3":
        if not isinstance(value, (list, tuple)) or len(value) != 3 \
                or not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                           for x in value):
            raise ActionError("E_INVAL", f"{name} must be vec3")
        return [float(value[0]), float(value[1]), float(value[2])]
    if typ == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ActionError("E_INVAL", f"{name} must be int")
        return int(value)
    if typ == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ActionError("E_INVAL", f"{name} must be number")
        return float(value)
    if typ == "bool":
        if not isinstance(value, bool):
            raise ActionError("E_INVAL", f"{name} must be bool")
        return value
    if typ in ("string", "inventory_item", "block", "entity"):
        if not isinstance(value, str) or not value:
            raise ActionError("E_INVAL", f"{name} must be a non-empty string")
        return value
    if typ == "object":
        if not isinstance(value, dict):
            raise ActionError("E_INVAL", f"{name} must be an object")
        return value
    raise ActionError("E_NOTSUP", f"unknown arg type: {typ}")
