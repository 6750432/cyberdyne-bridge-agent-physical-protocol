#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Executable CBAP v1 conformance cases (Core + safety subset).

These tests intentionally use the public wire shape only. They do not import
bridge.py or node/server.js.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import time
import unittest

from drivers.mc.driver import McDriver
from kernel.legacy_runtime import protocol
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.fake_hand import FakeHand

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEVICE = os.path.join(ROOT, "drivers", "mc", "device.json")
MAPPING = os.path.join(ROOT, "drivers", "mc", "mapping.json")
DEVICE_ID = "mc://bot/DeepSeek"


class NoStateDriver:
    """Minimal driver for read-timeout cases: valid descriptor, no state."""

    def __init__(self, health_ok: bool = True):
        with open(DEVICE, encoding="utf-8") as f:
            self.device = json.load(f)
        self.connected = True
        self._health_ok = health_ok
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_connect = None
        self.on_disconnect = None

    def describe(self):
        return json.loads(json.dumps(self.device))

    def wait_state(self, timeout_s):
        time.sleep(max(0.0, float(timeout_s)))
        return None

    def health(self):
        return {"ok": self._health_ok, "connected": self.connected,
                "state_age_ms": None, "device_id": self.device["device_id"]}

    def estop(self):
        return True

    def send(self, command):
        return True

    def map_action(self, frame):
        return {"cmd": str((frame or {}).get("op") or "unknown")}


class Harness:
    def __init__(self, token=None, driver=None, start_client=True):
        self.tmp = tempfile.mkdtemp(prefix="cbap-conf-")
        self.hand_sock = os.path.join(self.tmp, "hand.sock")
        self.cbap_sock = os.path.join(self.tmp, "cbap.sock")
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self.hand = None
        if driver is None:
            self.hand = FakeHand(self.hand_sock)
            self.hand.start()
            self.driver = McDriver(socket_path=self.hand_sock,
                                   device_path=DEVICE, mapping_path=MAPPING,
                                   connect_timeout=1.0, reconnect=True)
            self.driver.connect()
        else:
            self.driver = driver
        self.server = KernelServer(self.driver, socket_path=self.cbap_sock,
                                   audit_path=self.audit, token=token)
        if not self.server.start():
            raise RuntimeError("kernel did not start")
        self.client = None
        if start_client:
            self.client = self.new_client("cbap-operator", operator=True)

    def new_client(self, agent_id="cbap-operator", operator=False,
                   features=None):
        c = CBAPClient(self.cbap_sock, agent_id=agent_id)
        c.connect()
        op = None
        if operator:
            with open(self.cbap_sock + ".operator", encoding="ascii") as f:
                op = f.read().strip()
        c.hello(token=None, operator_token=op, features=features)
        return c

    def open(self, client=None, mode="rw"):
        c = client or self.client
        r = c.open(DEVICE_ID, mode)
        assert r.get("ok"), r
        return r["payload"]["fd"]

    def close(self):
        for c in [self.client]:
            try:
                if c:
                    c.close()
            except Exception:
                pass
        try:
            self.server.stop()
        except Exception:
            pass
        try:
            self.driver.close()
        except Exception:
            pass
        try:
            if self.hand:
                self.hand.stop()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)


def raw_connect(path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.0)
    s.connect(path)
    return s


def raw_send(sock, msg):
    sock.sendall(protocol.encode(msg))


def raw_recv(sock):
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    line = buf.split(b"\n", 1)[0]
    return json.loads(line.decode("utf-8")) if line else None


def hello_msg(agent="raw", version=protocol.PROTOCOL_VERSION, token=None):
    m = {"v": version, "type": "hello", "id": protocol.new_id("h"),
         "ts": protocol.now_ms(), "agent_id": agent,
         "role": "agent", "capabilities": ["read", "write", "lease", "estop"]}
    if token is not None:
        m["auth"] = {"token": token}
    return m


class ConformanceTest(unittest.TestCase):
    def setUp(self):
        self.h = None

    def tearDown(self):
        if self.h:
            self.h.close()
            self.h = None

    # 1
    def test_01_first_packet_must_be_hello(self):
        self.h = Harness()
        s = raw_connect(self.h.cbap_sock)
        raw_send(s, {"v": "1.0", "type": "request", "id": "r1",
                     "op": "device_list", "args": {}})
        msg = raw_recv(s)
        self.assertEqual(msg["error"]["code"], "E_PROTOCOL")
        s.close()

    # 2
    def test_02_version_mismatch(self):
        self.h = Harness()
        s = raw_connect(self.h.cbap_sock)
        raw_send(s, hello_msg(version="2.0"))
        msg = raw_recv(s)
        self.assertEqual(msg["error"]["code"], "E_VERSION")
        s.close()

    # 3
    def test_03_auth_failure(self):
        self.h = Harness(token="secret", start_client=False)
        s = raw_connect(self.h.cbap_sock)
        raw_send(s, hello_msg(token="wrong"))
        msg = raw_recv(s)
        self.assertEqual(msg["error"]["code"], "E_AUTH")
        self.assertNotIn("devices", msg)
        s.close()

    # 4
    def test_04_unknown_message_type(self):
        self.h = Harness()
        s = raw_connect(self.h.cbap_sock)
        raw_send(s, hello_msg(token=self.h.server.token))
        welcome = raw_recv(s)
        self.assertEqual(welcome["type"], "welcome")
        raw_send(s, {"v": "1.0", "type": "wat", "id": "w1"})
        msg = raw_recv(s)
        self.assertEqual(msg["error"]["code"], "E_PROTOCOL")
        raw_send(s, {"v": "1.0", "type": "request", "id": "r1",
                     "op": "device_list", "args": {}})
        msg = raw_recv(s)
        self.assertTrue(msg.get("ok"), msg)
        s.close()

    # 5
    def test_05_unknown_op(self):
        self.h = Harness()
        r = self.h.client.call("nope", {})
        self.assertEqual(r["error"]["code"], "E_NOTSUP")
        self.assertTrue(self.h.client.device_list().get("ok"))

    # 6
    def test_06_open_unknown_device(self):
        self.h = Harness()
        r = self.h.client.open("mc://nope", "r")
        self.assertEqual(r["error"]["code"], "E_NOENT")

    # 7
    def test_07_readonly_fd_write(self):
        self.h = Harness()
        fd = self.h.open(mode="r")
        r = self.h.client.call("write", {"fd": fd, "frame": {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}}})
        self.assertEqual(r["error"]["code"], "E_PERM")

    # 8
    def test_08_exclusive_conflict(self):
        self.h = Harness()
        c2 = self.h.new_client("second")
        try:
            fd1 = self.h.open()
            r = self.h.client.lease(fd1)
            self.assertTrue(r.get("ok"), r)
            r2 = c2.open(DEVICE_ID, "exclusive")
            self.assertEqual(r2["error"]["code"], "E_BUSY")
            _, _, result = self.h.client.write(fd1, {
                "channel": "body", "op": "move",
                "args": {"dir": [1, 0], "ms": 10}}, deadline_ms=2000)
            self.assertTrue(result.get("ok"), result)
        finally:
            c2.close()

    # 9
    def test_09_read_no_data_is_again(self):
        self.h = Harness(driver=NoStateDriver(), start_client=True)
        fd = self.h.open()
        r = self.h.client.read(fd, timeout_ms=0)
        self.assertEqual(r["error"]["code"], "E_AGAIN")

    # 10
    def test_10_read_timeout(self):
        self.h = Harness(driver=NoStateDriver(), start_client=True)
        fd = self.h.open()
        r = self.h.client.read(fd, timeout_ms=50)
        self.assertEqual(r["error"]["code"], "E_TIMEOUT")

    # 11
    def test_11_write_lifecycle_same_id(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        rid, ack, result = self.h.client.write(fd, {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}}, deadline_ms=2000)
        self.assertEqual(ack.get("state"), "accepted")
        self.assertEqual(ack.get("id"), rid)
        self.assertEqual(result.get("id"), rid)

    # 12
    def test_12_idempotent_write(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        before = len([c for c in self.h.hand.commands if c.get("cmd") == "move"])
        frame = {"channel": "body", "op": "move",
                 "args": {"dir": [1, 0], "ms": 10}}
        _, _, r1 = self.h.client.write(fd, frame, deadline_ms=2000,
                                       idempotency_key="same-key")
        _, _, r2 = self.h.client.write(fd, frame, deadline_ms=2000,
                                       idempotency_key="same-key")
        after = len([c for c in self.h.hand.commands if c.get("cmd") == "move"])
        self.assertTrue(r1.get("ok"), r1)
        self.assertTrue(r2.get("ok"), r2)
        self.assertEqual(after - before, 1, "side effect must happen once")

    # 13
    def test_13_cancel_pending_write(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        rid = self.h.client.request("write", {"fd": fd, "frame": {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10, "delay_ms": 400}}},
            deadline_ms=2000)
        ack = self.h.client.wait_ack(rid)
        self.assertEqual(ack.get("state"), "accepted")
        time.sleep(0.05)
        cid = protocol.new_id("c")
        self.h.client.send({"v": "1.0", "type": "cancel", "id": cid,
                            "target": rid})
        c = self.h.client.wait(cid, 2)
        self.assertTrue(c.get("ok"), c)
        r = self.h.client.wait(rid, 2)
        self.assertEqual(r["error"]["code"], "E_CANCELED")

    # 14
    def test_14_estop_blocks_write_and_audits(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        r = self.h.client.estop(fd, reason="conf-14")
        self.assertEqual(r["payload"]["safe_state"], "idle")
        r2 = self.h.client.call("write", {"fd": fd, "frame": {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}}})
        self.assertEqual(r2["error"]["code"], "E_SAFETY")
        with open(self.h.audit, encoding="utf-8") as f:
            self.assertTrue(any(json.loads(x).get("event") == "estop"
                                for x in f if x.strip()))

    # 15
    def test_15_state_seq_strictly_increases(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        seqs = []
        for _ in range(10):
            _, _, result = self.h.client.write(fd, {
                "channel": "body", "op": "move",
                "args": {"dir": [1, 0], "ms": 1}}, deadline_ms=2000)
            self.assertTrue(result.get("ok"), result)
            time.sleep(0.01)
            for msg in self.h.client.drain_inbox():
                if msg.get("type") == "state":
                    seqs.append(int(msg.get("seq") or 0))
        self.assertGreaterEqual(len(seqs), 10, seqs)
        for a, b in zip(seqs, seqs[1:]):
            self.assertEqual(b, a + 1, seqs)

    # 16
    def test_16_dig_not_complete_without_probe(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        rid = self.h.client.request("write", {"fd": fd, "frame": {
            "channel": "world", "op": "dig",
            "args": {"p": [1, 64, 1], "delay_ms": 400}}},
            deadline_ms=2000)
        self.assertEqual(self.h.client.wait_ack(rid).get("state"), "accepted")
        time.sleep(0.05)
        st = self.h.client.stat(fd)
        self.assertGreaterEqual(st["payload"].get("pending", 0), 1, st)
        cid = protocol.new_id("c")
        self.h.client.send({"v": "1.0", "type": "cancel", "id": cid,
                            "target": rid})
        self.h.client.wait(cid, 2)
        r = self.h.client.wait(rid, 2)
        self.assertEqual(r["error"]["code"], "E_CANCELED")

    # 17
    def test_17_lease_expiry_not_renewed(self):
        self.h = Harness()
        fd = self.h.open()
        r = self.h.client.lease(fd, ttl_ms=50)
        self.assertTrue(r.get("ok"), r)
        time.sleep(0.1)
        r2 = self.h.client.call("write", {"fd": fd, "frame": {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}}})
        self.assertEqual(r2["error"]["code"], "E_BUSY")

    # 18
    def test_18_disconnect_releases_lease(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        self.h.client.close()
        self.h.client = None
        time.sleep(0.2)
        c2 = self.h.new_client("after-disconnect")
        try:
            r = c2.open(DEVICE_ID, "exclusive")
            self.assertTrue(r.get("ok"), r)
        finally:
            c2.close()

    # 19
    def test_19_oversize_frame_keeps_connection(self):
        self.h = Harness(start_client=False)
        s = raw_connect(self.h.cbap_sock)
        raw_send(s, hello_msg(token=self.h.server.token))
        self.assertEqual(raw_recv(s)["type"], "welcome")
        s.sendall(b"x" * (protocol.MAX_FRAME + 1024) + b"\n")
        msg = raw_recv(s)
        self.assertEqual(msg["error"]["code"], "E_FRAME")
        s.sendall(protocol.encode({"v": "1.0", "type": "ping", "id": "p1"}))
        msg = raw_recv(s)
        self.assertEqual(msg["type"], "pong")
        s.close()

    # 21
    def test_21_event_seq_increases(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        for text in ("a", "b"):
            _, _, r = self.h.client.write(fd, {
                "channel": "chat", "op": "say", "args": {"text": text}})
            self.assertTrue(r.get("ok"), r)
            time.sleep(0.1)
        events = self.h.client.poll(timeout_ms=1000)["payload"]["events"]
        seqs = [e.get("seq") for e in events if e.get("kind") == "chat"]
        self.assertGreaterEqual(len(seqs), 2, events)
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))

    # 22
    def test_22_poll_filters_and_feature_negotiation(self):
        self.h = Harness()
        c = self.h.new_client("filtered", operator=True,
                              features=["poll_filter"])
        self.assertIn("poll_filter", c.welcome.get("features", []))
        fd = self.h.open(c)
        c.lease(fd)
        _, _, r = c.write(fd, {"channel": "chat", "op": "say",
                               "args": {"text": "filtered"}})
        self.assertTrue(r.get("ok"), r)
        events = c.poll(timeout_ms=1000, fds=[fd], events=["chat"])["payload"]["events"]
        self.assertTrue(events, events)
        self.assertTrue(all(e.get("kind") == "chat" for e in events), events)
        self.assertTrue(all(fd in (e.get("fds") or []) for e in events), events)
        r = c.poll(timeout_ms=0, fds=["fd-does-not-exist"])
        self.assertEqual(r.get("error", {}).get("code"), "E_NOENT")
        c.close()
        plain = self.h.new_client("no-filter-feature", operator=True, features=[])
        fd2 = self.h.open(plain)
        r = plain.poll(timeout_ms=0, fds=[fd2])
        self.assertEqual(r.get("error", {}).get("code"), "E_NOTSUP")
        plain.close()

    # 20 + D1/D4/D5
    def test_20_driver_safety_and_health(self):
        self.h = Harness()
        fd = self.h.open()
        st = self.h.client.stat(fd)
        self.assertTrue(st["payload"]["health"]["ok"], st)
        self.h.client.lease(fd)
        self.assertTrue(self.h.client.estop(fd).get("ok"))
        r = self.h.client.call("write", {"fd": fd, "frame": {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}}})
        self.assertEqual(r["error"]["code"], "E_SAFETY")

    def test_d1_missing_estop_rejected(self):
        d = NoStateDriver()
        d.device["safety"].pop("estop", None)
        with self.assertRaises(ValueError):
            KernelServer(d, socket_path=os.path.join(tempfile.mkdtemp(), "x.sock"))

    def test_d4_unhealthy_driver_refuses_lease(self):
        self.h = Harness(driver=NoStateDriver(health_ok=False), start_client=True)
        fd = self.h.open()
        r = self.h.client.lease(fd)
        self.assertEqual(r["error"]["code"], "E_SAFETY")

    def test_d5_driver_crash_marks_offline(self):
        self.h = Harness()
        fd = self.h.open()
        self.h.client.lease(fd)
        self.h.hand.stop()
        time.sleep(1.2)
        st = self.h.client.stat(fd)
        self.assertFalse(st["payload"]["health"]["ok"], st)


if __name__ == "__main__":
    unittest.main()
