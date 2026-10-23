#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One kernel, two peripherals: legacy MC hand + external data-flow MC agent."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest

from drivers.dataflow.driver import DataFlowDriver
from drivers.mc.driver import McDriver
from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.fake_dataflow_agent import FakeDataFlowAgent
from tests.cbap.fake_hand import FakeHand

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_DEVICE = os.path.join(ROOT, "drivers", "mc", "device.json")
LEGACY_MAPPING = os.path.join(ROOT, "drivers", "mc", "mapping.json")
FLOW_DEVICE = os.path.join(ROOT, "drivers", "dataflow", "device.json")
FLOW_MAPPING = os.path.join(ROOT, "drivers", "dataflow", "mapping.json")


class MultiDeviceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-multi-")
        self.legacy_sock = os.path.join(self.tmp, "legacy.sock")
        self.flow_sock = os.path.join(self.tmp, "flow.sock")
        self.cbap_sock = os.path.join(self.tmp, "cbap.sock")

        self.legacy_hand = FakeHand(self.legacy_sock)
        self.legacy_hand.start()
        self.legacy = McDriver(self.legacy_sock, LEGACY_DEVICE, LEGACY_MAPPING)
        self.legacy.connect()

        self.flow_agent = FakeDataFlowAgent(self.flow_sock, name="flow-test")
        self.flow_agent.start()
        self.flow_dev_path = os.path.join(self.tmp, "flow-device.json")
        self.flow_map_path = os.path.join(self.tmp, "flow-mapping.json")
        dev = json.load(open(FLOW_DEVICE, encoding="utf-8"))
        dev["device_id"] = "mcflow://agent/flow-test"
        json.dump(dev, open(self.flow_dev_path, "w", encoding="utf-8"),
                  ensure_ascii=False)
        mp = json.load(open(FLOW_MAPPING, encoding="utf-8"))
        mp["device_id"] = "mcflow://agent/flow-test"
        json.dump(mp, open(self.flow_map_path, "w", encoding="utf-8"),
                  ensure_ascii=False)
        self.flow = DataFlowDriver(self.flow_sock, self.flow_dev_path,
                                   self.flow_map_path,
                                   device_id="mcflow://agent/flow-test")
        self.flow.connect()

        self.kernel = KernelServer(drivers=[self.legacy, self.flow],
                                   socket_path=self.cbap_sock,
                                   audit_path=os.path.join(self.tmp, "audit"))
        if not self.kernel.start():
            raise RuntimeError("kernel did not start")
        self.client = CBAPClient(self.cbap_sock, agent_id="multi")
        self.client.connect()
        self.client.hello()

    def tearDown(self):
        for x in (self.client,):
            try:
                x.close()
            except Exception:
                pass
        for x in (self.kernel, self.flow, self.legacy,
                  self.flow_agent, self.legacy_hand):
            try:
                x.stop() if hasattr(x, "stop") else x.close()
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def open(self, device_id):
        r = self.client.open(device_id)
        self.assertTrue(r.get("ok"), r)
        return r["payload"]["fd"]

    def test_two_devices_are_visible(self):
        r = self.client.device_list()
        ids = {d["device_id"] for d in r["payload"]["devices"]}
        self.assertEqual(ids, {"mc://bot/DeepSeek",
                               "mcflow://agent/flow-test"})

    def test_read_and_write_each_device(self):
        legacy_fd = self.open("mc://bot/DeepSeek")
        flow_fd = self.open("mcflow://agent/flow-test")
        self.assertTrue(self.client.read(legacy_fd, "body", 1000).get("ok"))
        fr = self.client.read(flow_fd, "body", 1000)
        self.assertTrue(fr.get("ok"), fr)
        self.assertEqual(fr["payload"]["frame"]["body"]["pos"][0], 100.0)

        self.assertTrue(self.client.lease(legacy_fd).get("ok"))
        self.assertTrue(self.client.lease(flow_fd).get("ok"))
        _, _, r1 = self.client.write(legacy_fd, {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}})
        _, _, r2 = self.client.write(flow_fd, {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 100}})
        self.assertTrue(r1.get("ok"), r1)
        self.assertTrue(r2.get("ok"), r2)
        self.assertEqual(self.flow_agent.pos[0], 100.1)

    def test_lease_is_per_device(self):
        legacy_fd = self.open("mc://bot/DeepSeek")
        flow_fd = self.open("mcflow://agent/flow-test")
        self.assertTrue(self.client.lease(legacy_fd).get("ok"))
        # dataflow device has no lease yet: write must be refused, even though
        # the legacy device is leased.
        r = self.client.call("write", {"fd": flow_fd, "frame": {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}}})
        self.assertEqual(r["error"]["code"], "E_BUSY")
        self.assertTrue(self.client.lease(flow_fd).get("ok"))
        _, _, ok = self.client.write(flow_fd, {
            "channel": "body", "op": "move",
            "args": {"dir": [1, 0], "ms": 10}})
        self.assertTrue(ok.get("ok"), ok)

    def test_dataflow_event_reaches_poll(self):
        fd = self.open("mcflow://agent/flow-test")
        self.client.lease(fd)
        _, _, r = self.client.write(fd, {
            "channel": "chat", "op": "say", "args": {"text": "hello-flow"}})
        self.assertTrue(r.get("ok"), r)
        time.sleep(0.1)
        p = self.client.poll(timeout_ms=500)
        kinds = [e.get("kind") for e in p.get("payload", {}).get("events", [])]
        self.assertIn("chat", kinds)


if __name__ == "__main__":
    unittest.main()
