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
import hashlib
import hmac
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from drivers.mcp_client import MCPError, MCPStdioClient
from drivers.mcp_device.sandbox import SandboxUnavailable, wrap_command
from kernel.legacy_runtime.secrets import SecretError, get_secret


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


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _manifest_payload(manifest: dict) -> dict:
    return {k: v for k, v in manifest.items()
            if k not in {"_manifest_path", "signature"}}


class MCPDeviceDriver:
    """A CBAP-D driver wrapping a generic MCP hardware server."""

    def __init__(self, manifest_path: str | os.PathLike,
                 connect_timeout: float = 30.0):
        self.manifest = _read_manifest(manifest_path)
        self._verify_manifest_signature()
        self.manifest_path = self.manifest["_manifest_path"]
        self.device_id = str(self.manifest["device_id"])
        self.display_name = str(self.manifest.get("display_name") or self.device_id)
        self.poll_interval = max(0.05, float(self.manifest.get("poll_interval", 0.2)))
        self.facts_timeout = max(
            0.0, float(self.manifest.get("facts_timeout_ms", 2000)) / 1000.0)
        self.connect_timeout = float(connect_timeout)

        transport = self.manifest["transport"]
        base = Path(self.manifest_path).parent
        cwd = transport.get("cwd")
        cwd = str((base / cwd).resolve()) if cwd else str(base)
        env = dict(transport.get("env") or {})
        run_as_uid = transport.get("run_as_uid")
        run_as_gid = transport.get("run_as_gid")
        if (run_as_uid is not None or run_as_gid is not None) and os.geteuid() != 0:
            raise MCPDeviceError("E_SAFETY", "run_as_uid/run_as_gid requires root")
        try:
            command = wrap_command([str(x) for x in transport["command"]],
                                   transport.get("sandbox"), cwd)
        except SandboxUnavailable as e:
            raise MCPDeviceError("E_SAFETY", str(e))
        self.client = MCPStdioClient(
            command,
            cwd=cwd, env=env, timeout=self.connect_timeout,
            inherit_env=bool(transport.get("inherit_env", False)),
            env_allowlist=transport.get("env_allowlist"),
            rlimits=transport.get("rlimits"),
            run_as_uid=run_as_uid,
            run_as_gid=run_as_gid,
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
        self._tool_digest: str | None = None
        self._instructions_digest: str | None = None
        self._estop_verified: bool | None = None
        self._lock = threading.RLock()
        # Kernel-compatible callback hooks.  The Kernel replaces these on
        # startup just like it does for McDriver.
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_disconnect = None

    def _load_or_create_pin(self) -> dict:
        path = self.manifest_path + ".pins.json"
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise MCPDeviceError("E_SAFETY", "invalid pin file")
            return data
        except FileNotFoundError:
            pass
        except OSError as e:
            raise MCPDeviceError("E_SAFETY", f"cannot read pin file: {e}")
        data = {
            "tools_sha256": self._tool_digest,
            "instructions_sha256": self._instructions_digest,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o600)
            try:
                os.write(fd, _canonical(data).encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as e:
            raise MCPDeviceError("E_SAFETY", f"cannot write pin file: {e}")
        return data

    def _verify_manifest_signature(self) -> None:
        sig = self.manifest.get("signature")
        if not sig:
            if os.environ.get("CBAP_REQUIRE_SIGNED_MANIFEST") == "1":
                raise MCPDeviceError("E_AUTH", "unsigned manifest rejected")
            return
        try:
            key = get_secret("CBAP_MANIFEST_KEY")
        except SecretError as e:
            raise MCPDeviceError("E_AUTH", str(e))
        if not key:
            raise MCPDeviceError("E_AUTH", "manifest signature requires CBAP_MANIFEST_KEY")
        body = _canonical(_manifest_payload(self.manifest)).encode("utf-8")
        want = hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(sig), want):
            raise MCPDeviceError("E_AUTH", "manifest signature mismatch")

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
            tools = [
                {"name": t.get("name"), "description": t.get("description"),
                 "inputSchema": t.get("inputSchema"),
                 "annotations": t.get("annotations")}
                for t in (self.client.tools or []) if isinstance(t, dict)
            ]
            self._tool_digest = hashlib.sha256(
                _canonical(tools).encode("utf-8")).hexdigest()
            instr = (self.server_info or {}).get("instructions") or ""
            self._instructions_digest = hashlib.sha256(
                str(instr).encode("utf-8")).hexdigest()
            pin = self.manifest.get("pin_tools") or {}
            if not pin:
                pin = self._load_or_create_pin()
            if pin.get("tools_sha256") and not hmac.compare_digest(
                    str(pin["tools_sha256"]), self._tool_digest):
                self.client.close()
                raise MCPDeviceError("E_SAFETY", "tool definition digest mismatch")
            if pin.get("instructions_sha256") and not hmac.compare_digest(
                    str(pin["instructions_sha256"]), self._instructions_digest):
                self.client.close()
                raise MCPDeviceError("E_SAFETY", "server instructions digest mismatch")
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
        elif spec.get("source") == "command":
            cmd = spec.get("command")
            if not isinstance(cmd, list) or not cmd:
                raise MCPDeviceError("E_INVAL", "facts.command must be an argv list")
            base = Path(self.manifest_path).parent
            cwd = spec.get("cwd")
            cwd = str((base / cwd).resolve()) if cwd else str(base)
            allow = spec.get("env_allowlist") or ["PATH", "HOME", "LANG", "TMPDIR"]
            env = {k: os.environ[k] for k in allow if k in os.environ}
            env.update({str(k): str(v) for k, v in (spec.get("env") or {}).items()})
            proc = subprocess.run(
                [str(x) for x in cmd], cwd=cwd, env=env,
                capture_output=True, text=True, timeout=self.connect_timeout,
                shell=False, check=False,
            )
            if proc.returncode != 0:
                raise MCPDeviceError("E_IO", f"facts command failed: {proc.stderr[-300:]}")
            if len(proc.stdout) > 1024 * 1024:
                raise MCPDeviceError("E_IO", "facts command output too large")
            value = self._parse_tool_result(proc.stdout.strip())
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

    def _match(self, actual: Any, expected: Any,
               tolerance: float | None = None) -> bool:
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            return all(k in actual and self._match(actual[k], v, tolerance)
                       for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(
                self._match(a, b, tolerance) for a, b in zip(actual, expected))
        if (tolerance is not None and isinstance(actual, (int, float))
                and isinstance(expected, (int, float))
                and not isinstance(actual, bool)
                and not isinstance(expected, bool)):
            return abs(float(actual) - float(expected)) <= float(tolerance)
        return actual == expected

    def verify(self, expected: Any = None,
               tolerance: float | None = None) -> dict:
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
            independent = bool(self.facts_spec.get("independent", False))
            if expected is None:
                return {"ok": True, "status": "observed", "actual": actual,
                        "independent": independent}
            # Device facts can lag the tool result (Minecraft server ticks,
            # MQTT broker round trips, ...).  Poll until the fact settles or
            # the declared window expires.  A one-shot read here would create
            # a false mismatch.
            deadline = time.monotonic() + self.facts_timeout
            last = actual
            while True:
                matched = self._match(last, expected, tolerance)
                if matched:
                    return {"ok": True, "status": "verified",
                            "expected": expected, "actual": last,
                            "independent": independent}
                if time.monotonic() >= deadline:
                    return {"ok": False, "status": "mismatch",
                            "expected": expected, "actual": last}
                time.sleep(min(self.poll_interval, 0.1))
                try:
                    last = self.refresh()
                except Exception as e:
                    last = None
                    if time.monotonic() >= deadline:
                        return {"ok": False, "status": "error",
                                "expected": expected, "actual": None,
                                "error": str(e)}

    def _emit_result(self, cmd: str, ok: bool, why: str | None,
                     extra: dict | None = None) -> None:
        if self.on_result:
            try:
                self.on_result(cmd, bool(ok), why,
                               dict(extra or {}))
            except Exception:
                pass

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
                    verification = self.verify(expect, command.get("tolerance"))
                    self._last_verification = verification
                    self._emit_result(
                        op, bool(verification["ok"]),
                        None if verification["ok"] else "fact mismatch",
                        verification,
                    )
                    return bool(verification["ok"])
                self._last_verification = {
                    "ok": True, "status": "observed", "actual": actual,
                }
                self._emit_result(op, True, None, {"facts": actual})
                return True
            except Exception as e:
                self._last_error = str(e)
                self._last_verification = {
                    "ok": False, "status": "error", "actual": self.latest_state,
                    "error": str(e),
                }
                self._emit_result(op, False, f"MCP tool failed: {e}")
                return False

    def estop(self) -> bool:
        with self._lock:
            if not self.connected:
                return False
            if not self.estop_spec:
                self._last_error = "E_SAFETY: no estop tool declared"
                return False
            try:
                hw = self.estop_spec.get("hardware_command")
                if hw:
                    if not isinstance(hw, list) or not hw:
                        raise MCPDeviceError("E_SAFETY", "hardware_command must be argv")
                    proc = subprocess.run(
                        [str(x) for x in hw], cwd=os.path.dirname(self.manifest_path),
                        env={k: os.environ[k] for k in ("PATH", "HOME", "LANG")
                             if k in os.environ},
                        capture_output=True, text=True, timeout=5,
                        shell=False, check=False,
                    )
                    if proc.returncode != 0:
                        raise MCPDeviceError("E_SAFETY", "hardware estop failed")
                self._call_spec(self.estop_spec)
                actual = self.refresh()
                expect = (self.estop_spec.get("expect")
                          or self.estop_spec.get("verify"))
                if expect is not None:
                    v = self.verify(expect, self.estop_spec.get("tolerance"))
                    self._estop_verified = bool(v.get("ok"))
                    if not v.get("ok"):
                        self._last_error = "estop safe-state mismatch"
                        return False
                else:
                    self._estop_verified = None
                self._last_error = None
                return True
            except Exception as e:
                self._estop_verified = False
                self._last_error = str(e)
                return False

    def map_action(self, frame: dict) -> dict:
        """Convert a Kernel CBAP frame into this driver's command shape."""
        frame = dict(frame or {})
        channel = frame.get("channel")
        op = frame.get("op")
        args = frame.get("args") or {}
        command = {"cmd": op, "op": op, "args": args}
        if "expect" in frame:
            command["expect"] = frame["expect"]
        return command

    # ── Kernel interface ─────────────────────────────────────

    def describe(self) -> dict:
        transport = self.manifest.get("transport") or {}
        limits = self.manifest.get("limits") or {}
        actions = {
            str(name): {
                "args": copy.deepcopy(spec.get("args") or {}),
                "result": {},
                "danger": "high" if bool(spec.get("danger")) else "normal",
                "idempotent": bool(spec.get("idempotent", False)),
            }
            for name, spec in self.tools.items()
            if isinstance(spec, dict)
        }
        estop_verified = bool(self.estop_spec and
                              (self.estop_spec.get("expect") or
                               self.estop_spec.get("verify")))
        return {
            "device_id": self.device_id,
            "type": "mcp-device",
            "name": self.display_name,
            "transport": "stdio",
            "tools": sorted(self.tools),
            "facts": bool(self.facts_spec),
            "facts_independent": bool(self.facts_spec.get("independent", False)),
            "tool_digest": self._tool_digest,
            "instructions_digest": self._instructions_digest,
            "estop": bool(self.estop_spec),
            "contract": "cbap-device-v1",
            "class": "actuator",
            "version": "1.0",
            "legacy": False,
            "actions": actions,
            "capabilities": (["read", "write", "lease"] +
                             (["estop"] if estop_verified else [])),
            "trust": {
                "source": str(self.facts_spec.get("source") or "mcp-tool"),
                "independent": bool(self.facts_spec.get("independent", False)),
                "attestation": "none",
                "level": 2 if self.facts_spec.get("independent") else 1,
            },
            "isolation": {
                "process": "mcp-child",
                "uid": int(transport.get("run_as_uid") or os.getuid()),
                "sandbox": str(transport.get("sandbox") or "none"),
                "network": "stdio",
            },
            "resources": {
                "max_inflight": int(limits.get("max_inflight") or 4),
                "rate_hz": int(limits.get("rate_hz") or 20),
                "max_bytes": int(limits.get("max_bytes") or 65536),
                "max_sessions": int(limits.get("max_sessions") or 4),
            },
            "safety": {
                "estop": estop_verified,
                "watchdog_ms": int(self.manifest.get("watchdog_ms", 10000)),
                "safe_state": ("off" if estop_verified else "unknown"),
            },
        }

    def health(self) -> dict:
        return {
            "ok": bool(self.connected),
            "device_id": self.device_id,
            "state_age_ms": self.state_age_ms(),
            "last_error": self._last_error,
            "server": self.server_info,
            "advertised_tools": sorted(self.advertised_tools),
            "tool_digest": self._tool_digest,
            "instructions_digest": self._instructions_digest,
            "estop_verified": self._estop_verified,
        }

    def last_verification(self) -> dict | None:
        return copy.deepcopy(self._last_verification)
