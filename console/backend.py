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
import re
import threading
import time
from pathlib import Path
from typing import Any

from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.client import CBAPError
from drivers.mcp_client import MCPStdioClient
from drivers.mcp_device.driver import MCPDeviceDriver


class ConsoleError(RuntimeError):
    pass


class ConsoleBackend:
    def __init__(self, socket_path: str, audit_path: str | None = None,
                 token: str | None = None, agent_id: str = "cbap-console",
                 registry_dir: str | None = None):
        self.socket_path = os.path.abspath(socket_path)
        self.audit_path = os.path.abspath(audit_path) if audit_path else None
        self.token = token
        self.agent_id = agent_id
        self._lock = threading.RLock()
        self._client: CBAPClient | None = None
        self._fds: dict[str, str] = {}
        self._last_error: str | None = None
        self.registry_dir = Path(registry_dir or
                                 (Path(__file__).resolve().parent.parent /
                                  "devices" / "onboarded"))
        self._onboard_lock = threading.Lock()

    # ── connection ───────────────────────────────────────────
    def _connect_locked(self) -> None:
        if self._client and self._client.connected:
            return
        self._fds.clear()
        c = CBAPClient(self.socket_path, agent_id=self.agent_id)
        c.connect()
        op = None
        try:
            with open(self.socket_path + ".operator", encoding="ascii") as f:
                op = f.read().strip()
        except OSError:
            op = None
        c.hello(token=self.token, operator_token=op)
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

    # ── approvals / lease ────────────────────────────────────
    def approvals(self) -> dict:
        with self._lock:
            try:
                self._connect_locked()
                res = self._client.call("approval_list", {})
                if not res.get("ok"):
                    raise ConsoleError(str(res.get("error") or "approval_list failed"))
                return {"ok": True,
                        "approvals": (res.get("payload") or {}).get("approvals") or []}
            except Exception as e:
                self._last_error = str(e)
                return {"ok": False, "approvals": [], "error": str(e)}

    def approve(self, approval_id: str) -> dict:
        with self._lock:
            try:
                self._connect_locked()
                res = self._client.call("approval_approve",
                                        {"approval_id": approval_id})
                if not res.get("ok"):
                    raise ConsoleError(str(res.get("error") or "approval failed"))
                return {"ok": True, "result": res.get("payload") or {},
                        "approvals": self.approvals().get("approvals") or []}
            except Exception as e:
                self._last_error = str(e)
                return {"ok": False, "error": str(e)}

    def deny(self, approval_id: str) -> dict:
        with self._lock:
            try:
                self._connect_locked()
                res = self._client.call("approval_deny",
                                        {"approval_id": approval_id})
                if not res.get("ok"):
                    raise ConsoleError(str(res.get("error") or "deny failed"))
                return {"ok": True, "result": res.get("payload") or {},
                        "approvals": self.approvals().get("approvals") or []}
            except Exception as e:
                self._last_error = str(e)
                return {"ok": False, "error": str(e)}

    def release_lease(self, device_id: str) -> dict:
        with self._lock:
            try:
                self._connect_locked()
                res = self._client.call("admin_release",
                                        {"device_id": device_id})
                if not res.get("ok"):
                    raise ConsoleError(str(res.get("error") or "release failed"))
                return {"ok": True, "result": res.get("payload") or {},
                        "status": self.refresh()}
            except Exception as e:
                self._last_error = str(e)
                return {"ok": False, "error": str(e)}

    # ── MCP onboarding ───────────────────────────────────────
    @staticmethod
    def _safe_name(text: str) -> str:
        name = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(text)).strip("._")
        if not name or ".." in name or len(name) > 128:
            raise ConsoleError("invalid device_id")
        return name

    @staticmethod
    def _command(value: Any) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ConsoleError("command must be a non-empty JSON array")
        if len(value) > 32:
            raise ConsoleError("command too long")
        out = []
        for x in value:
            if not isinstance(x, str) or not x or len(x) > 2048:
                raise ConsoleError("command arguments must be strings")
            out.append(x)
        return out

    def _registry_path(self, name: str) -> Path:
        safe = self._safe_name(name)
        self.registry_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self.registry_dir / f"{safe}.json"

    def onboard_scan(self, body: dict) -> dict:
        if not self._onboard_lock.acquire(timeout=15):
            return {"ok": False, "error": "another onboarding scan is running"}
        client = None
        try:
            command = self._command(body.get("command"))
            cwd = body.get("cwd")
            if cwd is not None and (not isinstance(cwd, str) or not cwd):
                raise ConsoleError("cwd must be a path")
            timeout = max(1.0, min(float(body.get("timeout") or 10), 20.0))
            client = MCPStdioClient(
                command, cwd=cwd, inherit_env=False,
                env_allowlist=["PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE",
                               "TMPDIR"],
                timeout=timeout,
            )
            info = client.start()
            tools = []
            for t in client.tools:
                if not isinstance(t, dict) or not t.get("name"):
                    continue
                tools.append({
                    "name": str(t.get("name")),
                    "description": str(t.get("description") or "")[:1000],
                    "inputSchema": t.get("inputSchema") or t.get("input_schema") or {},
                })
            return {"ok": True, "server": info, "tools": tools,
                    "command": command, "cwd": cwd}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            self._onboard_lock.release()

    def onboard_list(self) -> dict:
        try:
            self.registry_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            rows = []
            for p in sorted(self.registry_dir.glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                rows.append({
                    "name": p.stem,
                    "device_id": data.get("device_id"),
                    "display_name": data.get("display_name"),
                    "path": str(p),
                    "mtime": int(p.stat().st_mtime * 1000),
                    "signed": bool(data.get("signature")),
                    "pinned": bool((data.get("pin_tools") or {}).get("tools_sha256")) or
                              p.with_suffix(p.suffix + ".pins.json").exists(),
                    "tools": len(data.get("tools") or {}),
                    "facts_source": (data.get("facts") or {}).get("source"),
                    "estop": bool((data.get("estop") or {}).get("expect") or
                                  (data.get("estop") or {}).get("verify")),
                })
            return {"ok": True, "devices": rows, "registry": str(self.registry_dir)}
        except Exception as e:
            return {"ok": False, "error": str(e), "devices": []}

    def onboard_create(self, body: dict) -> dict:
        try:
            device_id = str(body.get("device_id") or "")
            name = self._safe_name(device_id)
            command = self._command(body.get("command"))
            selected = body.get("tools")
            if not isinstance(selected, list) or not selected:
                raise ConsoleError("select at least one tool")
            tools: dict[str, dict] = {}
            for item in selected[:128]:
                if not isinstance(item, dict):
                    raise ConsoleError("tools entries must be objects")
                op = str(item.get("cbap_op") or item.get("op") or "")
                tool = str(item.get("tool") or "")
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", op):
                    raise ConsoleError(f"invalid cbap op: {op}")
                if not tool:
                    raise ConsoleError(f"tool required for {op}")
                args = item.get("args") or {}
                if not isinstance(args, dict):
                    raise ConsoleError("tool args must be an object")
                tools[op] = {"tool": tool, "args": args}
            facts = body.get("facts") or {}
            if facts and not isinstance(facts, dict):
                raise ConsoleError("facts must be an object")
            facts = dict(facts)
            if facts:
                facts.setdefault("source", "tool")
                if facts.get("source") not in ("tool", "resource", "command"):
                    raise ConsoleError("facts.source must be tool/resource/command")
                facts.setdefault("independent", False)
            estop = body.get("estop") or {}
            if estop:
                if not isinstance(estop, dict):
                    raise ConsoleError("estop must be an object")
                if not estop.get("tool"):
                    raise ConsoleError("estop.tool required")
                if not isinstance(estop.get("expect"), dict) or not estop.get("expect"):
                    raise ConsoleError("estop.expect required for safe onboarding")
            cwd = body.get("cwd")
            if cwd is not None and (not isinstance(cwd, str) or not cwd):
                raise ConsoleError("cwd must be a path")
            manifest = {
                "device_id": device_id,
                "display_name": str(body.get("display_name") or device_id),
                "transport": {
                    "type": "stdio", "command": command,
                    "inherit_env": False,
                    "env_allowlist": ["PATH", "HOME", "LANG", "LC_ALL",
                                      "LC_CTYPE", "TMPDIR"],
                },
                "tools": tools,
                "facts": facts,
                "estop": estop,
                "watchdog_ms": int(body.get("watchdog_ms") or 10000),
                "poll_interval": float(body.get("poll_interval") or 0.2),
                "facts_timeout_ms": int(body.get("facts_timeout_ms") or 2000),
            }
            if cwd:
                manifest["transport"]["cwd"] = cwd
            path = self._registry_path(name)
            if path.exists() and not body.get("overwrite"):
                raise ConsoleError("device already exists; set overwrite=true")
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
            return {"ok": True, "path": str(path), "manifest": manifest}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def onboard_probe(self, body: dict) -> dict:
        if not self._onboard_lock.acquire(timeout=20):
            return {"ok": False, "error": "another onboarding operation is running"}
        driver = None
        try:
            name = str(body.get("name") or "")
            path = self._registry_path(name)
            if not path.exists():
                raise ConsoleError("device not found in onboarding registry")
            driver = MCPDeviceDriver(path, connect_timeout=10.0)
            driver.connect()
            result: dict[str, Any] = {
                "ok": True,
                "name": name,
                "device_id": driver.device_id,
                "health": driver.health(),
                "describe": driver.describe(),
                "facts": driver.facts_spec,
                "estop": driver.estop_spec,
                "tools": sorted(driver.advertised_tools),
            }
            if body.get("op"):
                cmd = {"op": str(body["op"]), "args": body.get("args") or {}}
                if isinstance(body.get("expect"), dict):
                    cmd["expect"] = body["expect"]
                if body.get("tolerance") is not None:
                    cmd["tolerance"] = body["tolerance"]
                result["tool_ok"] = driver.send(cmd)
                result["verification"] = driver.last_verification()
            else:
                result["verification"] = driver.last_verification()
            result["signed"] = bool(driver.manifest.get("signature"))
            result["pinned"] = bool(driver.manifest.get("pin_tools")) or                 Path(str(path) + ".pins.json").exists()
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            if driver:
                try:
                    driver.close()
                except Exception:
                    pass
            self._onboard_lock.release()

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
