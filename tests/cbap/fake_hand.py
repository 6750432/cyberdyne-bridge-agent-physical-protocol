#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A tiny fake legacy hand for CBAP gateway tests.

It speaks the same line-JSON as node/server.js, but does not touch Minecraft.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time


class FakeHand:
    def __init__(self, socket_path: str):
        self.socket_path = os.path.abspath(socket_path)
        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._clients: set[socket.socket] = set()
        self._lock = threading.Lock()
        self.commands: list[dict] = []
        self.seq = 0
        self.pos = [0.0, 64.0, 0.0]
        self.items = {"oak_log": 1}
        self.chest = {"oak_log": 5}
        self.state = self._base_state()

    def _base_state(self) -> dict:
        return {
            "type": "state",
            "t": int(time.time() * 1000),
            "seq": self.seq,
            "bot": "FakeHand",
            "connected": True,
            "pos": list(self.pos),
            "hp": 20.0,
            "food": 20,
            "onGround": True,
            "look": {"yaw": 0.0, "pitch": 0.0},
            "near": [],
            "threats": [],
            "foods": [],
            "players": [],
            "friends": [],
            "weapons": [],
            "held": None,
            "drops": [],
            "hz": 5,
            "plugins": {"pathfinder": False, "body": True},
            "watched": None,
            "respawned": False,
            "deaths": 0,
            "scan": None,
            "durability": {"held": None, "armor": {}},
            "blocks": [],
            "items": dict(self.items),
            "chest": {"p": [1, 64, 1], "items": dict(self.chest),
                      "t": int(time.time() * 1000)},
            "furnace": None,
            "stuck_count": 0,
            "stuck_ms": None,
            "stuck_dir": None,
            "attacked_by": None,
            "acting": "idle",
            "msg": None,
        }

    def start(self, timeout: float = 2.0) -> bool:
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except OSError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.socket_path)
        srv.listen(4)
        srv.settimeout(0.5)
        self._srv = srv
        self._thread = threading.Thread(
            target=self._serve, name="fake-hand", daemon=True)
        self._thread.start()
        self._ready.set()
        return self._ready.wait(timeout)

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._srv:
                self._srv.close()
        except OSError:
            pass
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            try:
                c.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except OSError:
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._clients.add(conn)
            threading.Thread(target=self._client, args=(conn,),
                             name="fake-hand-client", daemon=True).start()

    def _client(self, conn: socket.socket) -> None:
        buf = b""
        conn.settimeout(0.5)
        try:
            self._send(conn, self.state)
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    self._command(conn, msg)
        finally:
            with self._lock:
                self._clients.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _send(self, conn: socket.socket, msg: dict) -> None:
        try:
            conn.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            pass

    def _send_state(self) -> None:
        self.seq += 1
        self.state = self._base_state()
        self.state["seq"] = self.seq
        self.state["t"] = int(time.time() * 1000)
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            self._send(c, self.state)

    def _result(self, conn: socket.socket, cmd: str, ok: bool,
                why: str | None = None, extra: dict | None = None) -> None:
        msg = {
            "type": "event", "kind": "cmdResult", "cmd": cmd, "ok": bool(ok),
            "why": why, "t": int(time.time() * 1000),
        }
        if extra:
            msg.update(extra)
        self._send(conn, msg)

    def _command(self, conn: socket.socket, msg: dict) -> None:
        with self._lock:
            self.commands.append(msg)
        cmd = msg.get("cmd") or msg.get("act")
        if cmd in ("jump", "sneak", "swimdown", "jumpattack", "eat", "use"):
            self._result(conn, str(cmd), True, None, {})
            return
        if cmd == "collect":
            n = max(1, int(msg.get("数量", msg.get("count", 1)) or 1))
            item = str(msg.get("物品") or msg.get("item") or "oak_log")
            self.items[item] = self.items.get(item, 0) + n
            self._result(conn, "collect", True, None,
                         {"物品": item, "数量": n})
            self._send_state()
            return
        if cmd == "chest_audit":
            self._result(conn, "chest_audit", True, None,
                         {"p": msg.get("p"), "箱内": dict(self.chest)})
            return
        if cmd == "chest_take":
            item = str(msg.get("物品") or msg.get("item") or "")
            n = max(1, int(msg.get("数量", msg.get("count", 1)) or 1))
            n = min(n, self.chest.get(item, 0))
            if not n:
                self._result(conn, "chest_take", False,
                             f"箱子里没有「{item}」")
                return
            self.chest[item] -= n
            self.items[item] = self.items.get(item, 0) + n
            self._result(conn, "chest_take", True, None,
                         {"拿到": item, "数量": n})
            self._send_state()
            return
        if cmd == "chest_put":
            item = str(msg.get("物品") or msg.get("item") or "")
            n = max(1, int(msg.get("数量", msg.get("count", 1)) or 1))
            n = min(n, self.items.get(item, 0))
            if not n:
                self._result(conn, "chest_put", False,
                             f"背包里没有「{item}」")
                return
            self.items[item] -= n
            self.chest[item] = self.chest.get(item, 0) + n
            self._result(conn, "chest_put", True, None,
                         {"放了": item, "数量": n})
            self._send_state()
            return
        if cmd in ("furnace_put", "furnace_take"):
            self._result(conn, str(cmd), True, None, {})
            return
        if cmd == "递":
            self._result(conn, "递", True, None,
                         {"物品": msg.get("物品"), "数量": msg.get("数量", 1)})
            return
        if cmd == "move":
            d = msg.get("dir") or [0, 0]
            ms = min(max(int(msg.get("ms") or 100), 1), 5000)
            delay = max(0, int(msg.get("delay_ms") or 0))
            if delay:
                time.sleep(min(delay, 5000) / 1000.0)
            self.pos[0] += float(d[0]) * ms / 1000.0
            self.pos[2] += float(d[1]) * ms / 1000.0
            self._result(conn, "move", True, None, {"ms": ms})
            self._send_state()
            return
        if cmd == "dig":
            p = msg.get("p") or [0, 0, 0]
            delay = max(0, int(msg.get("delay_ms") or 0))
            if delay:
                time.sleep(min(delay, 5000) / 1000.0)
            self.items["oak_log"] = self.items.get("oak_log", 0) + 1
            self._result(conn, "dig", True, None, {"p": p})
            self._send_state()
            return
        if cmd == "place":
            self._result(conn, "place", True, None, {"p": msg.get("p")})
            self._send_state()
            return
        if cmd == "craft":
            self._result(conn, "craft", True, None, {"item": msg.get("item")})
            self._send_state()
            return
        if cmd == "say":
            self._result(conn, "say", True, None, {"text": msg.get("text")})
            chat = {
                "type": "event", "kind": "chat", "from": "FakeHand",
                "text": str(msg.get("text") or ""),
                "t": int(time.time() * 1000),
            }
            self._send(conn, chat)
            return
        if cmd == "stop":
            self._result(conn, "stop", True)
            return
        if cmd == "scan_environment":
            self._result(conn, "scan_environment", True, None,
                         {"方块类": 0, "实体": 0, "要找": [], "命中": 0})
            return
        if cmd == "watch_blocks":
            self._result(conn, "watch_blocks", True, None, {"盯着": 0})
            return
        if cmd == "watch_items":
            self._result(conn, "watch_items", True, None, {"盯着": 1})
            return
        if cmd == "furnace_watch":
            self._result(conn, "furnace_watch", True, None,
                         {"盯着": msg.get("p")})
            return
        if cmd == "attack":
            self._result(conn, "attack", True, None, {"target": msg.get("target")})
            return
        if cmd == "goto":
            self.pos = [float(x) for x in (msg.get("p") or self.pos)[:3]]
            self._result(conn, "goto", True, None, {"p": self.pos})
            self._send_state()
            return
        self._result(conn, str(cmd or "unknown"), False,
                     f"fake hand does not know {cmd}")
