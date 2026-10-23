#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP data contract: device descriptor and MC mapping must agree."""

from __future__ import annotations

import json
import os
import unittest

from drivers.mc.driver import McDriver
from drivers.dataflow.driver import DataFlowDriver

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEVICE = os.path.join(ROOT, "drivers", "mc", "device.json")
MAPPING = os.path.join(ROOT, "drivers", "mc", "mapping.json")
FLOW_DEVICE = os.path.join(ROOT, "drivers", "dataflow", "device.json")
FLOW_MAPPING = os.path.join(ROOT, "drivers", "dataflow", "mapping.json")
MCP_DEVICE = os.path.join(ROOT, "drivers", "mcp", "device.json")
MCP_MAPPING = os.path.join(ROOT, "drivers", "mcp", "mapping.json")

EXPECTED_OPS = {
    "move", "jump", "jumpattack", "sneak", "swimdown", "eat",
    "attack", "goto", "stop", "dig", "place", "use", "collect",
    "chest_take", "chest_put", "chest_audit", "furnace_put",
    "furnace_take", "give", "craft", "say",
}
KNOWN_TYPES = {"vec2", "vec3", "int", "float", "bool", "string",
               "inventory_item", "block", "entity", "object"}


class DataContractTest(unittest.TestCase):
    def setUp(self) -> None:
        with open(DEVICE, encoding="utf-8") as f:
            self.device = json.load(f)
        with open(MAPPING, encoding="utf-8") as f:
            self.mapping = json.load(f)
        self.driver = McDriver(device_path=DEVICE, mapping_path=MAPPING,
                               connect_timeout=0.1, reconnect=False)

    def test_mapping_matches_device_channels(self) -> None:
        channels = self.device.get("channels") or {}
        for op, spec in self.mapping["ops"].items():
            with self.subTest(op=op):
                ch = spec["channel"]
                self.assertIn(ch, channels, f"{op}: missing channel {ch}")
                writes = channels[ch].get("write") or []
                self.assertIn(op, writes,
                              f"{op}: not declared in {ch}.write")
                self.assertIsInstance(spec.get("op"), str)
                self.assertTrue(spec["op"])

    def test_expected_surface_is_complete(self) -> None:
        self.assertEqual(set(self.mapping["ops"]), EXPECTED_OPS)
        for ch in ("body", "world", "inventory", "chat"):
            self.assertIn(ch, self.device["channels"])

    def test_arg_types_known(self) -> None:
        for op, spec in self.mapping["ops"].items():
            for arg, typ in (spec.get("args") or {}).items():
                name = arg.lstrip("?")
                self.assertTrue(name)
                self.assertIn(typ, KNOWN_TYPES, f"{op}.{arg}: unknown type {typ}")

    def test_driver_maps_legacy_dialect(self) -> None:
        cases = [
            ({"channel": "body", "op": "move",
              "args": {"dir": [1, 0], "ms": 100}},
             {"cmd": "move", "dir": [1.0, 0.0], "ms": 100}),
            ({"channel": "world", "op": "collect",
              "args": {"item": "oak_log", "block": "oak_log", "count": 3}},
             {"cmd": "collect", "物品": "oak_log", "方块": "oak_log", "数量": 3}),
            ({"channel": "world", "op": "chest_take",
              "args": {"p": [1, 2, 3], "item": "oak_log", "count": 2}},
             {"cmd": "chest_take", "p": [1.0, 2.0, 3.0], "物品": "oak_log", "数量": 2}),
            ({"channel": "world", "op": "chest_put",
              "args": {"p": [1, 2, 3], "item": "oak_log", "count": 2}},
             {"cmd": "chest_put", "p": [1.0, 2.0, 3.0], "物品": "oak_log", "数量": 2}),
            ({"channel": "world", "op": "furnace_put",
              "args": {"p": [1, 2, 3], "input": {"name": "iron_ore", "count": 1},
                       "fuel": {"name": "coal", "count": 1}}},
             {"cmd": "furnace_put", "p": [1.0, 2.0, 3.0],
              "输入": {"name": "iron_ore", "count": 1},
              "燃料": {"name": "coal", "count": 1}}),
            ({"channel": "world", "op": "give",
              "args": {"item": "stick", "count": 1, "to": "mintstar"}},
             {"cmd": "递", "物品": "stick", "数量": 1, "谁": "mintstar"}),
            ({"channel": "body", "op": "stop", "args": {}},
             {"cmd": "stop"}),
        ]
        for frame, expected in cases:
            with self.subTest(op=frame["op"]):
                self.assertEqual(self.driver.map_action(frame), expected)

    def test_legacy_hand_concurrency_is_honest(self) -> None:
        self.assertEqual(self.device["limits"]["max_inflight"], 1)

    def test_dataflow_mapping_matches_channels(self) -> None:
        with open(FLOW_DEVICE, encoding="utf-8") as f:
            dev = json.load(f)
        with open(FLOW_MAPPING, encoding="utf-8") as f:
            mp = json.load(f)
        self.assertEqual(dev["device_id"], mp["device_id"])
        for op, spec in mp["ops"].items():
            with self.subTest(op=op):
                ch = spec["channel"]
                self.assertIn(ch, dev["channels"])
                self.assertIn(op, dev["channels"][ch].get("write") or [])
        self.assertEqual(set(mp["ops"]), EXPECTED_OPS - {"jumpattack"})

    def test_mcp_mapping_matches_channels(self) -> None:
        with open(MCP_DEVICE, encoding="utf-8") as f:
            dev = json.load(f)
        with open(MCP_MAPPING, encoding="utf-8") as f:
            mp = json.load(f)
        self.assertEqual(dev["device_id"], mp["device_id"])
        for op, spec in mp["ops"].items():
            with self.subTest(op=op):
                ch = spec["channel"]
                self.assertIn(ch, dev["channels"])
                self.assertIn(op, dev["channels"][ch].get("write") or [])
        self.assertEqual(set(mp["ops"]),
                         {"move", "goto", "dig", "place", "attack",
                          "use", "craft", "say"})

    def test_dataflow_driver_maps_generic_args(self) -> None:
        d = DataFlowDriver("/tmp/does-not-exist.sock",
                           device_path=FLOW_DEVICE,
                           mapping_path=FLOW_MAPPING,
                           device_id="mcflow://agent/test")
        got = d.map_action({"channel": "world", "op": "collect",
                            "args": {"item": "oak_log", "block": "oak_log",
                                     "count": 3}})
        self.assertEqual(got["cmd"], "collect")
        self.assertEqual(got["args"], {"item": "oak_log", "block": "oak_log",
                                      "count": 3})


if __name__ == "__main__":
    unittest.main()
