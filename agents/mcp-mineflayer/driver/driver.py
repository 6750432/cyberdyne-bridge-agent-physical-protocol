#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP-D driver for a real MCP Minecraft agent.

This driver launches an external MCP server over stdio (public MCP JSON-RPC
only) and exposes it as a CBAP device. It does not import, patch, or read the
server's internals.

First target: swaynos/mineflayer-mcp (9 tools / 6 resources), because its
surface maps cleanly onto CBAP body/world/inventory/chat channels.
"""

from __future__ import annotations

import copy
import json
import os
import queue
import shutil
import threading
import time
from typing import Any

from drivers.mc.driver import ActionError
from drivers.mcp_client import MCPError, MCPStdioClient

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SERVER_PATH = os.environ.get("CBAP_MCP_SERVER", "")
DEFAULT_NODE = os.environ.get("CBAP_NODE_BIN") or shutil.which("node") or "node"


class MCPDriver:
    def __init__(self, server_path: str | None = None,
                 host: str = "127.0.0.1", port: int = 25565,
                 username: str = "MCPBody", version: str | None = "1.21.1",
                 node_bin: str | None = None,
                 lock_path: str | None = None,
                 command: list[str] | None = None,
                 cwd: str | None = None,
                 device_path: str | None = None,
                 mapping_path: str | None = None,
                 device_id: str | None = None,
                 poll_interval: float = 0.5,
                 connect_timeout: float = 40.0,
                 auto_restart: bool = True,
                 restart_delay: float = 1.0):
        self.server_path = os.path.abspath(
            server_path or DEFAULT_SERVER_PATH or ".")
        self.host = host
        self.port = int(port)
        self.username = username
        self.version = version
        self.node_bin = node_bin or DEFAULT_NODE
        self.lock_path = lock_path or f"/tmp/cbap-mcp-{username}.lock"
        with open(device_path or os.path.join(HERE, "device.json"),
                  encoding="utf-8") as f:
            self.device = json.load(f)
        with open(mapping_path or os.path.join(HERE, "mapping.json"),
                  encoding="utf-8") as f:
            self.mapping = json.load(f)
        if device_id:
            self.device["device_id"] = str(device_id)
            self.mapping["device_id"] = str(device_id)
        self.cwd = cwd or self.server_path
        self.command = command or [
            self.node_bin, "src/index.js",
            "--host", self.host, "--port", str(self.port),
            "--username", self.username,
            "--lock", self.lock_path,
            "--version", self.version or "1.21.1",
            "--log-level", "warn",
        ]
        self.poll_interval = max(0.2, float(poll_interval))
        self.connect_timeout = float(connect_timeout)
        self.auto_restart = bool(auto_restart)
        self.restart_delay = max(0.2, float(restart_delay))

        self.client: MCPStdioClient | None = None
        self.connected = False
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_connect = None
        self.on_disconnect = None

        self._latest_state: dict | None = None
        self._state_cond = threading.Condition()
        self._state_seq = 0
        self._last_state_at = 0.0
        self._stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._actions: queue.Queue = queue.Queue()
        self._action_busy = threading.Event()
        self._restart_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._stats_lock = threading.Lock()
        self.stats = {
            "tool_calls": 0,
            "last_tool": None,
            "last_result": None,
            "last_error": None,
            "state_seq": 0,
            "started_at": None,
            "server_path": self.server_path,
            "username": self.username,
            "position": None,
            "health": None,
            "food": None,
            "tool_history": [],
            "restarts": 0,
        }

    def describe(self) -> dict:
        return copy.deepcopy(self.device)

    def _set_stats(self, **kw) -> None:
        with self._stats_lock:
            self.stats.update(kw)

    def _record_tool(self, name: str, args: dict, ok: bool,
                     result: Any = None, error: str | None = None) -> None:
        with self._stats_lock:
            self.stats["tool_calls"] += 1
            self.stats["last_tool"] = name
            self.stats["last_result"] = result if ok else None
            self.stats["last_error"] = error
            h = list(self.stats.get("tool_history") or [])
            h.append({"t": int(time.time() * 1000), "tool": name,
                      "args": args, "ok": ok,
                      "error": error,
                      "result": result if isinstance(result, (dict, list, str, int, float, bool, type(None))) else str(result)})
            self.stats["tool_history"] = h[-40:]

    # ── lifecycle ─────────────────────────────────────────────

    def _start_client(self) -> dict:
        if not os.path.isdir(self.cwd):
            raise ActionError("E_INVAL", f"MCP server cwd not found: {self.cwd}")
        c = MCPStdioClient(self.command, cwd=self.cwd,
                           timeout=self.connect_timeout)
        info = c.start()
        self.client = c
        self.connected = True
        self._set_stats(server_info=info,
                        connected_at=int(time.time() * 1000),
                        tool_surface=[t.get("name") for t in c.tools])
        return info

    def connect(self) -> None:
        if self.connected:
            return
        self._stop.clear()
        self._start_client()
        self._poll_thread = threading.Thread(target=self._poll_loop,
                                             name="mcp-poll", daemon=True)
        self._poll_thread.start()
        self._worker_thread = threading.Thread(target=self._worker_loop,
                                               name="mcp-actions", daemon=True)
        self._worker_thread.start()
        if self.on_connect:
            try:
                self.on_connect()
            except Exception:
                pass
        # Wait for the first real observation, but do not fail the whole
        # registration if the bot is still spawning.
        end = time.time() + min(15.0, self.connect_timeout)
        while time.time() < end:
            if self._latest_state is not None:
                break
            time.sleep(0.2)

    def close(self) -> None:
        self.connected = False
        self._stop.set()
        with self._state_cond:
            self._state_cond.notify_all()
        if self._worker_thread:
            try:
                self._actions.put(None)
            except Exception:
                pass
        c = self.client
        self.client = None
        if c:
            c.close()

    def estop(self) -> bool:
        # MCP Mineflayer server has no stop tool. The only safe, protocol-level
        # action is to terminate the external process and let the bot disconnect.
        if not self.connected and not self.client:
            return True
        self.connected = False
        self._stop.set()
        with self._state_cond:
            self._state_cond.notify_all()
        c = self.client
        self.client = None
        if c:
            c.close()
        if self.on_event:
            try:
                self.on_event({"type": "event", "kind": "estop",
                               "why": "MCP process terminated",
                               "device_id": self.device.get("device_id")})
            except Exception:
                pass
        return True

    def cancel(self) -> bool:
        """Best-effort cancel of the in-flight MCP tool.

        MCP has no cancel primitive. Terminate the external process; the poll
        loop will restart it when auto_restart is enabled.
        """
        q_keep = queue.Queue()
        while True:
            try:
                item = self._actions.get_nowait()
            except queue.Empty:
                break
            if item is None:
                continue
            # Drop queued actions; the canceled kernel request is already done.
        self._actions = q_keep
        self.connected = False
        c = self.client
        self.client = None
        if c:
            c.close()
        if self.on_event:
            try:
                self.on_event({"type": "event", "kind": "cancel",
                               "why": "MCP process terminated to cancel action",
                               "device_id": self.device.get("device_id")})
            except Exception:
                pass
        return True

    def health(self) -> dict:
        age = None
        if self._last_state_at:
            age = int((time.time() - self._last_state_at) * 1000)
        watchdog = int((self.device.get("safety") or {}).get("watchdog_ms") or 10000)
        ok = bool(self.connected and (age is None or age <= watchdog))
        return {
            "ok": ok,
            "connected": bool(self.connected),
            "state_age_ms": age,
            "device_id": self.device.get("device_id"),
            "backend": "mcp-stdio",
        }

    def wait_state(self, timeout_s: float) -> dict | None:
        end = time.time() + max(0.0, float(timeout_s))
        with self._state_cond:
            while self._latest_state is None and time.time() < end:
                self._state_cond.wait(timeout=max(0.0, end - time.time()))
            return copy.deepcopy(self._latest_state)

    # ── observation ───────────────────────────────────────────

    def _call(self, tool: str, args: dict | None = None,
              timeout: float = 60.0) -> Any:
        c = self.client
        if not c or not self.connected:
            raise MCPError("MCP driver is not connected")
        try:
            result = c.call_tool(tool, args or {}, timeout=timeout)
            self._record_tool(tool, args or {}, True, result)
            return result
        except MCPError as e:
            self._record_tool(tool, args or {}, False, error=str(e))
            raise

    def _refresh_state(self, full: bool = False) -> None:
        status = self._call("status", {}, timeout=15)
        if not isinstance(status, dict):
            return
        pos = status.get("position") or {}
        state: dict = {
            "type": "state",
            "pos": [pos.get("x"), pos.get("y"), pos.get("z")],
            "hp": status.get("health"),
            "food": status.get("food"),
            "saturation": status.get("saturation"),
            "dimension": pos.get("dimension"),
            "onGround": True,
            "acting": "busy" if self._action_busy.is_set() else "idle",
            "items": (self._latest_state or {}).get("items") or {},
            "blocks": (self._latest_state or {}).get("blocks") or [],
            "scan": (self._latest_state or {}).get("scan"),
            "chat": (self._latest_state or {}).get("chat") or [],
            "seq": 0,
            "t": int(time.time() * 1000),
        }
        if full:
            try:
                inv = self._call("inventory", {"action": "inspect"}, timeout=15)
                state["items"] = self._inventory_to_dict(inv)
                state["inventory_raw"] = inv
            except MCPError:
                pass
            try:
                blocks = self._call("observe", {
                    "target": "blocks",
                    "blockTypes": ["oak_log", "stone", "grass_block", "dirt", "crafting_table", "furnace", "spruce_planks"],
                    "maxDistance": 16, "maxCount": 8}, timeout=20)
                state["blocks"] = (blocks or {}).get("blocks") or []
                state["scan"] = {"blocks": state["blocks"]}
            except MCPError:
                pass
            try:
                chat = self._call("observe", {"target": "chat", "limit": 20},
                                  timeout=15)
                state["chat"] = (chat or {}).get("messages") or []
            except MCPError:
                pass
        with self._state_lock:
            self._state_seq += 1
            state["seq"] = self._state_seq
            self._latest_state = state
            self._last_state_at = time.time()
        with self._state_cond:
            self._state_cond.notify_all()
        self._set_stats(state_seq=state["seq"], position=state["pos"],
                        health=state["hp"], food=state["food"],
                        acting=state["acting"])
        if self.on_state:
            try:
                self.on_state(copy.deepcopy(state))
            except Exception:
                pass

    def tool(self, name: str, args: dict | None = None) -> Any:
        """Invoke a public MCP tool (diagnostics/adapters)."""
        return self._call(name, args or {}, timeout=30)

    def observe(self, target: str, **kwargs) -> Any:
        args = {"target": target}
        args.update(kwargs)
        return self._call("observe", args, timeout=30)

    @staticmethod
    def _inventory_to_dict(inv: Any) -> dict:
        if not isinstance(inv, dict):
            return {}
        items = inv.get("items") or []
        out: dict[str, int] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("item") or it.get("type")
            if not name:
                continue
            try:
                n = int(it.get("count") or 1)
            except Exception:
                n = 1
            out[str(name)] = out.get(str(name), 0) + n
        return out

    def _poll_loop(self) -> None:
        last_full = 0.0
        while not self._stop.is_set():
            if not self.connected:
                if not self.auto_restart:
                    break
                if not self._restart_client():
                    break
                last_full = 0.0
                continue
            try:
                now = time.time()
                full = (now - last_full) >= 2.0
                if not self._action_busy.is_set():
                    self._refresh_state(full=full)
                    if full:
                        last_full = now
            except Exception as e:
                self._set_stats(last_error=str(e))
                if self.client and not self.client.connected:
                    self.connected = False
                    with self._state_cond:
                        self._state_cond.notify_all()
                    if self.on_disconnect:
                        try:
                            self.on_disconnect(str(e))
                        except Exception:
                            pass
            self._stop.wait(self.poll_interval)

    def _restart_client(self) -> bool:
        if self._stop.is_set() or not self.auto_restart:
            return False
        if not self._restart_lock.acquire(blocking=False):
            return False
        try:
            old = self.client
            self.client = None
            if old:
                old.close()
            attempts = 0
            while not self._stop.is_set() and attempts < 6:
                attempts += 1
                try:
                    self._start_client()
                    with self._state_lock:
                        self._latest_state = None
                    self._set_stats(restarts=self.stats.get("restarts", 0) + 1,
                                    restart_attempts=attempts)
                    if self.on_connect:
                        try:
                            self.on_connect()
                        except Exception:
                            pass
                    return True
                except Exception as e:
                    self._set_stats(last_error=f"restart: {e}",
                                    restart_attempts=attempts)
                    self._stop.wait(self.restart_delay * attempts)
            return False
        finally:
            self._restart_lock.release()

    # ── action translation ────────────────────────────────────

    def map_action(self, frame: dict) -> dict:
        if not isinstance(frame, dict):
            raise ActionError("E_INVAL", "frame must be an object")
        op = str(frame.get("op") or "")
        spec = (self.mapping.get("ops") or {}).get(op)
        if not spec:
            raise ActionError("E_NOTSUP", f"MCP driver does not support op: {op}")
        channel = frame.get("channel")
        if channel and channel != spec.get("channel"):
            raise ActionError("E_INVAL", "channel does not match mapping")
        args = frame.get("args") or {}
        if not isinstance(args, dict):
            raise ActionError("E_INVAL", "args must be an object")
        tool = op
        targs: dict = {}
        if op == "move":
            if isinstance(args.get("p"), (list, tuple)) and len(args["p"]) == 3:
                tool = "move"
                targs = {"mode": "to", "x": float(args["p"][0]),
                         "y": float(args["p"][1]), "z": float(args["p"][2]),
                         "timeoutMs": 30000}
            else:
                d = args.get("dir") or [0, 0]
                if not isinstance(d, (list, tuple)) or len(d) < 2:
                    raise ActionError("E_INVAL", "move needs p or dir")
                dx = int(round(float(d[0])))
                dz = int(round(float(d[1])))
                if dx == 0 and dz == 0:
                    raise ActionError("E_INVAL", "move dir is zero")
                tool = "move"
                targs = {"mode": "relative", "dx": dx, "dy": 0, "dz": dz,
                         "timeoutMs": 30000}
        elif op == "goto":
            p = args.get("p")
            if not isinstance(p, (list, tuple)) or len(p) != 3:
                raise ActionError("E_INVAL", "goto needs p")
            tool = "move"
            targs = {"mode": "to", "x": float(p[0]), "y": float(p[1]),
                     "z": float(p[2]), "timeoutMs": 60000}
        elif op in ("dig", "place"):
            p = args.get("p")
            if not isinstance(p, (list, tuple)) or len(p) != 3:
                raise ActionError("E_INVAL", f"{op} needs p")
            dx, dy, dz = self._delta(p)
            tool = op
            targs = {"dx": dx, "dy": dy, "dz": dz}
            if args.get("item"):
                targs["itemName"] = str(args["item"])
        elif op == "say":
            tool = "chat"
            targs = {"message": str(args.get("text") or "")}
            if not targs["message"]:
                raise ActionError("E_INVAL", "say needs text")
        elif op == "attack":
            tool = "attack"
            t = args.get("target")
            if not isinstance(t, int):
                raise ActionError("E_INVAL", "MCP attack needs numeric entity target")
            targs = {"entity_id": t}
        elif op == "use":
            tool = "use"
            p = args.get("p")
            if isinstance(p, (list, tuple)) and len(p) == 3:
                dx, dy, dz = self._delta(p)
                targs = {"action": "block", "dx": dx, "dy": dy, "dz": dz}
            else:
                targs = {"action": "item"}
        elif op == "craft":
            tool = "use"
            targs = {"action": "craft", "itemName": str(args.get("item") or ""),
                     "count": int(args.get("count") or 1)}
            if not targs["itemName"]:
                raise ActionError("E_INVAL", "craft needs item")
        elif op == "equip":
            tool = "inventory"
            name = str(args.get("name") or "")
            if not name:
                raise ActionError("E_INVAL", "equip needs name")
            targs = {"action": "equip", "name": name,
                     "destination": args.get("destination") or "hand"}
        elif op == "stop":
            raise ActionError("E_NOTSUP",
                              "MCP mineflayer server has no stop tool; use estop")
        else:
            raise ActionError("E_NOTSUP", f"MCP driver has no adapter for op: {op}")
        return {"cmd": op, "tool": tool, "args": targs, "channel": channel}

    def _delta(self, p) -> tuple[int, int, int]:
        st = self._latest_state or {}
        pos = st.get("pos")
        if not pos or pos[0] is None:
            raise ActionError("E_STALE", "no position yet; cannot compute relative offset")
        # MCP dig/place uses floor(bot feet) + offset, not rounded distance.
        import math
        return (int(math.floor(float(p[0]))) - int(math.floor(float(pos[0]))),
                int(math.floor(float(p[1]))) - int(math.floor(float(pos[1]))),
                int(math.floor(float(p[2]))) - int(math.floor(float(pos[2]))))

    def send(self, command: dict) -> bool:
        if not self.connected:
            return False
        if not isinstance(command, dict):
            return False
        self._actions.put(command)
        return True

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                cmd = self._actions.get(timeout=0.2)
            except queue.Empty:
                continue
            if cmd is None:
                break
            tool = cmd.get("tool")
            cid = cmd.get("cmd")
            args = cmd.get("args") or {}
            self._action_busy.set()
            try:
                result = self._call(str(tool), args, timeout=120)
                self._action_busy.clear()
                try:
                    # Publish the post-action observation before the result so
                    # an immediate read sees the new position, not the old one.
                    self._refresh_state(full=False)
                except Exception:
                    pass
                self._set_stats(last_action=cid, acting="idle")
                if self.on_result:
                    self.on_result(cid, True, None,
                                   result if isinstance(result, dict)
                                   else {"result": result})
            except Exception as e:
                self._set_stats(last_error=str(e), acting="idle")
                if self.client and not self.client.connected:
                    self.connected = False
                    with self._state_cond:
                        self._state_cond.notify_all()
                    if self.on_disconnect:
                        try:
                            self.on_disconnect(str(e))
                        except Exception:
                            pass
                if self.on_result:
                    self.on_result(cid, False, str(e),
                                   {"tool": tool, "error": str(e)})
            finally:
                self._action_busy.clear()
