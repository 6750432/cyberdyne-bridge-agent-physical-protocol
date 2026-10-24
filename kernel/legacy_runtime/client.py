#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal CBAP-U client (stdlib only) for examples and tests."""

from __future__ import annotations

import socket
import threading
import time
from collections import defaultdict, deque

from . import protocol


class CBAPError(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail or {}


class CBAPClient:
    def __init__(self, socket_path: str, agent_id: str = "cbap-client"):
        self.socket_path = socket_path
        self.agent_id = agent_id
        self._sock: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._results: dict[str, deque] = defaultdict(deque)
        self._acks: dict[str, deque] = defaultdict(deque)
        self._events: list[dict] = []
        self._inbox: list[dict] = []
        self._latest_state: dict | None = None
        self._connected = False
        self.welcome: dict | None = None
        self._welcome_evt = threading.Event()
        self._buffer = b""
        self.session_id: str | None = None

    # ── lifecycle ──────────────────────────────────────────────

    def connect(self, timeout: float = 3.0) -> bool:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(self.socket_path)
        s.settimeout(0.5)
        self._sock = s
        self._connected = True
        self._reader = threading.Thread(
            target=self._read_loop, name="cbap-client-reader", daemon=True)
        self._reader.start()
        return True

    def close(self) -> None:
        self._stop.set()
        self._connected = False
        sock = self._sock
        self._sock = None
        with self._cv:
            self._cv.notify_all()
        try:
            if sock:
                sock.close()
        except OSError:
            pass
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=1.0)

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            self._buffer += chunk
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = protocol.parse_line(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                self._dispatch(msg)
        self._connected = False
        with self._cv:
            self._cv.notify_all()

    def _dispatch(self, msg: dict) -> None:
        typ = msg.get("type")
        rid = msg.get("id")
        with self._cv:
            self._inbox.append(msg)
            if typ == "welcome":
                self.welcome = msg
                self.session_id = msg.get("session_id")
                self._welcome_evt.set()
            elif typ in ("result", "error") and isinstance(rid, str):
                self._results[rid].append(msg)
            elif typ == "ack" and isinstance(rid, str):
                self._acks[rid].append(msg)
            elif typ == "state":
                self._latest_state = msg
            elif typ == "event":
                self._events.append(msg)
            self._cv.notify_all()

    # ── wire ──────────────────────────────────────────────────

    def send(self, msg: dict) -> None:
        sock = self._sock
        if not sock:
            raise ConnectionError("not connected")
        with self._send_lock:
            protocol.send_line(sock, msg)

    def request(self, op: str, args: dict | None = None,
                deadline_ms: int | None = None,
                idempotency_key: str | None = None) -> str:
        rid = protocol.new_id("r")
        msg = {
            "v": protocol.PROTOCOL_VERSION,
            "type": "request",
            "id": rid,
            "ts": protocol.now_ms(),
            "op": op,
            "args": args or {},
        }
        if deadline_ms is not None:
            msg["deadline_ms"] = int(deadline_ms)
        if idempotency_key:
            msg["idempotency_key"] = idempotency_key
        self.send(msg)
        return rid

    def wait(self, rid: str, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        with self._cv:
            while not self._results.get(rid) and not self._stop.is_set():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"no CBAP result for {rid}")
                self._cv.wait(min(left, 0.1))
            if not self._results.get(rid):
                raise TimeoutError(f"no CBAP result for {rid}")
            return self._results[rid].popleft()

    def wait_ack(self, rid: str, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        with self._cv:
            while not self._acks.get(rid) and not self._stop.is_set():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"no CBAP ack for {rid}")
                self._cv.wait(min(left, 0.1))
            return self._acks[rid].popleft()

    def call(self, op: str, args: dict | None = None,
             timeout: float = 5.0, deadline_ms: int | None = None,
             idempotency_key: str | None = None) -> dict:
        rid = self.request(op, args, deadline_ms, idempotency_key)
        return self.wait(rid, timeout)

    # ── convenience ───────────────────────────────────────────

    def hello(self, capabilities: list[str] | None = None,
              token: str | None = None, timeout: float = 3.0,
              operator_token: str | None = None,
              agent_token: str | None = None) -> dict:
        if token is None:
            try:
                with open(self.socket_path + ".token", encoding="ascii") as f:
                    token = f.read().strip()
            except OSError:
                token = None
        rid = protocol.new_id("h")
        msg = {
            "v": protocol.PROTOCOL_VERSION,
            "type": "hello",
            "id": rid,
            "ts": protocol.now_ms(),
            "agent_id": self.agent_id,
            "role": "agent",
            "capabilities": capabilities or ["read", "write", "lease", "estop"],
        }
        auth = {}
        if token:
            auth["token"] = token
        if operator_token:
            auth["operator_token"] = operator_token
        if agent_token:
            auth["agent_token"] = agent_token
        if auth:
            msg["auth"] = auth
        self.send(msg)
        if not self._welcome_evt.wait(timeout):
            raise TimeoutError("no welcome")
        if not self.welcome:
            raise CBAPError("E_PROTOCOL", "no welcome")
        return self.welcome

    def open(self, device_id: str, mode: str = "rw", timeout: float = 5.0) -> dict:
        return self.call("open", {"device_id": device_id, "mode": mode}, timeout)

    def read(self, fd: str, channel: str | None = None,
             timeout_ms: int = 1000, timeout: float = 5.0) -> dict:
        args = {"fd": fd, "timeout_ms": timeout_ms}
        if channel:
            args["channel"] = channel
        return self.call("read", args, timeout)

    def lease(self, fd: str, ttl_ms: int = 30000, timeout: float = 5.0,
              wait_ms: int = 0) -> dict:
        args = {"fd": fd, "ttl_ms": ttl_ms}
        if wait_ms:
            args["wait_ms"] = int(wait_ms)
        return self.call("lease", args, timeout)

    def release(self, fd: str, timeout: float = 5.0) -> dict:
        return self.call("release", {"fd": fd}, timeout)

    def write(self, fd: str, frame: dict, deadline_ms: int = 5000,
              idempotency_key: str | None = None, timeout: float = 5.0) -> tuple[str, dict, dict]:
        rid = self.request("write", {"fd": fd, "frame": frame}, deadline_ms,
                           idempotency_key)
        ack = self.wait_ack(rid, timeout)
        result = self.wait(rid, timeout)
        return rid, ack, result

    def poll(self, timeout_ms: int = 0, timeout: float = 5.0) -> dict:
        return self.call("poll", {"timeout_ms": timeout_ms}, timeout)

    def estop(self, fd: str | None = None, reason: str = "client",
              timeout: float = 5.0) -> dict:
        args: dict = {"reason": reason}
        if fd:
            args["fd"] = fd
        return self.call("estop", args, timeout)

    def stat(self, fd: str, timeout: float = 5.0) -> dict:
        return self.call("stat", {"fd": fd}, timeout)

    def device_list(self, timeout: float = 5.0) -> dict:
        return self.call("device_list", {}, timeout)

    @property
    def connected(self) -> bool:
        return self._connected

    def latest_state(self) -> dict | None:
        with self._lock:
            return self._latest_state

    def drain_inbox(self) -> list[dict]:
        with self._lock:
            out, self._inbox = self._inbox, []
            return out

    def wait_state(self, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        with self._cv:
            while self._latest_state is None and not self._stop.is_set():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("no state")
                self._cv.wait(min(left, 0.1))
            if self._latest_state is None:
                raise TimeoutError("no state")
            return self._latest_state

    def drain_events(self) -> list[dict]:
        with self._lock:
            out, self._events = self._events, []
            return out
