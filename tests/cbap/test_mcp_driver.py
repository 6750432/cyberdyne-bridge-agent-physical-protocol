#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP driver tests against a minimal stdio MCP server."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import time
import unittest

MCPDriver = importlib.import_module(
    "agents.mcp-mineflayer.driver.driver").MCPDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAKE = os.path.join(ROOT, "tests", "cbap", "fake_mcp_server.py")


class MCPDriverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-mcp-")
        self.driver = MCPDriver(
            command=[sys.executable, FAKE], cwd=ROOT,
            connect_timeout=15.0, poll_interval=0.2,
        )
        self.driver.connect()
        self.kernel = KernelServer(
            drivers=[self.driver], socket_path=os.path.join(self.tmp, "cbap.sock"),
            audit_path=os.path.join(self.tmp, "audit"))
        if not self.kernel.start():
            raise RuntimeError("kernel did not start")
        self.client = CBAPClient(os.path.join(self.tmp, "cbap.sock"),
                                 agent_id="mcp-test")
        self.client.connect()
        self.client.hello(operator_token=open(os.path.join(self.tmp, "cbap.sock") + ".operator", encoding="ascii").read().strip())
        r = self.client.open("mcp://mc/MCPBody")
        self.assertTrue(r.get("ok"), r)
        self.fd = r["payload"]["fd"]

    def tearDown(self):
        try:
            self.client.close()
        except Exception:
            pass
        try:
            self.kernel.stop()
        except Exception:
            pass
        try:
            self.driver.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_device_and_real_state(self):
        d = self.client.device_list()["payload"]["devices"]
        self.assertEqual(d[0]["device_id"], "mcp://mc/MCPBody")
        r = self.client.read(self.fd, "body", 3000)
        self.assertTrue(r.get("ok"), r)
        body = r["payload"]["frame"]["body"]
        self.assertEqual(body["pos"], [10.0, 64.0, 10.0])
        self.assertEqual(body["hp"], 20)

    def test_move_and_chat_are_real_tool_calls(self):
        self.client.lease(self.fd)
        _, _, a = self.client.write(self.fd, {
            "channel": "body", "op": "move",
            "args": {"dir": [2, 0], "ms": 100}}, deadline_ms=10000)
        self.assertTrue(a.get("ok"), a)
        self.assertEqual(self.driver.wait_state(1)["pos"], [12.0, 64.0, 10.0])
        _, _, b = self.client.write(self.fd, {
            "channel": "chat", "op": "say",
            "args": {"text": "mcp test"}}, deadline_ms=10000)
        self.assertTrue(b.get("ok"), b)
        self.assertIn("chat", [h["tool"] for h in self.driver.stats["tool_history"]])

    def test_read_exposes_blocks_and_chat_channels(self):
        r = self.client.read(self.fd, "world", 3000)
        self.assertTrue(r.get("ok"), r)
        self.assertIn("blocks", r["payload"]["frame"]["world"])
        self.assertIn("chat", r["payload"]["frame"]["world"])

    def test_dig_uses_floor_offsets(self):
        self.driver._latest_state = {"pos": [10.5, 64.9, 10.2]}
        out = self.driver.map_action({
            "channel": "world", "op": "dig",
            "args": {"p": [12, 66, 10]}})
        self.assertEqual(out["tool"], "dig")
        self.assertEqual(out["args"], {"dx": 2, "dy": 2, "dz": 0})

    def test_equip_and_place_map_to_inventory_tool(self):
        eq = self.driver.map_action({
            "channel": "inventory", "op": "equip",
            "args": {"name": "crafting_table"}})
        self.assertEqual(eq["tool"], "inventory")
        self.assertEqual(eq["args"], {"action": "equip",
                                      "name": "crafting_table",
                                      "destination": "hand"})
        self.driver._latest_state = {"pos": [10.5, 64.9, 10.2]}
        pl = self.driver.map_action({
            "channel": "world", "op": "place",
            "args": {"p": [12, 64, 10], "item": "furnace"}})
        self.assertEqual(pl["tool"], "place")
        self.assertEqual(pl["args"], {"dx": 2, "dy": 0, "dz": 0,
                                      "itemName": "furnace"})

    def test_estop_terminates_mcp_process(self):
        self.client.lease(self.fd)
        r = self.client.estop(self.fd, reason="test")
        self.assertTrue(r.get("ok"), r)
        self.assertFalse(self.driver.connected)
        r2 = self.client.call("write", {"fd": self.fd, "frame": {
            "channel": "chat", "op": "say", "args": {"text": "blocked"}}})
        self.assertEqual(r2["error"]["code"], "E_SAFETY")


if __name__ == "__main__":
    unittest.main()
