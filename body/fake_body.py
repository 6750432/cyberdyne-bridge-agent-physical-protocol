#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Protocol-compatible fake MC body for SDK tests. No Minecraft required."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

VERSION = "mc-body/1"
CAPS = ["goto", "collect", "craft", "equip", "dig", "place", "say", "stop", "batch"]


class FakeBody:
    def __init__(self, socket_path: str | os.PathLike[str]):
        self.socket_path = str(socket_path)
        self._stop = threading.Event()
        self._thread = None
        self._srv = None
        self._seq = 0
        self._lock = threading.Lock()
        self._conns: set[socket.socket] = set()
        self.inventory = {"oak_log": 0, "cobblestone": 0, "stone_pickaxe": 0}
        self.pos = [0.0, 64.0, 0.0]

    def start(self):
        p = Path(self.socket_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        srv.listen(8)
        srv.settimeout(0.2)
        self._srv = srv
        self._thread = threading.Thread(target=self._serve, name="fake-body", daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._conns.add(conn)
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    def _send(self, conn, msg):
        try:
            conn.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            pass

    def _state(self):
        with self._lock:
            self._seq += 1
            return {
                "v": VERSION, "type": "state", "seq": self._seq,
                "t": int(time.time() * 1000),
                "body": {
                    "pos": list(self.pos), "yaw": 0, "pitch": 0,
                    "hp": 20, "food": 20, "on_ground": True,
                    "held": None, "inventory": dict(self.inventory),
                    "nearby_blocks": [], "players": [],
                },
            }

    def _session(self, conn):
        buf = b""
        conn.settimeout(0.1)
        last_state = 0.0
        try:
            while not self._stop.is_set():
                now = time.time()
                if now - last_state >= 0.1:
                    self._send(conn, self._state())
                    last_state = now
                try:
                    data = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    self._handle(conn, msg)
        finally:
            with self._lock:
                self._conns.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _handle(self, conn, msg):
        typ = msg.get("type")
        rid = msg.get("id")
        if typ == "hello":
            self._send(conn, {
                "v": VERSION, "type": "welcome", "id": rid,
                "body_id": "fake-body-1", "mc_version": "1.21.1",
                "capabilities": CAPS,
            })
            return
        if typ == "health":
            self._send(conn, {"v": VERSION, "type": "health", "id": rid,
                              "ok": True, "mc_connected": True,
                              "uptime_ms": 1})
            return
        if typ == "shutdown":
            self._send(conn, {"v": VERSION, "type": "result", "id": rid,
                              "ok": True, "facts": {"stopped": True}})
            self._stop.set()
            return
        if typ != "command":
            return
        cmd = str(msg.get("cmd") or "")
        args = msg.get("args") or {}
        self._send(conn, {"v": VERSION, "type": "ack", "id": rid,
                          "state": "accepted", "t": int(time.time()*1000)})
        # A tiny simulated local action; no Minecraft.
        time.sleep(0.02)
        ok, facts, err = True, {}, None
        if cmd == "goto":
            self.pos = [float(args.get("x", 0)), float(args.get("y", 64)),
                        float(args.get("z", 0))]
            facts = {"reached": True, "position": list(self.pos),
                     "duration_ms": 20}
        elif cmd == "collect":
            block = str(args.get("block") or "oak_log")
            count = int(args.get("count") or 1)
            self.inventory[block] = self.inventory.get(block, 0) + count
            facts = {"block": block, "collected": count,
                     "inventory": dict(self.inventory)}
        elif cmd == "craft":
            item = str(args.get("item") or "stone_pickaxe")
            count = int(args.get("count") or 1)
            self.inventory[item] = self.inventory.get(item, 0) + count
            facts = {"item": item, "count": count,
                     "inventory": dict(self.inventory)}
        elif cmd in ("equip", "dig", "place", "say", "stop"):
            facts = {"cmd": cmd, "ok": True}
        elif cmd == "batch":
            facts = {"completed": len(args.get("steps") or [])}
        else:
            ok, err = False, {"code": "E_NOTSUP",
                              "message": f"unknown cmd: {cmd}",
                              "retryable": False}
        self._send(conn, {"v": VERSION, "type": "result", "id": rid,
                          "ok": ok, "facts": facts, "error": err})

    def stop(self):
        self._stop.set()
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
        with self._lock:
            for c in list(self._conns):
                try:
                    c.close()
                except OSError:
                    pass
            self._conns.clear()
        try:
            Path(self.socket_path).unlink()
        except FileNotFoundError:
            pass
