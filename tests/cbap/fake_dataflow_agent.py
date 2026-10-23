#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A fake external data-flow MC agent used as a CBAP peripheral.

It intentionally uses a different wire shape from node/server.js:
  state:  {"type":"state","seq":N,"state":{...}}
  action: {"type":"action","id":"a-1","channel":"body","op":"move","args":{...}}
  result: {"type":"result","id":"a-1","ok":true,"data":{...}}
  estop:  {"type":"estop","id":"e-1"}
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time


class FakeDataFlowAgent:
    def __init__(self, socket_path: str, name: str = "flow-agent"):
        self.socket_path = os.path.abspath(socket_path)
        self.name = name
        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._clients: set[socket.socket] = set()
        self._lock = threading.Lock()
        self.seq = 0
        self.pos = [100.0, 64.0, 100.0]
        self.items = {"oak_log": 4}
        self.chest = {"oak_log": 3}
        self.commands: list[dict] = []
        self.estops = 0

    def _state(self) -> dict:
        self.seq += 1
        return {
            "type": "state", "seq": self.seq,
            "t": int(time.time() * 1000),
            "state": {
                "type": "state",
                "pos": list(self.pos), "hp": 20.0, "food": 20,
                "onGround": True,
                "held": None,
                "items": dict(self.items),
                "chest": {"p": [100, 64, 101], "items": dict(self.chest),
                          "t": int(time.time() * 1000)},
                "scan": None, "blocks": [],
                "chat": [],
                "acting": "idle",
                "device": self.name,
            },
        }

    def _send(self, conn, obj):
        try:
            conn.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            pass

    def _broadcast_state(self):
        with self._lock:
            clients = list(self._clients)
        st = self._state()
        for c in clients:
            self._send(c, st)

    def _serve(self):
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
                             name="fake-flow-client", daemon=True).start()

    def _client(self, conn):
        buf = b""
        conn.settimeout(0.5)
        try:
            self._send(conn, {"type": "cbap_ready", "v": "1.0",
                              "device_id": f"mcflow://agent/{self.name}"})
            self._send(conn, self._state())
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
                    except Exception:
                        continue
                    self._handle(conn, msg)
        finally:
            with self._lock:
                self._clients.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _result(self, conn, rid, ok=True, why=None, data=None, facts=None):
        msg = {"type": "result", "id": rid, "ok": bool(ok),
               "why": why, "t": int(time.time() * 1000)}
        if data is not None:
            msg["data"] = data
        if facts is not None:
            msg["facts"] = facts
        self._send(conn, msg)

    def _handle(self, conn, msg):
        typ = msg.get("type")
        if typ == "cbap_hello":
            return
        with self._lock:
            self.commands.append(msg)
        if typ == "estop":
            self.estops += 1
            self._result(conn, msg.get("id"), True, None,
                         {"safe_state": "idle"})
            self._broadcast_state()
            return
        if typ == "ioctl":
            self._result(conn, msg.get("id"), True, None,
                         {"ioctl": msg.get("op"), "ok": True})
            return
        if typ != "action":
            return
        rid = msg.get("id")
        op = msg.get("op")
        args = msg.get("args") or {}
        if op == "move":
            d = args.get("dir") or [0, 0]
            ms = max(1, int(args.get("ms") or 100))
            self.pos[0] += float(d[0]) * ms / 1000.0
            self.pos[2] += float(d[1]) * ms / 1000.0
            self._result(conn, rid, True, None, {"pos": list(self.pos)})
            self._broadcast_state()
            return
        if op == "dig":
            self.items["oak_log"] = self.items.get("oak_log", 0) + 1
            self._result(conn, rid, True, None, {"block": "air"})
            self._broadcast_state()
            return
        if op == "collect":
            n = max(1, int(args.get("count") or 1))
            item = str(args.get("item") or "oak_log")
            self.items[item] = self.items.get(item, 0) + n
            self._result(conn, rid, True, None, {"item": item, "count": n})
            self._broadcast_state()
            return
        if op == "say":
            text = str(args.get("text") or "")
            self._result(conn, rid, True, None, {"text": text})
            self._send(conn, {"type": "event", "kind": "chat",
                              "t": int(time.time() * 1000),
                              "payload": {"text": text}})
            return
        if op == "stop":
            self._result(conn, rid, True, None, {"stopped": True})
            return
        if op in ("jump", "sneak", "swimdown", "eat", "use",
                  "chest_audit", "furnace_put", "furnace_take", "give"):
            self._result(conn, rid, True, None, {"op": op})
            return
        self._result(conn, rid, False, f"fake flow agent does not know {op}")

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
        self._thread = threading.Thread(target=self._serve, name="fake-flow",
                                        daemon=True)
        self._thread.start()
        return True

    def stop(self):
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
