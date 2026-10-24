#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end tests for the CBAP v1 gateway + MC driver + fake hand."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import unittest

from drivers.mc.driver import McDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.fake_hand import FakeHand

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEVICE = os.path.join(ROOT, "drivers", "mc", "device.json")
MAPPING = os.path.join(ROOT, "drivers", "mc", "mapping.json")
DEVICE_ID = "mc://bot/DeepSeek"


class GatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="cbap-test-")
        self.hand_sock = os.path.join(self.tmp, "hand.sock")
        self.cbap_sock = os.path.join(self.tmp, "cbap.sock")
        self.audit = os.path.join(self.tmp, "audit.jsonl")

        self.hand = FakeHand(self.hand_sock)
        self.hand.start()
        self.driver = McDriver(socket_path=self.hand_sock,
                               device_path=DEVICE,
                               mapping_path=MAPPING)
        self.driver.connect()
        self.server = KernelServer(self.driver, socket_path=self.cbap_sock,
                                   audit_path=self.audit)
        self.assertTrue(self.server.start())

        self.client = CBAPClient(self.cbap_sock, agent_id="test-agent")
        self.client.connect()
        self.welcome = self.client.hello(operator_token=open(self.cbap_sock + ".operator", encoding="ascii").read().strip())

    def tearDown(self) -> None:
        try:
            self.client.close()
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
            self.hand.stop()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _open(self, mode: str = "rw") -> str:
        r = self.client.open(DEVICE_ID, mode)
        self.assertTrue(r.get("ok"), r)
        return r["payload"]["fd"]

    def test_hello_and_device_list(self) -> None:
        self.assertEqual(self.welcome.get("type"), "welcome")
        self.assertEqual(self.welcome.get("protocol"), "1.0")
        r = self.client.device_list()
        self.assertTrue(r.get("ok"), r)
        devices = r["payload"]["devices"]
        self.assertEqual(devices[0]["device_id"], DEVICE_ID)

    def test_open_read(self) -> None:
        fd = self._open()
        r = self.client.read(fd, channel="body", timeout_ms=1000)
        self.assertTrue(r.get("ok"), r)
        body = r["payload"]["frame"]["body"]
        self.assertIn("pos", body)
        self.assertEqual(body["hp"], 20.0)

    def test_write_requires_lease(self) -> None:
        fd = self._open()
        r = self.client.call("write", {
            "fd": fd,
            "frame": {"channel": "body", "op": "move",
                      "args": {"dir": [1, 0], "ms": 100}},
        })
        self.assertFalse(r.get("ok"), r)
        self.assertEqual(r["error"]["code"], "E_BUSY")

    def test_lease_and_move(self) -> None:
        fd = self._open()
        lease = self.client.lease(fd, ttl_ms=30000)
        self.assertTrue(lease.get("ok"), lease)
        rid, ack, result = self.client.write(
            fd,
            {"channel": "body", "op": "move",
             "args": {"dir": [1, 0], "ms": 100}},
            deadline_ms=3000,
        )
        self.assertEqual(ack.get("state"), "accepted", ack)
        self.assertTrue(result.get("ok"), result)
        self.assertTrue(any(c.get("cmd") == "move" for c in self.hand.commands))
        time.sleep(0.15)
        r = self.client.read(fd, channel="body", timeout_ms=1000)
        self.assertTrue(r.get("ok"), r)
        self.assertGreater(r["payload"]["frame"]["body"]["pos"][0], 0.0)

    def test_fair_lease_wait_and_release(self) -> None:
        fd1 = self._open()
        c2 = CBAPClient(self.cbap_sock, agent_id="waiter")
        c2.connect(); c2.hello(operator_token=open(self.cbap_sock + ".operator", encoding="ascii").read().strip())
        try:
            r2 = c2.open(DEVICE_ID)
            self.assertTrue(r2.get("ok"), r2)
            fd2 = r2["payload"]["fd"]
            self.assertTrue(self.client.lease(fd1).get("ok"))
            got = {}

            def wait_lease():
                got["r"] = c2.lease(fd2, ttl_ms=30000, wait_ms=3000, timeout=8)

            t = threading.Thread(target=wait_lease, daemon=True)
            t.start()
            time.sleep(0.2)
            self.assertTrue(self.client.release(fd1).get("payload", {}).get("released"))
            t.join(timeout=5)
            self.assertFalse(t.is_alive(), "waiter did not wake")
            self.assertTrue(got.get("r", {}).get("ok"), got)
            old = self.client.call("write", {"fd": fd1, "frame": {
                "channel": "chat", "op": "say", "args": {"text": "stale"}}})
            self.assertEqual(old["error"]["code"], "E_BUSY")
            _, _, res = c2.write(fd2, {
                "channel": "chat", "op": "say",
                "args": {"text": "new owner"}}, deadline_ms=3000)
            self.assertTrue(res.get("ok"), res)
            self.assertTrue(c2.release(fd2).get("payload", {}).get("released"))
        finally:
            c2.close()

    def test_chat_event_poll(self) -> None:
        fd = self._open()
        self.client.lease(fd)
        rid, ack, result = self.client.write(
            fd,
            {"channel": "chat", "op": "say", "args": {"text": "hello"}},
            deadline_ms=3000,
        )
        self.assertTrue(result.get("ok"), result)
        polled = self.client.poll(timeout_ms=1000)
        self.assertTrue(polled.get("ok"), polled)
        kinds = [e.get("kind") for e in polled["payload"]["events"]]
        self.assertIn("chat", kinds)

    def test_estop_blocks_write(self) -> None:
        fd = self._open()
        self.client.lease(fd)
        r = self.client.estop(fd, reason="test")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r["payload"]["safe_state"], "idle")
        r = self.client.call("write", {
            "fd": fd,
            "frame": {"channel": "body", "op": "move",
                      "args": {"dir": [1, 0], "ms": 100}},
        })
        self.assertFalse(r.get("ok"), r)
        self.assertEqual(r["error"]["code"], "E_SAFETY")

    def test_extended_device_ops(self) -> None:
        fd = self._open()
        self.client.lease(fd)
        frames = [
            {"channel": "world", "op": "collect",
             "args": {"item": "oak_log", "block": "oak_log", "count": 2}},
            {"channel": "world", "op": "chest_take",
             "args": {"p": [1, 64, 1], "item": "oak_log", "count": 1}},
            {"channel": "world", "op": "chest_put",
             "args": {"p": [1, 64, 1], "item": "oak_log", "count": 1}},
            {"channel": "world", "op": "chest_audit",
             "args": {"p": [1, 64, 1]}},
            {"channel": "world", "op": "furnace_put",
             "args": {"p": [1, 64, 1],
                      "input": {"name": "iron_ore", "count": 1},
                      "fuel": {"name": "coal", "count": 1}}},
            {"channel": "world", "op": "furnace_take",
             "args": {"p": [1, 64, 1], "item": "iron_ingot", "count": 1}},
            {"channel": "world", "op": "give",
             "args": {"item": "stick", "count": 1, "to": "mintstar"}},
            {"channel": "body", "op": "jump", "args": {"count": 1}},
            {"channel": "body", "op": "sneak", "args": {"ms": 10}},
            {"channel": "body", "op": "eat", "args": {}},
        ]
        for frame in frames:
            with self.subTest(op=frame["op"]):
                rid, ack, result = self.client.write(fd, frame, deadline_ms=3000)
                self.assertEqual(ack.get("state"), "accepted", ack)
                self.assertEqual(result.get("id"), rid, result)
                self.assertTrue(result.get("ok"), result)
        cmds = [c.get("cmd") for c in self.hand.commands]
        for expected in ("collect", "chest_take", "chest_put", "chest_audit",
                         "furnace_put", "furnace_take", "递", "jump", "sneak", "eat"):
            self.assertIn(expected, cmds)
        self.assertEqual(self.hand.chest.get("oak_log"), 5)
        self.assertEqual(self.hand.items.get("oak_log"), 3)

    def test_ioctl_watch_items_and_furnace(self) -> None:
        fd = self._open()
        for request, args in (
            ("watch_items", {"items": ["*"]}),
            ("furnace_watch", {"p": [1, 64, 1], "每_ms": 500}),
        ):
            with self.subTest(request=request):
                rid = self.client.request("ioctl",
                                          {"fd": fd, "request": request,
                                           "args": args})
                ack = self.client.wait_ack(rid)
                self.assertEqual(ack.get("state"), "accepted")
                result = self.client.wait(rid)
                self.assertTrue(result.get("ok"), result)
        cmds = [c.get("cmd") for c in self.hand.commands]
        self.assertIn("watch_items", cmds)
        self.assertIn("furnace_watch", cmds)

    def test_unknown_op(self) -> None:
        r = self.client.call("nope", {})
        self.assertFalse(r.get("ok"), r)
        self.assertEqual(r["error"]["code"], "E_NOTSUP")

    def test_open_unknown_device(self) -> None:
        r = self.client.open("mc://nope", "r")
        self.assertFalse(r.get("ok"), r)
        self.assertEqual(r["error"]["code"], "E_NOENT")


if __name__ == "__main__":
    unittest.main()
