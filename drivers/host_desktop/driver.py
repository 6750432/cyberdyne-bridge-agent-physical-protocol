#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP-D host desktop driver: a deliberately tiny, allowlisted action surface.

This is the host side of the VM -> host CBAP test. It exposes exactly:

    host://desktop   write_file / list / stat / ping

No shell, no arbitrary path, no executable bits. All paths must stay under the
configured test root (default: ~/Desktop/CBAP-Host-Test).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class HostActionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class HostDesktopDriver:
    DEVICE_ID = "host://desktop"
    MAX_BYTES = 64 * 1024

    def __init__(self, root: str | os.PathLike[str] | None = None):
        default = Path.home() / "Desktop" / "CBAP-Host-Test"
        self.root = Path(root or default).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Refuse a symlinked allowlist root.
        if self.root.is_symlink():
            raise RuntimeError("host test root may not be a symlink")
        self.connected = True
        self._safe = False
        self._last_state: dict | None = None
        self._last_state_at = 0.0
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_connect = None
        self.on_disconnect = None

    # ── path safety ───────────────────────────────────────────

    def _safe_path(self, rel: str) -> Path:
        if not isinstance(rel, str) or not rel or "\x00" in rel:
            raise HostActionError("E_INVAL", "path must be a non-empty string")
        if os.path.isabs(rel):
            raise HostActionError("E_INVAL", "absolute paths are not allowed")
        p = (self.root / rel).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise HostActionError("E_PERM", "path escapes the host test root")
        # Reject symlinked components, including an existing target.
        cur = self.root
        for part in Path(rel).parts:
            cur = cur / part
            if cur.is_symlink():
                raise HostActionError("E_PERM", "symlinks are not allowed")
        return p

    # ── driver ABI ────────────────────────────────────────────

    def describe(self) -> dict:
        actions = {
            "write_file": {
                "args": {"path": "relative-path", "content": "string<=65536"},
                "result": {"path": "string", "bytes": "int", "sha256": "hex"},
                "danger": "normal", "idempotent": True,
            },
            "list": {
                "args": {"path?": "relative-path"},
                "result": {"entries": "array"}, "danger": "normal",
                "idempotent": True,
            },
            "stat": {
                "args": {"path": "relative-path"},
                "result": {"bytes": "int", "sha256": "hex"},
                "danger": "normal", "idempotent": True,
            },
            "ping": {"args": {}, "result": {"pong": "bool"},
                     "danger": "normal", "idempotent": True},
        }
        return {
            "device_id": self.DEVICE_ID,
            "type": "host-desktop",
            "name": "CBAP Host Desktop Test",
            "transport": "local-allowlist",
            "contract": "cbap-device-v1",
            "class": "filesystem",
            "version": "1.0",
            "legacy": False,
            "actions": actions,
            "capabilities": ["read", "write", "lease", "estop"],
            "trust": {
                "source": "host-filesystem",
                "independent": False,
                "attestation": "local-hash",
                "level": 1,
            },
            "isolation": {
                "process": "host-bridge",
                "uid": os.getuid(),
                "sandbox": "none",
                "network": "local",
            },
            "resources": {
                "max_inflight": 4,
                "rate_hz": 10,
                "max_bytes": int(self.MAX_BYTES),
                "max_sessions": 4,
            },
            "safety": {"estop": True, "watchdog_ms": 10000,
                       "safe_state": "read-only"},
            "root": str(self.root),
        }

    def safe_state(self) -> str:
        return "read-only" if self._safe else "unknown"

    def health(self) -> dict:
        return {
            "ok": bool(self.connected and not self._safe),
            "connected": bool(self.connected),
            "safe": bool(self._safe),
            "state_age_ms": self.state_age_ms(),
            "device_id": self.DEVICE_ID,
            "root": str(self.root),
        }

    def latest_state(self) -> dict | None:
        return dict(self._last_state) if self._last_state else None

    def state_age_ms(self) -> int | None:
        if not self._last_state_at:
            return None
        return int((time.time() - self._last_state_at) * 1000)

    def wait_state(self, timeout_s: float) -> dict | None:
        # The host action is synchronous; a completed action is the state.
        if self._last_state is not None:
            return dict(self._last_state)
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while self._last_state is None and time.monotonic() < deadline:
            time.sleep(0.02)
        return dict(self._last_state) if self._last_state else None

    def map_action(self, frame: dict) -> dict:
        if not isinstance(frame, dict):
            raise HostActionError("E_INVAL", "frame must be an object")
        op = frame.get("op")
        args = frame.get("args") or {}
        if not isinstance(op, str) or not op:
            raise HostActionError("E_INVAL", "frame.op must be a string")
        if not isinstance(args, dict):
            raise HostActionError("E_INVAL", "frame.args must be an object")
        if op not in ("write_file", "list", "stat", "ping"):
            raise HostActionError("E_NOTSUP", f"host op not supported: {op}")
        return {"cmd": op, "args": args}

    def send(self, command: dict) -> bool:
        cmd = str((command or {}).get("cmd") or "")
        args = (command or {}).get("args") or {}
        if self._safe:
            self._emit(cmd, False, "E_SAFETY: host test driver is stopped", {})
            return True
        try:
            if cmd == "write_file":
                extra = self._write_file(args)
            elif cmd == "list":
                extra = self._list(args)
            elif cmd == "stat":
                extra = self._stat(args)
            elif cmd == "ping":
                extra = {"pong": True, "root": str(self.root)}
            else:
                raise HostActionError("E_NOTSUP", f"unknown host command: {cmd}")
        except HostActionError as e:
            self._emit(cmd, False, f"{e.code}: {e.message}", {})
            return True
        except Exception as e:
            self._emit(cmd, False, f"E_IO: {type(e).__name__}: {e}", {})
            return True
        self._touch({"last_cmd": cmd, "last_result": extra})
        self._emit(cmd, True, None, extra)
        return True

    def estop(self) -> bool:
        self._safe = True
        self._touch({"estop": True})
        return True

    def cancel(self) -> None:
        # Single short local filesystem operation; nothing to kill.
        return None

    def close(self) -> None:
        self.connected = False
        if self.on_disconnect:
            try:
                self.on_disconnect("host driver closed")
            except Exception:
                pass

    # ── actions ───────────────────────────────────────────────

    def _write_file(self, args: dict) -> dict:
        rel = args.get("path")
        content = args.get("content")
        if not isinstance(content, str):
            raise HostActionError("E_INVAL", "content must be a string")
        data = content.encode("utf-8")
        if len(data) > self.MAX_BYTES:
            raise HostActionError("E_INVAL", f"content exceeds {self.MAX_BYTES} bytes")
        p = self._safe_path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Parent may have been created inside the allowlist; it cannot be a symlink.
        if p.parent.is_symlink():
            raise HostActionError("E_PERM", "parent may not be a symlink")
        fd, tmp = tempfile.mkstemp(prefix=".cbap-", dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, p)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        return {"path": str(p), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def _stat(self, args: dict) -> dict:
        p = self._safe_path(args.get("path"))
        if not p.exists():
            raise HostActionError("E_NOENT", "file does not exist")
        if not p.is_file() or p.is_symlink():
            raise HostActionError("E_INVAL", "not a regular file")
        data = p.read_bytes()
        return {
            "path": str(p), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "mode": oct(p.stat().st_mode & 0o777),
        }

    def _list(self, args: dict) -> dict:
        p = self._safe_path(args.get("path", "."))
        if not p.is_dir() or p.is_symlink():
            raise HostActionError("E_INVAL", "not a regular directory")
        entries = []
        for child in sorted(p.iterdir(), key=lambda x: x.name):
            if child.is_symlink():
                continue
            entries.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "bytes": child.stat().st_size if child.is_file() else None,
            })
        return {"path": str(p), "entries": entries[:200]}

    # ── callbacks ─────────────────────────────────────────────

    def _touch(self, extra: dict) -> None:
        self._last_state_at = time.time()
        self._last_state = {
            "type": "state", "device_id": self.DEVICE_ID,
            "body": {"root": str(self.root), **extra},
            "legacy_seq": int(self._last_state_at * 1000),
        }
        if self.on_state:
            try:
                self.on_state(dict(self._last_state))
            except Exception:
                pass

    def _emit(self, cmd: str, ok: bool, why: str | None, extra: dict) -> None:
        if self.on_result:
            try:
                payload = dict(extra or {})
                payload.setdefault("root", str(self.root))
                # The filesystem stat/hash is the host-side evidence; this is
                # not an independent external sensor.
                payload["independent"] = False
                self.on_result(cmd, ok, why, payload)
            except Exception:
                pass
