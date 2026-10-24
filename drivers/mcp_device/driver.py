#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic MCP device driver for CBAP.

This is the device-side counterpart to the MCP agent driver.  A manifest
describes one physical/logical device, its transport, the MCP tools that are
allowed, and the independent fact source used to verify an action.

The driver deliberately does not trust a tool's ``ok`` field.  A command is
only reported as verified when the declared fact source can be read back and
matches the optional ``expect`` predicate.

Manifest example::

    {
      "device_id": "mcp://lab/light-01",
      "display_name": "Lab light",
      "transport": {
        "type": "stdio",
        "command": ["python3", "light_mcp.py"],
        "cwd": "."
      },
      "tools": {
        "turn_on":  {"tool": "turn_on",  "args": {}},
        "turn_off": {"tool": "turn_off", "args": {}}
      },
      "facts": {
        "source": "tool",
        "tool": "get_state"
      },
      "estop": {"tool": "turn_off"},
      "poll_interval": 0.2
    }

Only stdio MCP is supported in v0.  HTTP/SSE can be added behind the same
driver contract without changing the Kernel.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from drivers.mcp_client import MCPError, MCPStdioClient


class MCPDeviceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _read_manifest(path: str | os.PathLike) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest is not an object: {p}")
    if not manifest.get("device_id"):
        raise ValueError(f"manifest missing device_id: {p}")
    transport = manifest.get("transport") or {}
    if transport.get("type") != "stdio":
        raise ValueError(f"only stdio transport is supported in v0: {p}")
    if not transport.get("command"):
        raise ValueError(f"manifest missing transport.command: {p}")
    if not manifest.get("tools"):
        raise ValueError(f"manifest missing tools: {p}")
    manifest["_manifest_path"] = str(p.resolve())
    return manifest


class MCPDeviceDriver:
    """A CBAP-D driver wrapping a generic MCP hardware server."""

    def __init__(self, manifest_path: str | os.PathLike,
                 connect_timeout: float = 30.0):
        self.manifest = _read_manifest(manifest_path)
        self.manifest_path = self.manifest["_manifest_path"]
        self.device_id = str(self.manifest["device_id"])
        self.display_name = str(self.manifest.get("display_name") or self.device_id)
        self.poll_interval = max(0.05, float(self.manifest.get("poll_interval", 0.2)))
        self.connect_timeout = float(connect_timeout)

        transport = self.manifest["transport"]
        base = Path(self.manifest_path).parent
        cwd = transport.get("cwd")
        cwd = str((base / cwd).resolve()) if cwd else str(base)
        env = dict(transport.get("env") or {})
        self.client = MCPStdioClient(
            [str(x) for x in transport["command"]],
            cwd=cwd, env=env, timeout=self.connect_timeout,
        )
        self.tools: dict[str, dict] = dict(self.manifest["tools"])
        self.facts_spec = dict(self.manifest.get("facts") or {})
        self.estop_spec = dict(self.manifest.get("estop") or {})

        self.connected = False
        self.server_info: dict = {}
        self.advertised_tools: set[str] = set()
        self._state: dict | None = None
        self._state_at: float = 0.0
        self._last_tool_result: Any = None
        self._last_verification: dict | None = None
        self._last_error: str | None = None
        self._lock = threading.RLock()
        # Kernel-compatible callback hook.
        self.on_state = None

    # ── lifecycle ─────────────────────────────────────────────

    def connect(self) -> bool:
        with self._lock:
            self.server_info = self.client.start()
            self.advertised_tools = {
                str(t.get("name")) for t in (self.client.tools or [])
                if isinstance(t, dict)
            }
            missing = sorted({
                str(spec.get("tool"))
                for spec in self.tools.values()
                if isinstance(spec, dict) and spec.get("tool")
                and str(spec["tool"]) not in self.advertised_tools
            })
            if missing:
                self.client.close()
                raise MCPDeviceError(
                    "E_NOTSUP",
                    f"{self.device_id}: advertised server is missing tools: {missing}",
                )
            self.connected = True
            self._last_error = None
            self.refresh()
            return True

    def close(self) -> None:
        with self._lock:
            self.connected = False
            self.client.close()

    # ── facts ─────────────────────────────────────────────────

    def _extract_path(self, value: Any, path: str | None) -> Any:
        if not path:
            return value
        current = value
        for part in str(path).split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                raise KeyError(f"path {path!r} not found")
        return current

    def _parse_tool_result(self, result: Any) -> Any:
        if isinstance(result, str):
            try:
                return json.loads(result)
            except Exception:
                return result
        return result

    def _read_facts(self) -> Any:
        spec = self.facts_spec
        if not spec:
            return None
        if spec.get("source") == "resource":
            result = self.client.request("resources/read", {
                "uri": str(spec.get("uri") or ""),
            }, timeout=self.connect_timeout)
            contents = (result or {}).get("contents") or []
            if not contents:
                return None
            text = contents[0].get("text") if isinstance(contents[0], dict) else None
            value = self._parse_tool_result(text)
        else:
            tool = spec.get("tool")
            if not tool:
                return None
            value = self.client.call_tool(
                str(tool), dict(spec.get("args") or {}),
                timeout=self.connect_timeout,
            )
            value = self._parse_tool_result(value)
        return self._extract_path(value, spec.get("path"))

    def refresh(self) -> dict | None:
        with self._lock:
            if not self.connected:
                return self._state
            try:
                value = self._read_facts()
                self._state = value if isinstance(value, dict) else {"value": value}
                self._state_at = time.monotonic()
                if self.on_state:
                    try:
                        self.on_state(copy.deepcopy(self._state))
                    except Exception:
                        pass
            except Exception as e:
                self._last_error = str(e)
                raise
            return self._state

    @property
    def latest_state(self) -> dict | None:
        return copy.deepcopy(self._state)

    def state_age_ms(self) -> int | None:
        if self._state is None:
            return None
        return int((time.monotonic() - self._state_at) * 1000)

    def wait_state(self, timeout_s: float) -> dict | None:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while time.monotonic() <= deadline:
            if self._state is not None:
                return self.latest_state
            time.sleep(min(self.poll_interval, 0.05))
        return self.latest_state

    # ── action ────────────────────────────────────────────────

    def _match(self, actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            return all(k in actual and self._match(actual[k], v)
                       for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(
                self._match(a, b) for a, b in zip(actual, expected))
        return actual == expected

    def verify(self, expected: Any = None) -> dict:
        """Read the independent fact source and compare it to an expectation.

        A missing fact source is ``unverifiable``; it is never treated as
        success.  This is the core distinction between a tool receipt and a
        CBAP completion fact.
        """
        with self._lock:
            if not self.connected:
                return {"ok": False, "status": "offline",
                        "actual": self.latest_state, "error": "not connected"}
            if not self.facts_spec:
                return {"ok": False, "status": "unverifiable",
                        "actual": None, "error": "no facts source declared"}
            try:
                actual = self.refresh()
            except Exception as e:
                return {"ok": False, "status": "error", "actual": None,
                        "error": str(e)}
            if expected is None:
                return {"ok": True, "status": "observed", "actual": actual}
            matched = self._match(actual, expected)
            return {"ok": matched, "status": "verified" if matched else "mismatch",
                    "expected": expected, "actual": actual}

    def _call_spec(self, spec: dict, extra_args: dict | None = None) -> Any:
        tool = spec.get("tool")
        if not tool:
            raise MCPDeviceError("E_INVAL", "tool spec has no tool name")
        args = dict(spec.get("args") or {})
        args.update(extra_args or {})
        return self.client.call_tool(str(tool), args, timeout=self.connect_timeout)

    def send(self, command: dict) -> bool:
        """Execute one CBAP command.

        Accepted shapes::

          {"op": "turn_on", "args": {}}
          {"channel": "mcp", "op": "turn_on", "args": {}}
          {"op": "turn_on", "args": {}, "expect": {"on": true}}
        """
        with self._lock:
            if not self.connected:
                self._last_error = "not connected"
                return False
            op = str(command.get("op") or command.get("action") or "")
            if op in {"read", "state", "facts"}:
                try:
                    self.refresh()
                    return True
                except Exception as e:
                    self._last_error = str(e)
                    return False
            spec = self.tools.get(op)
            if not isinstance(spec, dict):
                self._last_error = f"E_NOTSUP: unknown device op {op!r}"
                return False
            try:
                result = self._call_spec(spec, command.get("args") or {})
                self._last_tool_result = result
                self._last_error = None
                # Re-read facts after every action.  The tool result alone is
                # never treated as completion.
                actual = self.refresh()
                expect = command.get("expect")
                if expect is not None:
                    verification = self.verify(expect)
                    self._last_verification = verification
                    return bool(verification["ok"])
                self._last_verification = {
                    "ok": True, "status": "observed", "actual": actual,
                }
                return True
            except Exception as e:
                self._last_error = str(e)
                self._last_verification = {
                    "ok": False, "status": "error", "actual": self.latest_state,
                    "error": str(e),
                }
                return False

    def estop(self) -> bool:
        with self._lock:
            if not self.connected:
                return False
            if not self.estop_spec:
                self._last_error = "E_SAFETY: no estop tool declared"
                return False
            try:
                self._call_spec(self.estop_spec)
                self.refresh()
                self._last_error = None
                return True
            except Exception as e:
                self._last_error = str(e)
                return False

    def map_action(self, frame: dict) -> dict:
        """Convert a Kernel CBAP frame into this driver's command shape."""
        frame = dict(frame or {})
        channel = frame.get("channel")
        op = frame.get("op")
        args = frame.get("args") or {}
        if channel == "mcp":
            return {"op": op, "args": args,
                    **({"expect": frame["expect"]} if "expect" in frame else {})}
        # A bare generic op is also accepted for device-to-device tests.
        return {"op": op, "args": args,
                **({"expect": frame["expect"]} if "expect" in frame else {})}

    # ── Kernel interface ─────────────────────────────────────

    def describe(self) -> dict:
        return {
            "device_id": self.device_id,
            "type": "mcp-device",
            "name": self.display_name,
            "transport": "stdio",
            "tools": sorted(self.tools),
            "facts": bool(self.facts_spec),
            "estop": bool(self.estop_spec),
        }

    def health(self) -> dict:
        return {
            "ok": bool(self.connected),
            "device_id": self.device_id,
            "state_age_ms": self.state_age_ms(),
            "last_error": self._last_error,
            "server": self.server_info,
            "advertised_tools": sorted(self.advertised_tools),
        }

    def last_verification(self) -> dict | None:
        return copy.deepcopy(self._last_verification)
