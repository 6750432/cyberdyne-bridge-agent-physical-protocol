#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python client for the MC Body API v0.

This is deliberately independent of CBAP: it can be used for development and
benchmarks directly against a Mineflayer body, or through the McDriver wrapper.

Wire: Unix domain socket + NDJSON.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

VERSION = "mc-body/1"


class MCBodyError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = bool(retryable)

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable}


class MCBodyClient:
    def __init__(self, socket_path: str | os.PathLike[str],
                 client: str = "mc-body-sdk"):
        self.socket_path = str(socket_path)
        self.client = str(client)
        self._sock: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._cv = threading.Condition()
        self._welcome: dict | None = None
        self._acks: dict[str, dict] = {}
        self._results: dict[str, dict] = {}
        self._states: dict[int, dict] = {}
        self._last_state: dict | None = None
        self._seq = 0
        self._send_lock = threading.Lock()
        self._buf = b""
        self.last_ack_ms: float | None = None
        self.last_result_ms: float | None = None

    # ── lifecycle ────────────────────────────────────────────

    def connect(self, timeout: float = 3.0) -> dict:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(self.socket_path)
        sock.settimeout(0.2)
        self._sock = sock
        self._reader = threading.Thread(target=self._read_loop,
                                        name="mc-body-sdk", daemon=True)
        self._reader.start()
        self._send({"v": VERSION, "type": "hello", "id": "h-1",
                    "client": self.client})
        deadline = time.monotonic() + timeout
        with self._cv:
            while self._welcome is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    self.close()
                    raise TimeoutError("MC body welcome timeout")
                self._cv.wait(min(left, 0.1))
            return self._welcome

    def close(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # ── wire ─────────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        sock = self._sock
        if sock is None:
            raise MCBodyError("E_IO", "not connected")
        with self._send_lock:
            sock.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))

    def _read_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                data = sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            self._buf += data
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                self._on_message(msg)

    def _on_message(self, msg: dict) -> None:
        typ = msg.get("type")
        now = time.monotonic()
        with self._cv:
            if typ == "welcome":
                self._welcome = msg
            elif typ == "state":
                body = msg.get("body") or {}
                self._seq = int(msg.get("seq") or self._seq)
                self._last_state = {"seq": self._seq, "t": msg.get("t"),
                                    "body": body}
                self._states[self._seq] = self._last_state
            elif typ == "ack":
                rid = str(msg.get("id") or "")
                self._acks[rid] = msg
                self.last_ack_ms = now * 1000
            elif typ == "result":
                rid = str(msg.get("id") or "")
                self._results[rid] = msg
                self.last_result_ms = now * 1000
                # Optimistic cache: a completed task already knows its
                # position/inventory facts; don't force the caller to wait
                # for the next 5-10 Hz state push.  The next state message is
                # still authoritative and will overwrite this.
                facts = msg.get("facts") or {}
                if self._last_state and isinstance(facts, dict):
                    body = self._last_state.setdefault("body", {})
                    if "position" in facts:
                        body["pos"] = list(facts["position"])
                    if "inventory" in facts:
                        body["inventory"] = dict(facts["inventory"])
                    if "held" in facts:
                        body["held"] = facts["held"]
            self._cv.notify_all()

    # ── calls ────────────────────────────────────────────────

    def command(self, cmd: str, args: dict | None = None,
                *, deadline_ms: int = 15000, timeout: float | None = None,
                request_id: str | None = None) -> dict:
        rid = request_id or f"r-{int(time.time() * 1000000)}"
        timeout = timeout if timeout is not None else max(
            1.0, deadline_ms / 1000.0 + 1.0)
        self._send({
            "v": VERSION, "type": "command", "id": rid, "cmd": str(cmd),
            "args": dict(args or {}), "deadline_ms": int(deadline_ms),
        })
        deadline = time.monotonic() + timeout
        with self._cv:
            while rid not in self._results:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise MCBodyError("E_TIMEOUT", f"no result for {cmd}")
                self._cv.wait(min(left, 0.1))
            result = self._results.pop(rid)
        if not result.get("ok"):
            err = result.get("error") or {}
            raise MCBodyError(str(err.get("code") or "E_INTERNAL"),
                              str(err.get("message") or "body error"),
                              retryable=bool(err.get("retryable")))
        return result

    def cancel(self, target: str, timeout: float = 2.0) -> dict:
        rid = f"c-{int(time.time() * 1000000)}"
        self._send({"v": VERSION, "type": "cancel", "id": rid,
                    "target": str(target)})
        deadline = time.monotonic() + timeout
        with self._cv:
            while rid not in self._results:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise MCBodyError("E_TIMEOUT", "cancel result timeout")
                self._cv.wait(min(left, 0.1))
            return self._results.pop(rid)

    def state(self, timeout: float = 2.0) -> dict:
        deadline = time.monotonic() + timeout
        with self._cv:
            while self._last_state is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("no MC body state")
                self._cv.wait(min(left, 0.1))
            return dict(self._last_state)

    @property
    def state_age_ms(self) -> int | None:
        with self._cv:
            if not self._last_state:
                return None
            t = self._last_state.get("t")
            if not t:
                return None
            return max(0, int(time.time() * 1000 - int(t)))

    # ── convenience ──────────────────────────────────────────

    def goto(self, x: float, y: float, z: float, *, range: float | None = None,
             timeout: float = 30.0) -> dict:
        args: dict[str, Any] = {"x": x, "y": y, "z": z}
        if range is not None:
            args["range"] = range
        return self.command("goto", args, deadline_ms=int(timeout * 1000),
                            timeout=timeout + 1.0)

    def collect(self, block: str, count: int = 1, *,
                radius: float | None = None, timeout: float = 60.0) -> dict:
        args: dict[str, Any] = {"block": block, "count": int(count)}
        if radius is not None:
            args["radius"] = radius
        return self.command("collect", args, deadline_ms=int(timeout * 1000),
                            timeout=timeout + 1.0)

    def craft(self, item: str, count: int = 1, *,
              timeout: float = 30.0) -> dict:
        return self.command("craft", {"item": item, "count": int(count)},
                            deadline_ms=int(timeout * 1000),
                            timeout=timeout + 1.0)

    def equip(self, item: str) -> dict:
        return self.command("equip", {"item": item})

    def say(self, text: str) -> dict:
        return self.command("say", {"text": str(text)[:256]})

    def stop(self) -> dict:
        return self.command("stop", {}, deadline_ms=5000)
