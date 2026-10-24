#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Security regression tests for the hardened CBAP Kernel."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer


class SecurityDriver:
    def __init__(self):
        self.connected = True
        self.state = {"on": False, "level": 0}
        self.seq = 0
        self.estop_count = 0
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_disconnect = None

    def describe(self):
        return {
            "device_id": "test://security/light-01",
            "type": "test-light",
            "safety": {"estop": True, "watchdog_ms": 5000,
                       "safe_state": "off"},
        }

    def health(self):
        return {"ok": True, "state_age_ms": 0,
                "device_id": "test://security/light-01"}

    def wait_state(self, timeout_s):
        self.seq += 1
        return dict(self.state, seq=self.seq, t=time.time())

    def estop(self):
        self.estop_count += 1
        self.state["on"] = False
        return True

    def send(self, command):
        # Leave the write pending so release/cancel/fencing can be tested.
        if getattr(self, "complete", False):
            cb = self.on_result
            if cb:
                cb("move", True, None, {"facts": {}})
        return True

    def map_action(self, frame):
        return {"cmd": str((frame or {}).get("op") or "unknown")}


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-security-")
        self.sock = os.path.join(self.tmp, "cbap.sock")
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self.driver = SecurityDriver()
        self.kernel = KernelServer(self.driver, socket_path=self.sock,
                                   audit_path=self.audit,
                                   max_inflight=4, rate_hz=20)
        self.assertTrue(self.kernel.start())

    def tearDown(self):
        self.kernel.stop()

    def client(self, agent="viewer", operator=False):
        c = CBAPClient(self.sock, agent_id=agent)
        c.connect()
        op = None
        if operator:
            with open(self.sock + ".operator", encoding="ascii") as f:
                op = f.read().strip()
        c.hello(operator_token=op)
        return c

    def test_socket_and_token_are_private(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.sock).st_mode), 0o600)
        token_path = self.sock + ".token"
        self.assertTrue(os.path.exists(token_path))
        self.assertEqual(stat.S_IMODE(os.stat(token_path).st_mode), 0o600)
        with open(token_path, encoding="ascii") as f:
            self.assertTrue(f.read().strip())

    def test_agent_cannot_estop_without_role(self):
        viewer = self.client("viewer")
        opened = viewer.open("test://security/light-01", "rw")
        self.assertTrue(opened["ok"], opened)
        fd = opened["payload"]["fd"]
        self.assertTrue(viewer.lease(fd)["ok"])
        denied = viewer.estop(fd, reason="viewer")
        self.assertEqual(denied["error"]["code"], "E_PERM")
        operator = self.client("cbap-operator", operator=True)
        op_fd = operator.open("test://security/light-01", "r")["payload"]["fd"]
        allowed = operator.estop(op_fd, reason="operator")
        self.assertTrue(allowed["ok"], allowed)
        viewer.close()
        operator.close()

    def test_per_agent_token_and_uid(self):
        import hashlib
        tok = "agent-secret"
        h = hashlib.sha256(tok.encode()).hexdigest()
        policy = {"agents": {"viewer": {
            "devices": ["test://security/light-01"],
            "capabilities": ["read", "write", "lease"],
            "uids": [os.getuid()],
            "token_sha256": h,
        }}}
        k = KernelServer(
            SecurityDriver(), socket_path=os.path.join(self.tmp, "a.sock"),
            audit_path=os.path.join(self.tmp, "a-audit.jsonl"), policy=policy)
        self.assertTrue(k.start())
        try:
            sock = os.path.join(self.tmp, "a.sock")
            bad = CBAPClient(sock, agent_id="viewer")
            bad.connect()
            with self.assertRaises(Exception):
                bad.hello(agent_token="wrong")
            bad.close()
            good = CBAPClient(sock, agent_id="viewer")
            good.connect()
            self.assertTrue(good.hello(agent_token=tok).get("session_id"))
            good.close()
        finally:
            k.stop()

    def test_device_allowlist(self):
        k = KernelServer(
            SecurityDriver(), socket_path=os.path.join(self.tmp, "p.sock"),
            audit_path=os.path.join(self.tmp, "p-audit.jsonl"),
            policy={"default": {"devices": ["other://allowed"],
                                "capabilities": ["read", "write", "lease"]}})
        self.assertTrue(k.start())
        try:
            c = CBAPClient(os.path.join(self.tmp, "p.sock"), agent_id="viewer")
            c.connect(); c.hello()
            r = c.open("test://security/light-01", "r")
            self.assertEqual(r["error"]["code"], "E_PERM")
            c.close()
        finally:
            k.stop()

    def test_inflight_limit_and_cancel(self):
        k = KernelServer(
            SecurityDriver(), socket_path=os.path.join(self.tmp, "l.sock"),
            audit_path=os.path.join(self.tmp, "l-audit.jsonl"),
            max_inflight=1, rate_hz=20)
        self.assertTrue(k.start())
        try:
            c = CBAPClient(os.path.join(self.tmp, "l.sock"), agent_id="viewer")
            c.connect(); c.hello()
            fd = c.open("test://security/light-01", "rw")["payload"]["fd"]
            c.lease(fd)
            r1 = c.request("write", {"fd": fd, "frame": {
                "channel": "body", "op": "move", "args": {}}})
            c.wait_ack(r1)
            r2 = c.call("write", {"fd": fd, "frame": {
                "channel": "body", "op": "move", "args": {}}})
            self.assertEqual(r2["error"]["code"], "E_BUSY")
            c.release(fd)
            self.assertEqual(c.wait(r1, 2)["error"]["code"], "E_CANCELED")
            c.close()
        finally:
            k.stop()

    def test_audit_truncation_is_detected(self):
        from kernel.legacy_runtime.security import AuditChain
        path = os.path.join(self.tmp, "trunc.jsonl")
        a = AuditChain(path, signing_key="k")
        a.append("one"); a.append("two")
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[:-1]) + "\n")
        ok, why = AuditChain(path, signing_key="k").verify()
        self.assertFalse(ok, why)

    def test_preauth_connection_cap(self):
        import socket
        k = KernelServer(
            SecurityDriver(), socket_path=os.path.join(self.tmp, "c.sock"),
            audit_path=os.path.join(self.tmp, "c-audit.jsonl"),
            max_connections=1)
        self.assertTrue(k.start())
        a = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        b = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            a.connect(os.path.join(self.tmp, "c.sock"))
            time.sleep(0.2)
            b.settimeout(1)
            b.connect(os.path.join(self.tmp, "c.sock"))
            self.assertEqual(b.recv(1), b"")
        finally:
            a.close(); b.close(); k.stop()

    def test_symlink_token_target_is_rejected(self):
        from kernel.legacy_runtime.security import TokenFile
        target = os.path.join(self.tmp, "target")
        Path(target).write_text("do not touch", encoding="utf-8")
        token_path = os.path.join(self.tmp, "symlink.sock") + ".token"
        os.symlink(target, token_path)
        with self.assertRaises(OSError):
            TokenFile(os.path.join(self.tmp, "symlink.sock")).write()
        self.assertEqual(Path(target).read_text(encoding="utf-8"), "do not touch")

    def test_audit_chain_verifies(self):
        c = self.client("viewer")
        c.device_list()
        c.close()
        ok, why = self.kernel.audit.verify()
        self.assertTrue(ok, why)

    def test_release_cancels_pending_and_fencing_blocks_old_fd(self):
        a = self.client("viewer")
        b = self.client("viewer")
        fd_a = a.open("test://security/light-01", "rw")["payload"]["fd"]
        fd_b = b.open("test://security/light-01", "rw")["payload"]["fd"]
        lease_a = a.lease(fd_a)
        self.assertTrue(lease_a["ok"], lease_a)
        rid = a.request("write", {"fd": fd_a, "frame": {
            "channel": "body", "op": "move", "args": {}}}, deadline_ms=5000)
        a.wait_ack(rid)
        rel = a.release(fd_a)
        self.assertTrue(rel["ok"], rel)
        result = a.wait(rid, 2)
        self.assertEqual(result["error"]["code"], "E_CANCELED")
        lease_b = b.lease(fd_b)
        self.assertTrue(lease_b["ok"], lease_b)
        stale = a.call("write", {"fd": fd_a, "frame": {
            "channel": "body", "op": "move", "args": {"fencing_token": 1}}})
        self.assertEqual(stale["error"]["code"], "E_BUSY")
        a.close(); b.close()

    def test_audit_remote_mirror_receives_signed_rows(self):
        received = []

        class Sink(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or "0")
                raw = self.rfile.read(n).decode("utf-8")
                received.append(raw)
                row = json.loads(raw.splitlines()[0])
                body = json.dumps({"seq": row.get("seq"), "hash": row.get("hash")}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
        th = threading.Thread(target=sink.serve_forever, daemon=True)
        th.start()
        path = os.path.join(self.tmp, "remote-audit.jsonl")
        from kernel.legacy_runtime.security import AuditChain
        a = AuditChain(path, signing_key="audit-key",
                       remote_url=f"http://127.0.0.1:{sink.server_port}/audit",
                       require_remote_ack=True)
        a.append("unit", value=1)
        deadline = time.time() + 3
        while not received and time.time() < deadline:
            time.sleep(0.05)
        sink.shutdown(); sink.server_close(); th.join(timeout=1)
        self.assertTrue(received)
        self.assertIn('"mac"', received[0])
        deadline = time.time() + 3
        while not os.path.exists(a.remote_ack_path) and time.time() < deadline:
            time.sleep(0.05)
        ok, why = a.verify()
        self.assertTrue(ok, why)

    def test_require_independent_facts_rejects_self_report(self):
        k = KernelServer(
            SecurityDriver(), socket_path=os.path.join(self.tmp, "i.sock"),
            audit_path=os.path.join(self.tmp, "i-audit.jsonl"),
            require_independent_facts=True)
        k.driver.complete = True
        self.assertTrue(k.start())
        try:
            c = CBAPClient(os.path.join(self.tmp, "i.sock"), agent_id="viewer")
            c.connect(); c.hello()
            fd = c.open("test://security/light-01", "rw")["payload"]["fd"]
            c.lease(fd)
            # The fake driver emits no `independent: true` fact, so the
            # Kernel must refuse to call this verified.
            rid = c.request("write", {"fd": fd, "frame": {
                "channel": "body", "op": "move", "args": {}}})
            c.wait_ack(rid)
            # This driver reports synchronously, so the result may already
            # be queued; wait for it.
            r = c.wait(rid, 2)
            self.assertFalse(r.get("ok", False), r)
            c.close()
        finally:
            k.stop()

    def test_other_session_cannot_cancel(self):
        a = self.client("viewer")
        b = self.client("viewer")
        fd = a.open("test://security/light-01", "rw")["payload"]["fd"]
        a.lease(fd)
        rid = a.request("write", {"fd": fd, "frame": {
            "channel": "body", "op": "move", "args": {}}})
        a.wait_ack(rid)
        b.send({"v": "1.0", "type": "cancel", "id": "c-x",
                "ts": 1, "target": rid})
        r = b.wait("c-x", 2)
        self.assertFalse(r.get("ok"), r)
        self.assertEqual(r["error"]["code"], "E_PERM")
        self.assertTrue(a.release(fd)["ok"])
        self.assertEqual(a.wait(rid, 2)["error"]["code"], "E_CANCELED")
        a.close(); b.close()

    def test_auth_failures_degrade_to_safe(self):
        # Five bad hellos are counted by the Kernel monitor.
        import socket
        from kernel.legacy_runtime import protocol
        for _ in range(5):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.sock)
            msg = {"v": protocol.PROTOCOL_VERSION, "type": "hello",
                   "id": protocol.new_id("h"), "ts": protocol.now_ms(),
                   "agent_id": "intruder", "auth": {"token": "wrong"}}
            s.sendall(protocol.encode(msg))
            s.recv(4096)
            s.close()
        self.assertTrue(self.kernel._safe)
        ok, _ = self.kernel.audit.verify()
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
