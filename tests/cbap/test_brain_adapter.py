#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test the legacy `接线口`-shaped adapter over CBAP."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

from drivers.mc.driver import McDriver
from kernel.legacy_runtime.brain_adapter import CBAPHandAdapter
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.fake_hand import FakeHand

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEVICE = os.path.join(ROOT, "drivers", "mc", "device.json")
MAPPING = os.path.join(ROOT, "drivers", "mc", "mapping.json")
DEVICE_ID = "mc://bot/DeepSeek"


class BrainAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="cbap-adapter-")
        self.hand_sock = os.path.join(self.tmp, "hand.sock")
        self.cbap_sock = os.path.join(self.tmp, "cbap.sock")
        self.hand = FakeHand(self.hand_sock)
        self.hand.start()
        self.driver = McDriver(socket_path=self.hand_sock,
                               device_path=DEVICE,
                               mapping_path=MAPPING)
        self.driver.connect()
        self.server = KernelServer(self.driver, socket_path=self.cbap_sock,
                                   audit_path=os.path.join(self.tmp, "audit.jsonl"))
        self.assertTrue(self.server.start())
        self.adapter = CBAPHandAdapter(
            cfg={"bot_name": "Fake"}, cbap_socket=self.cbap_sock,
            device_id=DEVICE_ID, mapping_path=MAPPING)
        self.assertTrue(self.adapter.连(重试=2))

    def tearDown(self) -> None:
        try:
            self.adapter.断()
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

    def _collect(self, timeout: float = 3.0) -> list[dict]:
        out: list[dict] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msgs, disconnected = self.adapter.收()
            out.extend(msgs)
            if any(m.get("kind") == "cmdResult" for m in msgs):
                return out
            if disconnected:
                return out
            time.sleep(0.02)
        return out

    def test_move_dig_say(self) -> None:
        self.assertTrue(self.adapter.发({"cmd": "move", "dir": [1, 0], "ms": 100}))
        msgs = self._collect()
        results = [m for m in msgs if m.get("kind") == "cmdResult"]
        self.assertTrue(results and results[-1]["ok"], results)
        self.assertEqual(results[-1]["cmd"], "move")

        self.assertTrue(self.adapter.发({"cmd": "dig", "p": [1, 2, 3]}))
        msgs = self._collect()
        results = [m for m in msgs if m.get("kind") == "cmdResult"]
        self.assertTrue(results and results[-1]["ok"], results)
        self.assertEqual(results[-1]["cmd"], "dig")

        self.assertTrue(self.adapter.发({"cmd": "say", "text": "hi"}))
        msgs = self._collect()
        deadline = time.monotonic() + 1.0
        while not any(m.get("kind") == "chat" for m in msgs) \
                and time.monotonic() < deadline:
            more, _ = self.adapter.收()
            msgs.extend(more)
            time.sleep(0.02)
        self.assertTrue(any(m.get("kind") == "chat" for m in msgs), msgs)
        results = [m for m in msgs if m.get("kind") == "cmdResult"]
        self.assertTrue(results and results[-1]["ok"], results)

    def test_scan_and_watch(self) -> None:
        self.assertTrue(self.adapter.发({"cmd": "scan_environment",
                                         "半径": 12, "步长": 2}))
        msgs = self._collect()
        results = [m for m in msgs if m.get("kind") == "cmdResult"]
        self.assertTrue(results and results[-1]["ok"], results)
        self.assertEqual(results[-1]["cmd"], "scan_environment")

        self.assertTrue(self.adapter.发({"cmd": "watch_blocks",
                                         "list": [[1, 2, 3]]}))
        msgs = self._collect()
        results = [m for m in msgs if m.get("kind") == "cmdResult"]
        self.assertTrue(results and results[-1]["ok"], results)
        self.assertEqual(results[-1]["cmd"], "watch_blocks")

    def test_unsupported_fails_closed(self) -> None:
        self.assertFalse(self.adapter.发({"cmd": "furnace_watch"}))
        msgs, _ = self.adapter.收()
        results = [m for m in msgs if m.get("kind") == "cmdResult"]
        self.assertTrue(results, msgs)
        self.assertFalse(results[0]["ok"])
        self.assertIn("不支持", results[0]["why"])


if __name__ == "__main__":
    unittest.main()
