#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal MCP stdio client (JSON-RPC 2.0, newline framed).

The MCP server is an external process. We do not import or modify its code.
Only the public MCP methods are used: initialize, tools/list, tools/call.
"""

from __future__ import annotations

import json
import os
import queue
import select
import subprocess
import sys
import threading
import time
from typing import Any


class MCPError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPStdioClient:
    def __init__(self, command: list[str], cwd: str | None = None,
                 env: dict | None = None, timeout: float = 30.0):
        self.command = [str(x) for x in command]
        self.cwd = cwd
        self.env = dict(os.environ)
        if env:
            self.env.update({str(k): str(v) for k, v in env.items()})
        self.timeout = float(timeout)
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stop = threading.Event()
        self.stderr_tail: list[str] = []
        self.server_info: dict = {}
        self.tools: list[dict] = []
        self.connected = False
        self.last_error: str | None = None

    def _next_id(self) -> int:
        with self._id_lock:
            self._id += 1
            return self._id

    def _send(self, obj: dict) -> None:
        if not self.proc or self.proc.poll() is not None:
            raise MCPError("MCP process is not running")
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            assert self.proc.stdin is not None
            self.proc.stdin.write(data)
            self.proc.stdin.flush()

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for raw in iter(self.proc.stdout.readline, b""):
            if self._stop.is_set():
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            # The external server may write warnings/stack traces to stdout.
            # Ignore anything that is not a JSON-RPC object.
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            rid = msg.get("id")
            if rid is not None:
                with self._pending_lock:
                    q = self._pending.pop(int(rid), None)
                if q is not None:
                    q.put(msg)
            # notifications are intentionally ignored in v0
        # process ended: fail all waiters
        with self._pending_lock:
            waiters = list(self._pending.values())
            self._pending.clear()
        for q in waiters:
            q.put({"error": {"code": -32000, "message": "MCP process ended"}})
        self.connected = False

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for raw in iter(self.proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self.stderr_tail.append(line)
                if len(self.stderr_tail) > 80:
                    self.stderr_tail.pop(0)

    def start(self) -> dict:
        if self.proc and self.proc.poll() is None:
            return self.server_info
        self._stop.clear()
        self.proc = subprocess.Popen(
            self.command, cwd=self.cwd, env=self.env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )
        self._reader = threading.Thread(target=self._read_stdout,
                                        name="mcp-stdout", daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr,
                                               name="mcp-stderr", daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        result = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cyberdyne-cbap", "version": "0.1.0"},
        }, timeout=self.timeout)
        self.server_info = result or {}
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self.request("tools/list", {}, timeout=self.timeout) or {}
        self.tools = list(tools.get("tools") or [])
        self.connected = True
        return self.server_info

    def request(self, method: str, params: dict | None = None,
                timeout: float | None = None) -> Any:
        rid = self._next_id()
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[rid] = q
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                        "params": params or {}})
        except Exception:
            with self._pending_lock:
                self._pending.pop(rid, None)
            raise
        try:
            msg = q.get(timeout=timeout or self.timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(rid, None)
            raise MCPError(f"MCP timeout: {method}")
        if "error" in msg:
            err = msg.get("error") or {}
            raise MCPError(str(err.get("message") or "MCP error"),
                           err.get("code"), err.get("data"))
        return msg.get("result")

    def call_tool(self, name: str, args: dict | None = None,
                  timeout: float | None = None) -> Any:
        result = self.request("tools/call", {
            "name": name,
            "arguments": args or {},
        }, timeout=timeout)
        if not isinstance(result, dict):
            return result
        if result.get("isError"):
            texts = [c.get("text", "") for c in (result.get("content") or [])
                     if isinstance(c, dict)]
            raise MCPError("; ".join(texts) or f"tool failed: {name}")
        content = result.get("content") or []
        if isinstance(content, list):
            texts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    texts.append(str(c.get("text") or ""))
            if len(texts) == 1:
                text = texts[0]
                try:
                    return json.loads(text)
                except Exception:
                    return text
            if texts:
                return texts
        return result

    def close(self) -> None:
        self._stop.set()
        self.connected = False
        p = self.proc
        if p is None:
            return
        try:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        finally:
            for stream in (p.stdin, p.stdout, p.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
            self.proc = None
