#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP-U gateway for the legacy Minecraft hand.

This is deliberately a *thin* first layer:

  Agent --CBAP-U--> KernelServer --McDriver--> node/server.js

It does not modify bridge.py or node/server.js. It is meant to prove the
syscall shape (open/read/write/poll/estop) against the real legacy protocol,
with a fake hand in tests.

Known v0 limits (documented, not hidden):
  - one body / one device;
  - lease is global (one writer);
  - legacy cmdResult has no request id, so results are matched FIFO per verb;
  - cancel marks the CBAP request canceled, but cannot always stop the
    already-sent legacy action;
  - estop latches the gateway into safe mode; recovery is close/open or
    restart (admin recovery comes later).
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import protocol

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CBAP_SOCKET = os.path.join(ROOT, "cbap.sock")


@dataclass
class Fd:
    fd: str
    agent_id: str
    device_id: str
    mode: str
    opened_at: float = field(default_factory=time.time)
    lease_id: str | None = None
    lease_expires: float = 0.0
    closed: bool = False
    driver: Any = None


@dataclass
class Pending:
    session: "Session"
    request_id: str
    cmd: str
    deadline: float
    timer: threading.Timer | None = None
    done: bool = False
    idem_key: tuple | None = None
    driver: Any = None


class Session:
    def __init__(self, sock: socket.socket, addr: Any):
        self.sock = sock
        self.addr = addr
        self.agent_id: str | None = None
        self.capabilities: set[str] = set()
        self.fds: dict[str, Fd] = {}
        self.send_lock = threading.Lock()
        self.events: list[dict] = []
        self.event_cv = threading.Condition()
        self.closed = False
        self.session_id = protocol.new_id("s")

    def send(self, msg: dict) -> bool:
        if self.closed:
            return False
        with self.send_lock:
            try:
                protocol.send_line(self.sock, msg)
                return True
            except (OSError, ValueError):
                self.closed = True
                return False

    def push_event(self, ev: dict) -> None:
        with self.event_cv:
            self.events.append(ev)
            self.event_cv.notify_all()

    def drain_events(self) -> list[dict]:
        with self.event_cv:
            out, self.events = self.events, []
            return out


class KernelServer:
    """CBAP-U server + a small kernel-shaped dispatcher."""

    def __init__(self, driver=None, socket_path: str | None = None,
                 kernel_id: str = "cyberdyne-legacy",
                 token: str | None = None,
                 lease_ttl_ms: int = 30000,
                 audit_path: str | None = None,
                 drivers: list | None = None):
        # 多设备：drivers=[legacy, dataflow...]；旧单驱动参数仍然兼容。
        if drivers is None:
            drivers = [driver] if driver is not None else []
        self.drivers = list(drivers)
        if not self.drivers:
            raise ValueError("E_INVAL: at least one driver required")
        for d in self.drivers:
            dev = d.describe() if hasattr(d, "describe") else {}
            safety = (dev or {}).get("safety") or {}
            if not safety.get("estop") or not isinstance(safety.get("watchdog_ms"), int):
                raise ValueError("E_INVAL: driver.safety.estop/watchdog_ms required")
        self.driver = self.drivers[0]  # 兼容旧代码/旧测试
        self.socket_path = os.path.abspath(socket_path or DEFAULT_CBAP_SOCKET)
        self.kernel_id = kernel_id
        self.token = token
        self.lease_ttl_ms = max(1000, int(lease_ttl_ms))
        self.audit_path = audit_path or os.path.join(ROOT, "logs", "cbap-audit.jsonl")

        self._sessions: set[Session] = set()
        self._fds: dict[str, Fd] = {}
        self._pending: dict[tuple, deque[Pending]] = {}
        self._idem: dict[tuple, dict] = {}
        self._leases: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._seq = 0
        self._safe = False
        self._fd_counter = 0

        self._server: socket.socket | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

        # Wire each driver's callbacks with its own identity.
        for d in self.drivers:
            d.on_state = (lambda msg, drv=d: self._on_state(drv, msg))
            d.on_result = (lambda cmd, ok, why, extra, drv=d:
                           self._on_result(drv, cmd, ok, why, extra))
            d.on_event = (lambda ev, drv=d: self._on_event(drv, ev))
            d.on_disconnect = (lambda reason, drv=d: self._on_disconnect(drv, reason))

    # ── lifecycle ──────────────────────────────────────────────

    def start(self, timeout: float = 3.0) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        self._thread = threading.Thread(
            target=self.serve_forever, name="cbap-kernel", daemon=True)
        self._thread.start()
        return self._ready.wait(timeout)

    def serve_forever(self) -> None:
        path = self.socket_path
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server = srv
        try:
            srv.bind(path)
            srv.listen(16)
            srv.settimeout(0.5)
            self._ready.set()
            self._audit("kernel_start", socket=path)
            while not self._stop.is_set():
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                t = threading.Thread(
                    target=self._handle_session, args=(conn, addr),
                    name="cbap-session", daemon=True)
                t.start()
        except OSError as e:
            self._audit("kernel_error", error=str(e))
            raise
        finally:
            self._ready.clear()
            try:
                srv.close()
            except OSError:
                pass
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass

    def stop(self) -> None:
        self._stop.set()
        srv = self._server
        self._server = None
        try:
            if srv:
                srv.close()
        except OSError:
            pass
        with self._lock:
            sessions = list(self._sessions)
        for s in sessions:
            try:
                s.sock.close()
            except OSError:
                pass
            s.closed = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    # ── session loop ──────────────────────────────────────────

    def _handle_session(self, sock: socket.socket, addr: Any) -> None:
        session = Session(sock, addr)
        sock.settimeout(0.5)
        buf = b""
        try:
            while not self._stop.is_set() and not session.closed:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if len(buf) > protocol.MAX_FRAME * 2 and b"\n" not in buf:
                    session.send({
                        "v": protocol.PROTOCOL_VERSION, "type": "error",
                        "id": protocol.new_id("e"), "ts": protocol.now_ms(),
                        "error": protocol.error("E_FRAME", "frame too large"),
                    })
                    buf = b""
                    continue
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if len(line) > protocol.MAX_FRAME:
                        session.send({
                            "v": protocol.PROTOCOL_VERSION, "type": "error",
                            "id": protocol.new_id("e"), "ts": protocol.now_ms(),
                            "error": protocol.error("E_FRAME", "frame too large"),
                        })
                        continue
                    try:
                        msg = protocol.parse_line(line)
                    except (ValueError, UnicodeDecodeError) as e:
                        session.send({
                            "v": protocol.PROTOCOL_VERSION, "type": "error",
                            "id": protocol.new_id("e"), "ts": protocol.now_ms(),
                            "error": protocol.error("E_PROTOCOL", str(e)),
                        })
                        continue

                    if not session.agent_id:
                        ok = self._handle_hello(session, msg)
                        if not ok:
                            return
                        continue
                    self._handle_message(session, msg)
        except Exception as e:
            self._audit("session_error", agent=session.agent_id,
                        error=f"{type(e).__name__}: {e}",
                        where="".join(traceback.format_exc().splitlines()[-3:]))
        finally:
            self._cleanup_session(session)

    def _handle_hello(self, session: Session, msg: dict) -> bool:
        rid = msg.get("id") or protocol.new_id("h")
        if msg.get("type") != "hello":
            session.send({
                "v": protocol.PROTOCOL_VERSION, "type": "error",
                "id": rid, "ts": protocol.now_ms(),
                "error": protocol.error("E_PROTOCOL", "first message must be hello"),
            })
            return False
        if msg.get("v") != protocol.PROTOCOL_VERSION:
            session.send({
                "v": protocol.PROTOCOL_VERSION, "type": "error",
                "id": rid, "ts": protocol.now_ms(),
                "error": protocol.error("E_VERSION",
                                        f"unsupported version: {msg.get('v')}"),
            })
            return False
        if self.token:
            auth = msg.get("auth") or {}
            if auth.get("token") != self.token:
                session.send({
                    "v": protocol.PROTOCOL_VERSION, "type": "error",
                    "id": rid, "ts": protocol.now_ms(),
                    "error": protocol.error("E_AUTH", "bad token"),
                })
                return False
        agent_id = msg.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            session.send({
                "v": protocol.PROTOCOL_VERSION, "type": "error",
                "id": rid, "ts": protocol.now_ms(),
                "error": protocol.error("E_INVAL", "agent_id required"),
            })
            return False
        session.agent_id = agent_id
        session.capabilities = {"read", "write", "lease", "estop"}
        with self._lock:
            self._sessions.add(session)
        devices = []
        for d in self.drivers:
            dev = d.describe()
            devices.append({
                "device_id": dev.get("device_id"),
                "type": dev.get("type"),
                "state": "ready" if d.connected else "offline",
            })
        session.send({
            "v": protocol.PROTOCOL_VERSION,
            "type": "welcome",
            "id": rid,
            "ts": protocol.now_ms(),
            "kernel_id": self.kernel_id,
            "protocol": protocol.PROTOCOL_VERSION,
            "session_id": session.session_id,
            "capabilities": sorted(session.capabilities),
            "limits": {"max_frame": protocol.MAX_FRAME,
                       "max_inflight": 4, "rate_hz": 5},
            "devices": devices,
        })
        self._audit("hello", agent=agent_id, session=session.session_id)
        return True

    def _handle_message(self, session: Session, msg: dict) -> None:
        typ = msg.get("type")
        if typ == "request":
            self._handle_request(session, msg)
            return
        if typ == "cancel":
            self._handle_cancel(session, msg)
            return
        if typ == "ping":
            pong = {"v": protocol.PROTOCOL_VERSION, "type": "pong",
                    "id": msg.get("id") or protocol.new_id("p"),
                    "ts": protocol.now_ms()}
            session.send(pong)
            return
        session.send({
            "v": protocol.PROTOCOL_VERSION, "type": "error",
            "id": msg.get("id") or protocol.new_id("e"),
            "ts": protocol.now_ms(),
            "error": protocol.error("E_PROTOCOL",
                                    f"unsupported message type: {typ}"),
        })

    def _handle_request(self, session: Session, msg: dict) -> None:
        rid = msg.get("id")
        if not isinstance(rid, str) or not rid:
            session.send({
                "v": protocol.PROTOCOL_VERSION, "type": "error",
                "id": protocol.new_id("e"), "ts": protocol.now_ms(),
                "error": protocol.error("E_INVAL", "request id required"),
            })
            return
        op = msg.get("op")
        args = msg.get("args") or {}
        if not isinstance(op, str) or not op:
            self._result(session, rid, False,
                         err=protocol.error("E_INVAL", "op required"))
            return
        if not isinstance(args, dict):
            self._result(session, rid, False,
                         err=protocol.error("E_INVAL", "args must be object"))
            return
        if op not in ("open", "close", "read", "write", "ioctl", "poll",
                      "lease", "estop", "stat", "device_list", "resume"):
            self._result(session, rid, False,
                         err=protocol.error("E_NOTSUP", f"unknown op: {op}"))
            return
        required = {
            "open": "read", "read": "read", "poll": "read",
            "stat": "read", "device_list": "read",
            "write": "write", "close": "write", "ioctl": "read",
            "lease": "lease", "estop": "estop", "resume": "admin",
        }.get(op)
        if required and required not in session.capabilities:
            self._result(session, rid, False,
                         err=protocol.error("E_PERM",
                                            f"capability required: {required}"))
            return
        try:
            if op == "open":
                self._op_open(session, rid, args)
            elif op == "close":
                self._op_close(session, rid, args)
            elif op == "read":
                self._op_read(session, rid, args)
            elif op == "write":
                self._op_write(session, rid, args, msg)
            elif op == "ioctl":
                self._op_ioctl(session, rid, args)
            elif op == "poll":
                self._op_poll(session, rid, args)
            elif op == "lease":
                self._op_lease(session, rid, args)
            elif op == "estop":
                self._op_estop(session, rid, args)
            elif op == "stat":
                self._op_stat(session, rid, args)
            elif op == "device_list":
                self._op_device_list(session, rid)
            elif op == "resume":
                self._op_resume(session, rid, args)
        except Exception as e:
            self._result(session, rid, False,
                         err=protocol.error(
                             getattr(e, "code", "E_INTERNAL"),
                             getattr(e, "message", str(e))))

    # ── helpers ───────────────────────────────────────────────

    def _result(self, session: Session, rid: str, ok: bool,
                payload: dict | None = None, facts: dict | None = None,
                err: dict | None = None) -> None:
        session.send(protocol.result(rid, ok, payload, facts, err))

    def _get_fd(self, session: Session, args: dict) -> Fd:
        fd = args.get("fd")
        if not isinstance(fd, str) or not fd:
            raise _OpError("E_INVAL", "fd required")
        with self._lock:
            f = session.fds.get(fd)
            if not f or f.closed:
                raise _OpError("E_NOENT", f"fd not found: {fd}")
            return f

    def _lease_for_fd(self, fd: Fd) -> dict | None:
        with self._lock:
            lease = self._leases.get(fd.device_id)
            if not lease:
                return None
            if lease["expires_at"] <= time.time():
                self._leases.pop(fd.device_id, None)
                return None
            if lease["fd"] != fd.fd:
                return None
            return lease

    def _acquire_lease(self, session: Session, fd: Fd, ttl_ms: int) -> dict:
        with self._lock:
            lease = self._leases.get(fd.device_id)
            now = time.time()
            if lease and lease["expires_at"] > now and lease["fd"] != fd.fd:
                raise _OpError("E_BUSY", "device is leased by another writer")
            lease_id = lease["lease_id"] if lease and lease["fd"] == fd.fd \
                else protocol.new_id("l")
            self._leases[fd.device_id] = {
                "lease_id": lease_id,
                "fd": fd.fd,
                "device_id": fd.device_id,
                "agent_id": session.agent_id,
                # CBAP 租约按调用方给的 TTL 生效；50ms 必须真的是 50ms。
                "expires_at": now + max(1, int(ttl_ms)) / 1000.0,
            }
            fd.lease_id = lease_id
            fd.lease_expires = self._leases[fd.device_id]["expires_at"]
            return dict(self._leases[fd.device_id])

    def _release_lease(self, fd: Fd) -> bool:
        with self._lock:
            lease = self._leases.get(fd.device_id)
            if lease and lease["fd"] == fd.fd:
                self._leases.pop(fd.device_id, None)
                fd.lease_id = None
                fd.lease_expires = 0.0
                return True
            return False

    # ── syscalls ─────────────────────────────────────────────

    def _op_open(self, session: Session, rid: str, args: dict) -> None:
        device_id = args.get("device_id")
        mode = args.get("mode", "rw")
        if mode not in ("r", "rw", "exclusive"):
            raise _OpError("E_INVAL", "mode must be r/rw/exclusive")
        dev = None
        for d in self.drivers:
            if d.describe().get("device_id") == device_id:
                dev = d
                break
        if dev is None:
            raise _OpError("E_NOENT", f"unknown device: {device_id}")
        with self._lock:
            self._fd_counter += 1
            fd_id = f"fd-{self._fd_counter}"
            f = Fd(fd=fd_id, agent_id=session.agent_id or "",
                   device_id=device_id, mode=mode, driver=dev)
            session.fds[fd_id] = f
            self._fds[fd_id] = f
        if mode == "exclusive":
            try:
                self._acquire_lease(session, f, self.lease_ttl_ms)
            except Exception:
                with self._lock:
                    session.fds.pop(fd_id, None)
                    self._fds.pop(fd_id, None)
                raise
        self._result(session, rid, True, payload={"fd": fd_id,
                                                  "device_id": device_id})
        self._audit("open", agent=session.agent_id, id=rid, fd=fd_id,
                    mode=mode)

    def _op_close(self, session: Session, rid: str, args: dict) -> None:
        f = self._get_fd(session, args)
        held = self._release_lease(f)
        if held:
            f.driver.estop()
        f.closed = True
        with self._lock:
            session.fds.pop(f.fd, None)
            self._fds.pop(f.fd, None)
        self._result(session, rid, True, payload={"closed": True})
        self._audit("close", agent=session.agent_id, id=rid, fd=f.fd,
                    released_lease=held)

    def _op_read(self, session: Session, rid: str, args: dict) -> None:
        f = self._get_fd(session, args)
        channel = args.get("channel")
        timeout_ms = args.get("timeout_ms", 0)
        if not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise _OpError("E_INVAL", "timeout_ms must be a non-negative int")
        state = f.driver.wait_state(timeout_ms / 1000.0)
        if state is None:
            if timeout_ms <= 0:
                raise _OpError("E_AGAIN", "no state yet")
            raise _OpError("E_TIMEOUT", "no state before timeout")
        payload = _state_payload(state)
        if channel:
            if channel not in payload:
                raise _OpError("E_INVAL", f"unknown channel: {channel}")
            payload = {channel: payload[channel]}
        self._result(session, rid, True, payload={"frame": payload},
                     facts={"state_seq": payload.get("legacy_seq")})
        _ = f

    def _op_write(self, session: Session, rid: str, args: dict, msg: dict) -> None:
        if self._safe:
            raise _OpError("E_SAFETY", "gateway is in safe mode after estop")
        f = self._get_fd(session, args)
        if f.mode == "r":
            raise _OpError("E_PERM", "fd is read-only")
        if not self._lease_for_fd(f):
            raise _OpError("E_BUSY", "write requires a lease")
        frame = args.get("frame")
        if not isinstance(frame, dict):
            raise _OpError("E_INVAL", "frame must be an object")
        try:
            legacy = f.driver.map_action(frame)
        except Exception as e:
            raise _OpError(getattr(e, "code", "E_INVAL"),
                           getattr(e, "message", str(e)))
        cmd = str(legacy.get("cmd") or "unknown")
        deadline_ms = msg.get("deadline_ms", 5000)
        if not isinstance(deadline_ms, int) or deadline_ms <= 0:
            deadline_ms = 5000
        idem_key = msg.get("idempotency_key")
        key = (session.agent_id, f.device_id, idem_key) if idem_key else None
        if key:
            with self._lock:
                cached = self._idem.get(key)
                if cached:
                    if cached.get("state") == "pending":
                        raise _OpError("E_BUSY", "same idempotency_key in flight")
                    # 幂等重放也必须先 ack 再 result，保持与正常 write 同一生命周期。
                    session.send({"v": protocol.PROTOCOL_VERSION, "type": "ack",
                                  "id": rid, "ts": protocol.now_ms(),
                                  "state": "accepted"})
                    self._result(session, rid, cached.get("ok", False),
                                 payload=cached.get("payload"),
                                 facts=cached.get("facts"),
                                 err=cached.get("error"))
                    return

        p = Pending(session=session, request_id=rid, cmd=cmd,
                    deadline=time.monotonic() + deadline_ms / 1000.0,
                    idem_key=key, driver=f.driver)
        with self._lock:
            self._pending.setdefault((f.device_id, cmd), deque()).append(p)
            if key:
                self._idem[key] = {"state": "pending", "id": rid}
        # ack first, then execute
        session.send({"v": protocol.PROTOCOL_VERSION, "type": "ack",
                      "id": rid, "ts": protocol.now_ms(),
                      "state": "accepted"})
        p.timer = threading.Timer(deadline_ms / 1000.0, self._expire, args=(p,))
        p.timer.daemon = True
        p.timer.start()
        ok_send = f.driver.send(legacy)
        if not ok_send:
            self._finish_pending(p, False, None, None,
                                 protocol.error("E_IO", "hand is not connected"))
        self._audit("write", agent=session.agent_id, id=rid, fd=f.fd,
                    op=frame.get("op"), cmd=cmd,
                    idem=bool(idem_key))

    def _op_ioctl(self, session: Session, rid: str, args: dict) -> None:
        f = self._get_fd(session, args)
        request = args.get("request")
        payload = args.get("args") or {}
        if request == "scan":
            radius = payload.get("radius", 12)
            step = payload.get("step", 2)
            legacy = {"cmd": "scan_environment", "半径": radius, "步长": step}
            cmd = "scan_environment"
        elif request == "watch":
            blocks = payload.get("blocks") or []
            legacy = {"cmd": "watch_blocks", "list": blocks}
            cmd = "watch_blocks"
        elif request == "watch_items":
            items = payload.get("items") or payload.get("list") or ["*"]
            legacy = {"cmd": "watch_items", "list": items}
            cmd = "watch_items"
        elif request == "furnace_watch":
            legacy = {"cmd": "furnace_watch", "p": payload.get("p"),
                      "每_ms": payload.get("每_ms", 2000)}
            cmd = "furnace_watch"
        else:
            raise _OpError("E_NOTSUP", f"unknown ioctl: {request}")
        p = Pending(session=session, request_id=rid, cmd=cmd,
                    deadline=time.monotonic() + 5.0, driver=f.driver)
        with self._lock:
            self._pending.setdefault((f.device_id, cmd), deque()).append(p)
        session.send({"v": protocol.PROTOCOL_VERSION, "type": "ack",
                      "id": rid, "ts": protocol.now_ms(),
                      "state": "accepted"})
        p.timer = threading.Timer(5.0, self._expire, args=(p,))
        p.timer.daemon = True
        p.timer.start()
        if not f.driver.send(legacy):
            self._finish_pending(p, False, None, None,
                                 protocol.error("E_IO", "hand is not connected"))
        _ = f

    def _op_lease(self, session: Session, rid: str, args: dict) -> None:
        f = self._get_fd(session, args)
        if f.mode == "r":
            raise _OpError("E_PERM", "cannot lease a read-only fd")
        try:
            _h = f.driver.health()
        except Exception:
            _h = {}
        if isinstance(_h, dict) and _h.get("ok") is False:
            raise _OpError("E_SAFETY", "driver health is not ok; refusing new lease")
        ttl = args.get("ttl_ms", self.lease_ttl_ms)
        lease = self._acquire_lease(session, f, ttl)
        self._result(session, rid, True, payload={
            "lease_id": lease["lease_id"],
            "expires_at": int(lease["expires_at"] * 1000),
        })

    def _op_estop(self, session: Session, rid: str, args: dict) -> None:
        self._safe = True
        f = None
        if args.get("fd"):
            f = self._get_fd(session, args)
            targets = [f.driver]
            with self._lock:
                self._leases.pop(f.device_id, None)
        else:
            targets = list(self.drivers)
            with self._lock:
                self._leases.clear()
        oks = []
        safe_state = "idle"
        for d in targets:
            try:
                oks.append(bool(d.estop()))
            except Exception:
                oks.append(False)
            safe_state = ((d.describe().get("safety") or {}).get("safe_state")
                          or safe_state)
        self._result(session, rid, True, payload={
            "safe_state": safe_state,
            "driver_ok": all(oks) if oks else False,
        })
        self._audit("estop", agent=session.agent_id, id=rid,
                    reason=args.get("reason"), driver_ok=all(oks) if oks else False)

    def _op_stat(self, session: Session, rid: str, args: dict) -> None:
        f = self._get_fd(session, args)
        with self._lock:
            lease = dict(self._leases.get(f.device_id) or {}) or None
            pending = sum(len(q) for q in self._pending.values())
        self._result(session, rid, True, payload={
            "device": f.driver.describe(),
            "health": f.driver.health(),
            "lease": lease,
            "safe": self._safe,
            "pending": pending,
            "fd": f.fd,
        })

    def _op_device_list(self, session: Session, rid: str) -> None:
        devices = []
        for d in self.drivers:
            dev = d.describe()
            devices.append({
                "device_id": dev.get("device_id"),
                "type": dev.get("type"),
                "state": "ready" if d.connected else "offline",
            })
        self._result(session, rid, True, payload={"devices": devices})

    def _op_resume(self, session: Session, rid: str, args: dict) -> None:
        # v0: only the local operator may resume; no admin auth yet.
        raise _OpError("E_PERM", "resume requires admin (not implemented in v0)")

    def _op_poll(self, session: Session, rid: str, args: dict) -> None:
        timeout_ms = args.get("timeout_ms", 0)
        if not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise _OpError("E_INVAL", "timeout_ms must be a non-negative int")
        deadline = time.monotonic() + timeout_ms / 1000.0
        with session.event_cv:
            while not session.events and not session.closed:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                session.event_cv.wait(min(left, 0.1))
            events, session.events = session.events, []
        self._result(session, rid, True, payload={"events": events})

    def _handle_cancel(self, session: Session, msg: dict) -> None:
        rid = msg.get("id") or protocol.new_id("c")
        target = msg.get("target")
        if not isinstance(target, str) or not target:
            self._result(session, rid, False,
                         err=protocol.error("E_INVAL", "target required"))
            return
        found = None
        with self._lock:
            for q in self._pending.values():
                for p in q:
                    if p.request_id == target and not p.done:
                        found = p
                        break
                if found:
                    break
        if not found:
            self._result(session, rid, True, payload={"already_done": True})
            return
        if found.timer:
            found.timer.cancel()
        self._finish_pending(found, False, None, None,
                             protocol.error("E_CANCELED", "canceled by agent"))
        self._result(session, rid, True, payload={"canceled": target})

    # ── result / state / event plumbing ───────────────────────

    def _finish_pending(self, p: Pending, ok: bool, payload: dict | None,
                        facts: dict | None, err: dict | None) -> None:
        with self._lock:
            if p.done:
                return
            p.done = True
            dev_id = p.driver.describe().get("device_id") if p.driver else None
            key = (dev_id, p.cmd)
            q = self._pending.get(key)
            if q:
                try:
                    q.remove(p)
                except ValueError:
                    pass
                if not q:
                    self._pending.pop(key, None)
            if p.idem_key:
                self._idem[p.idem_key] = {
                    "state": "done", "ok": ok, "payload": payload,
                    "facts": facts, "error": err,
                }
        if p.timer:
            p.timer.cancel()
        p.session.send(protocol.result(p.request_id, ok, payload, facts, err))

    def _expire(self, p: Pending) -> None:
        self._finish_pending(p, False, None, None,
                             protocol.error("E_TIMEOUT", "deadline exceeded",
                                            retryable=True))

    def _on_result(self, driver, cmd: str, ok: bool, why: str | None,
                   extra: dict) -> None:
        dev_id = driver.describe().get("device_id") if driver else None
        key = (dev_id, cmd)
        with self._lock:
            q = self._pending.get(key)
            p = q.popleft() if q else None
            if q is not None and not q:
                self._pending.pop(key, None)
        if p is None:
            return
        if p.done:
            return
        extra = _ascii_extra(extra or {})
        if ok:
            self._finish_pending(p, True, extra, extra, None)
        else:
            self._finish_pending(
                p, False, extra, None,
                protocol.error("E_IO", why or "device rejected the command",
                               retryable=True))

    def _on_state(self, driver, state_msg: dict) -> None:
        payload = _state_payload(state_msg)
        dev_id = driver.describe().get("device_id") if driver else None
        with self._lock:
            self._seq += 1
            seq = self._seq
            sessions = [s for s in self._sessions
                        if s.agent_id and not s.closed
                        and any(f.device_id == dev_id for f in s.fds.values())]
        if not sessions:
            return
        msg = protocol.state(seq, dev_id, payload, t_mono=protocol.monotonic_ms())
        for s in sessions:
            s.send(msg)

    def _on_event(self, driver, ev: dict) -> None:
        kind = str(ev.get("kind") or "event")
        payload = {k: v for k, v in ev.items()
                   if k not in ("type", "kind", "t", "bot")}
        payload.setdefault("device_id",
                           driver.describe().get("device_id") if driver else None)
        msg = protocol.event(kind, payload)
        with self._lock:
            sessions = [s for s in self._sessions if s.agent_id and not s.closed]
        for s in sessions:
            s.push_event({"kind": kind, "payload": payload, "ts": msg["ts"]})

    def _on_disconnect(self, driver, reason: str) -> None:
        self._on_event(driver, {"type": "event", "kind": "device_offline",
                                "why": str(reason)[:200]})
        with self._lock:
            pend = [p for q in self._pending.values() for p in q
                    if p.driver is driver]
            # 驱动崩了/断线：该设备的租约立刻释放，不让新 Agent 等到 TTL。
            for _dev, _lease in list(self._leases.items()):
                _f = self._fds.get(_lease.get("fd"))
                if _f is not None and _f.driver is driver:
                    self._leases.pop(_dev, None)
        for p in pend:
            self._finish_pending(
                p, False, None, None,
                protocol.error("E_IO", f"hand disconnected: {reason}",
                               retryable=True))

    def _cleanup_session(self, session: Session) -> None:
        with self._lock:
            self._sessions.discard(session)
            fds = list(session.fds.values())
            for f in fds:
                session.fds.pop(f.fd, None)
                self._fds.pop(f.fd, None)
            pend = []
            for cmd, q in list(self._pending.items()):
                for p in list(q):
                    if p.session is session:
                        pend.append(p)
                        try:
                            q.remove(p)
                        except ValueError:
                            pass
                if not q:
                    self._pending.pop(cmd, None)
        for f in fds:
            if self._release_lease(f):
                f.driver.estop()
        for p in pend:
            p.done = True
            if p.timer:
                p.timer.cancel()
        session.closed = True
        with session.event_cv:
            session.event_cv.notify_all()
        try:
            session.sock.close()
        except OSError:
            pass
        self._audit("session_end", agent=session.agent_id,
                    session=session.session_id, fds=len(fds))

    def _audit(self, event: str, **fields: Any) -> None:
        try:
            os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)
            row = {"t": protocol.now_ms(), "event": event}
            row.update(fields)
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass


class _OpError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _ascii_extra(extra: dict) -> dict:
    """Legacy hand emits some Chinese keys; CBAP wire fields MUST be ASCII."""
    rename = {
        "方块类": "block_kinds",
        "实体": "entities",
        "要找": "wanted",
        "命中": "hits",
        "盯着": "watching",
    }
    return {rename.get(k, k): v for k, v in extra.items()}


def _state_payload(s: dict) -> dict:
    """Legacy state -> CBAP payload. Keep MC fields under named channels."""
    return {
        "body": {
            "pos": s.get("pos"),
            "hp": s.get("hp"),
            "food": s.get("food"),
            "on_ground": s.get("onGround"),
            "held": s.get("held"),
            "durability": s.get("durability"),
            "acting": s.get("acting"),
        },
        "inventory": {
            "items": s.get("items") or {},
            "foods": s.get("foods") or [],
            "weapons": s.get("weapons") or [],
        },
        "world": {
            "scan": s.get("scan"),
            "blocks": s.get("blocks") or [],
            "furnace": s.get("furnace"),
            "chat": s.get("chat") or [],
        },
        "players": s.get("players") or [],
        "near": s.get("near") or [],
        "threats": s.get("threats") or [],
        "drops": s.get("drops") or [],
        "stuck": {
            "count": s.get("stuck_count"),
            "ms": s.get("stuck_ms"),
            "dir": s.get("stuck_dir"),
        },
        "attacked_by": s.get("attacked_by"),
        "legacy_seq": s.get("seq"),
        "legacy_t": s.get("t"),
    }
