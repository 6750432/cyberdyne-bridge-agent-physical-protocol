#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MC Body API v0 SDK tests against a protocol-compatible fake body."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from body.fake_body import FakeBody
from sdk.python.mc_body_client import MCBodyClient, MCBodyError


class MCBodySDKTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mc-body-")
        self.sock = Path(self.tmp.name) / "body.sock"
        self.body = FakeBody(self.sock).start()
        self.client = MCBodyClient(self.sock, client="test")
        self.welcome = self.client.connect()

    def tearDown(self):
        self.client.close()
        self.body.stop()
        self.tmp.cleanup()

    def test_welcome_and_state(self):
        self.assertEqual(self.welcome["mc_version"], "1.21.1")
        self.assertIn("goto", self.welcome["capabilities"])
        s = self.client.state()
        self.assertIn("pos", s["body"])
        self.assertGreaterEqual(s["seq"], 1)

    def test_goto_facts(self):
        res = self.client.goto(10, 64, -3)
        self.assertTrue(res["ok"])
        self.assertEqual(res["facts"]["position"], [10.0, 64.0, -3.0])
        self.assertEqual(self.client.state()["body"]["pos"], [10.0, 64.0, -3.0])

    def test_collect_and_craft(self):
        self.client.collect("oak_log", 3)
        self.client.craft("stone_pickaxe", 1)
        s = self.client.state()
        self.assertEqual(s["body"]["inventory"]["oak_log"], 3)
        self.assertEqual(s["body"]["inventory"]["stone_pickaxe"], 1)

    def test_unknown_command_raises_typed_error(self):
        with self.assertRaises(MCBodyError) as cm:
            self.client.command("nope", {})
        self.assertEqual(cm.exception.code, "E_NOTSUP")

    def test_stop(self):
        res = self.client.stop()
        self.assertTrue(res["ok"])
        self.assertTrue(res["facts"]["ok"])


if __name__ == "__main__":
    unittest.main()
