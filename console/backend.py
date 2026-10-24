#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local CBAP operator backend.

The console is deliberately a separate host: it talks to the Kernel over the
CBAP Unix socket and never opens a driver directly.  It has two operations:
read status, and request estop.  There is intentionally no resume endpoint.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.client import CBAPError


class ConsoleError(RuntimeError):
    pass


class ConsoleBackend:
    def __init__(self, socket_path: str, audit_path: str | None = None,
                 token: str | None = None, agent_id: str = "cbap-console"):
        self.socket_path = os.path.abspath(socket_path)
        self.audit_path = os.path.abspath(audit_path) if audit_path else None
        self.token = token
        self.agent_id = agent_id
        self._lock = threading.RLock()
        self._client: CBAPClient | None = None
        self._fds: dict[str, str] = {}
        self._last_error: str | None = None

    # ── connection ───────────────────────────────────────────
    def _connect_locked(self) -> None:
        if self._client and self._client.connected:
            return
        self._fds.clear()
        c = CBAPClient(self.socket_path, agent_id=self.agent_id)
        c.connect()
        c.hello(token=self.token)
        self._client = c
        self._last_error = None

    def close(self) -> None:
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None
            self._fds.clear()

    def _ensure_fds_locked(self, devices: list[dict]) -> None:
        wanted = {str(d.get("device_id")) for d in devices}
        for dev_id in list(self._fds):
            if dev_id not in wanted:
                fd = self._fds.pop(dev_id, None)
                if fd and self._client:
                    try:
                        self._client.call("close", {"fd": fd})
                    except Exception:
                        pass
        for d in devices:
            dev_id = str(d.get("device_id") or "")
            if not dev_id or dev_id in self._fds:
                continue
            try:
                opened = self._client.open(dev_id, mode="r")
                if opened.get("ok"):
                    self._fds[dev_id] = opened["payload"]["fd"]
            except Exception as e:
                self._last_error = f"{dev_id}: {e}"

    # ── status ───────────────────────────────────────────────
    def _facts(self, frame: dict) -> Any:
        if not isinstance(frame, dict):
            return None
        # Prefer the generic state channel; fall back to a compact body view.
        if isinstance(frame.get("state"), dict):
            return frame["state"]
        if "body" in frame:
            return {"body": frame.get("body"),
                    "inventory": frame.get("inventory"),
                    "world": frame.get("world")}
        return frame

    def refresh(self) -> dict:
        with self._lock:
            try:
                self._connect_locked()
                listing = self._client.device_list()
                if not listing.get("ok"):
                    raise ConsoleError(str(listing.get("error") or "device_list failed"))
                devices = listing.get("payload", {}).get("devices") or []
                self._ensure_fds_locked(devices)
                out = []
                for d in devices:
                    dev_id = str(d.get("device_id") or "")
                    fd = self._fds.get(dev_id)
                    item = {
                        "device_id": dev_id,
                        "type": d.get("type"),
                        "online": d.get("state") == "ready",
                        "fd": fd,
                        "facts": None,
                        "facts_error": None,
                        "safe": None,
                        "lease": None,
                        "pending": None,
                        "health": None,
                    }
                    if fd:
                        try:
                            st = self._client.stat(fd)
                            if st.get("ok"):
                                p = st.get("payload") or {}
                                item.update({
                                    "safe": p.get("safe"),
                                    "lease": p.get("lease"),
                                    "pending": p.get("pending"),
                                    "health": p.get("health"),
                                })
                            else:
                                item["facts_error"] = str(st.get("error") or "stat failed")
                        except Exception as e:
                            item["facts_error"] = str(e)
                        try:
                            rd = self._client.read(fd, timeout_ms=0)
                            if rd.get("ok"):
                                frame = (rd.get("payload") or {}).get("frame") or {}
                                item["facts"] = self._facts(frame)
                                item["channels"] = sorted(frame.keys())
                            else:
                                item["facts_error"] = str(rd.get("error") or item["facts_error"])
                        except CBAPError as e:
                            # E_AGAIN means "no state buffered yet", not a
                            # connection failure.
                            if e.code not in ("E_AGAIN", "E_TIMEOUT"):
                                item["facts_error"] = str(e)
                        except Exception as e:
                            item["facts_error"] = str(e)
                    out.append(item)
                return {
                    "ok": True,
                    "ts": time.time(),
                    "kernel": {"socket": self.socket_path, "connected": True},
                    "devices": out,
                }
            except Exception as e:
                self._last_error = str(e)
                return {
                    "ok": False,
                    "ts": time.time(),
                    "kernel": {"socket": self.socket_path, "connected": False},
                    "devices": [],
                    "error": str(e),
                }

    # ── estop ────────────────────────────────────────────────
    def estop(self, fd: str | None, reason: str = "console") -> dict:
        with self._lock:
            try:
                self._connect_locked()
                if fd and fd not in self._fds.values():
                    raise ConsoleError("unknown console fd")
                res = self._client.estop(fd, reason=reason)
                if not res.get("ok"):
                    raise ConsoleError(str(res.get("error") or "estop failed"))
                return {"ok": True, "result": res.get("payload") or {},
                        "status": self.refresh()}
            except Exception as e:
                self._last_error = str(e)
                return {"ok": False, "error": str(e)}

    # ── audit ────────────────────────────────────────────────
    def audit(self, limit: int = 80) -> dict:
        limit = max(1, min(int(limit), 500))
        if not self.audit_path:
            return {"ok": True, "rows": [], "path": None}
        p = Path(self.audit_path)
        if not p.exists():
            return {"ok": True, "rows": [], "path": str(p)}
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
            rows = []
            for line in lines:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
            return {"ok": True, "rows": rows, "path": str(p)}
        except OSError as e:
            return {"ok": False, "rows": [], "error": str(e)}
