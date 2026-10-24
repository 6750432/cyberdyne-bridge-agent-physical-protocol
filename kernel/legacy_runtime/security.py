#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Security primitives for the CBAP Kernel.

These are deliberately small and dependency-free:

  peer_credentials   local Unix-socket identity
  CapabilityPolicy   per-agent device + syscall grants
  AuditChain         append-only, hash-chained JSONL
  TokenFile          private kernel token shared with local clients
  AnomalyMonitor     fail-closed counters for impossible/abusive events
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import os
import queue
import secrets
import struct
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


# ── identity ─────────────────────────────────────────────────

def peer_credentials(sock) -> dict | None:
    """Return {pid, uid, gid} for a connected Linux AF_UNIX socket."""
    try:
        raw = sock.getsockopt(
            getattr(__import__("socket"), "SOL_SOCKET"),
            getattr(__import__("socket"), "SO_PEERCRED"),
            struct.calcsize("3i"),
        )
        pid, uid, gid = struct.unpack("3i", raw)
        return {"pid": pid, "uid": uid, "gid": gid}
    except (AttributeError, OSError, ValueError):
        return None


# ── capabilities ──────────────────────────────────────────────

DEFAULT_POLICY: dict[str, Any] = {
    "default": {
        "devices": ["*"],
        "capabilities": ["read", "write", "lease"],
    },
    "agents": {},
}
VALID_CAPS = {"read", "write", "lease", "estop"}


class PolicyError(ValueError):
    pass


class CapabilityPolicy:
    def __init__(self, source: str | dict | None = None):
        if source is None:
            data = json.loads(json.dumps(DEFAULT_POLICY))
        elif isinstance(source, dict):
            data = json.loads(json.dumps(source))
        else:
            with open(source, encoding="utf-8") as f:
                data = json.load(f)
        if not isinstance(data, dict):
            raise PolicyError("policy must be an object")
        default = data.get("default") or {}
        self.default_devices = list(default.get("devices") or ["*"])
        self.default_caps = set(default.get("capabilities") or
                                ["read", "write", "lease"])
        self.agents: dict[str, dict] = {}
        for name, grant in (data.get("agents") or {}).items():
            if not isinstance(grant, dict):
                raise PolicyError(f"agent grant must be object: {name}")
            caps = set(grant.get("capabilities") or self.default_caps)
            unknown = caps - VALID_CAPS
            if unknown:
                raise PolicyError(f"unknown capabilities for {name}: {sorted(unknown)}")
            self.agents[str(name)] = {
                "devices": list(grant.get("devices") or self.default_devices),
                "capabilities": caps,
            }

    def grant(self, agent_id: str, operator: bool = False) -> dict:
        if operator:
            return {"devices": ["*"],
                    "capabilities": {"read", "write", "lease", "estop"}}
        g = self.agents.get(agent_id)
        if g is None:
            return {"devices": list(self.default_devices),
                    "capabilities": set(self.default_caps)}
        return {"devices": list(g["devices"]),
                "capabilities": set(g["capabilities"])}

    @staticmethod
    def device_allowed(device_id: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatchcase(device_id, p) for p in patterns)


# ── audit chain ──────────────────────────────────────────────

class AuditChain:
    """Hash-chained JSONL.  The chain is tamper-evident, not tamper-proof."""

    def __init__(self, path: str, mirror_path: str | None = None,
                 lock: threading.Lock | None = None,
                 signing_key: str | None = None,
                 remote_url: str | None = None,
                 remote_token: str | None = None):
        self.path = os.path.abspath(path)
        self.mirror_path = os.path.abspath(mirror_path) if mirror_path else None
        self.signing_key = signing_key
        self.remote_url = remote_url
        self.remote_token = remote_token
        self._lock = lock or threading.Lock()
        self._last_hash = ""
        self._remote_q: queue.Queue | None = None
        self._remote_failures = 0
        self._load_tail()
        if self.remote_url:
            self._remote_q = queue.Queue(maxsize=1000)
            threading.Thread(target=self._remote_worker,
                             name="cbap-audit-remote", daemon=True).start()

    def _load_tail(self) -> None:
        try:
            with open(self.path, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = max(0, f.tell() - 16384)
                f.seek(pos)
                lines = f.read().decode("utf-8", "replace").splitlines()
            for line in reversed(lines):
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and row.get("hash"):
                        self._last_hash = str(row["hash"])
                        return
                except Exception:
                    continue
        except OSError:
            pass

    @staticmethod
    def _canonical(row: dict) -> str:
        return json.dumps(row, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    def append(self, event: str, **fields: Any) -> dict:
        with self._lock:
            row = {"t": int(time.time() * 1000), "event": str(event)}
            row.update(fields)
            prev = self._last_hash
            body = self._canonical(row)
            digest = hashlib.sha256((prev + "\n" + body).encode("utf-8")).hexdigest()
            row["prev"] = prev
            row["hash"] = digest
            if self.signing_key:
                row["mac"] = hmac.new(
                    self.signing_key.encode("utf-8"),
                    (prev + "\n" + body).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
            line = self._canonical(row) + "\n"
            self._append_file(self.path, line, 0o600)
            if self.mirror_path:
                self._append_file(self.mirror_path, line, 0o600)
            if self._remote_q is not None:
                try:
                    self._remote_q.put_nowait(line)
                except queue.Full:
                    self._remote_failures += 1
            self._last_hash = digest
            return row

    @staticmethod
    def _append_file(path: str, line: str, mode: int) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def verify(self) -> tuple[bool, str]:
        prev = ""
        try:
            with open(self.path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    row = json.loads(line)
                    got = row.pop("hash", "")
                    claimed_prev = row.pop("prev", "")
                    claimed_mac = row.pop("mac", None)
                    if claimed_prev != prev:
                        return False, f"prev mismatch at line {n}"
                    calc = hashlib.sha256(
                        (prev + "\n" + self._canonical(row)).encode("utf-8")
                    ).hexdigest()
                    if not hmac.compare_digest(calc, got):
                        return False, f"hash mismatch at line {n}"
                    if self.signing_key:
                        want = hmac.new(
                            self.signing_key.encode("utf-8"),
                            (claimed_prev + "\n" + self._canonical(row)).encode("utf-8"),
                            hashlib.sha256,
                        ).hexdigest()
                        if not claimed_mac or not hmac.compare_digest(want, claimed_mac):
                            return False, f"mac mismatch at line {n}"
                    prev = got
            return True, "ok"
        except (OSError, ValueError) as e:
            return False, str(e)


    def _remote_worker(self) -> None:
        assert self.remote_url is not None
        while True:
            line = self._remote_q.get()
            req = urllib.request.Request(
                self.remote_url, data=line.encode("utf-8"), method="POST",
                headers={"Content-Type": "application/x-ndjson",
                         **({"Authorization": f"Bearer {self.remote_token}"}
                            if self.remote_token else {})},
            )
            try:
                with urllib.request.urlopen(req, timeout=3) as r:
                    r.read(1)
            except Exception:
                self._remote_failures += 1


# ── token file ───────────────────────────────────────────────

class TokenFile:
    def __init__(self, socket_path: str, token: str | None = None,
                 suffix: str = ".token"):
        self.path = socket_path + suffix
        self.token = token or secrets.token_urlsafe(32)

    def write(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, self.token.encode("ascii"))
        finally:
            os.close(fd)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def read(self) -> str | None:
        try:
            with open(self.path, encoding="ascii") as f:
                return f.read().strip()
        except OSError:
            return None

    def remove(self) -> None:
        try:
            os.unlink(self.path)
        except OSError:
            pass


# ── anomaly monitor ─────────────────────────────────────────

class AnomalyMonitor:
    def __init__(self, window_s: float = 60.0, auth_threshold: int = 5,
                 estop_threshold: int = 10):
        self.window_s = window_s
        self.auth_threshold = auth_threshold
        self.estop_threshold = estop_threshold
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, kind: str) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._events.setdefault(kind, [])
            q.append(now)
            cutoff = now - self.window_s
            while q and q[0] < cutoff:
                q.pop(0)
            return len(q)

    def degraded(self, kind: str) -> bool:
        with self._lock:
            q = self._events.get(kind, [])
            cutoff = time.monotonic() - self.window_s
            q = [t for t in q if t >= cutoff]
            self._events[kind] = q
            if kind == "auth_failure":
                return len(q) >= self.auth_threshold
            if kind == "estop_burst":
                return len(q) >= self.estop_threshold
            return False
