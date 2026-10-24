#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic MCP device driver tests: facts, not tool receipts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from drivers.mcp_device.driver import MCPDeviceDriver

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "tests/cbap/fake_mcp_hardware.py"


class MCPDeviceDriverTest(unittest.TestCase):
    def _manifest(self, device: str = "light", liar: bool = False) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="mcp-device-"))
        command = [sys.executable, str(FAKE), "--device", device]
        if liar:
            command.append("--liar")
        manifest = {
            "device_id": f"mcp://lab/{device}-01" + ("-liar" if liar else ""),
            "display_name": f"Fake {device}",
            "transport": {
                "type": "stdio",
                "command": command,
                "cwd": str(ROOT),
            },
            "tools": ({"read_temperature": {"tool": "read_temperature"}}
                      if device == "sensor" else {
                          "turn_on": {"tool": "turn_on"},
                          "turn_off": {"tool": "turn_off"},
                      }),
            "facts": {"source": "tool", "tool": "get_state"},
            "estop": ({"tool": "turn_off"} if device == "light" else {}),
            "poll_interval": 0.05,
        }
        path = tmp / "device.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_honest_action_is_verified_by_facts(self):
        driver = MCPDeviceDriver(self._manifest())
        try:
            self.assertTrue(driver.connect())
            self.assertTrue(driver.send({
                "op": "turn_on", "expect": {"on": True},
            }))
            self.assertEqual(driver.latest_state["on"], True)
            self.assertEqual(driver.last_verification()["status"], "verified")
            self.assertTrue(driver.estop())
            self.assertEqual(driver.latest_state["on"], False)
        finally:
            driver.close()

    def test_liar_tool_is_detected(self):
        driver = MCPDeviceDriver(self._manifest(liar=True))
        try:
            self.assertTrue(driver.connect())
            # The tool says ok, but get_state still says off: reject.
            self.assertFalse(driver.send({
                "op": "turn_on", "expect": {"on": True},
            }))
            self.assertEqual(driver.latest_state["on"], False)
            self.assertEqual(driver.last_verification()["status"], "mismatch")
        finally:
            driver.close()

    def test_read_only_sensor_facts(self):
        driver = MCPDeviceDriver(self._manifest(device="sensor"))
        try:
            self.assertTrue(driver.connect())
            facts = driver.verify({"temp_c": 23.5})
            self.assertTrue(facts["ok"], facts)
            self.assertEqual(facts["status"], "verified")
        finally:
            driver.close()

    def test_missing_facts_source_is_unverifiable(self):
        driver = MCPDeviceDriver(self._manifest())
        try:
            driver.facts_spec = {}
            driver.connected = True
            result = driver.verify({"on": True})
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "unverifiable")
        finally:
            driver.close()


    def test_kernel_write_and_generic_state_read(self):
        from kernel.legacy_runtime.client import CBAPClient
        from kernel.legacy_runtime.server import KernelServer

        driver = MCPDeviceDriver(self._manifest())
        socket_dir = Path(tempfile.mkdtemp(prefix="mcp-kernel-"))
        sock = socket_dir / "cbap.sock"
        try:
            self.assertTrue(driver.connect())
            kernel = KernelServer(
                drivers=[driver], socket_path=str(sock),
                audit_path=str(socket_dir / "audit"),
            )
            self.assertTrue(kernel.start())
            client = CBAPClient(str(sock), agent_id="mcp-device-test")
            client.connect()
            client.hello()
            opened = client.open("mcp://lab/light-01")
            self.assertTrue(opened["ok"], opened)
            fd = opened["payload"]["fd"]
            client.lease(fd)
            _rid, ack, wr = client.write(fd, {
                "channel": "mcp", "op": "turn_on", "args": {},
                "expect": {"on": True},
            })
            self.assertEqual(ack.get("state"), "accepted")
            self.assertTrue(wr["ok"], wr)
            rd = client.read(fd, "state", timeout_ms=1000)
            self.assertTrue(rd["ok"], rd)
            self.assertTrue(rd["payload"]["frame"]["state"]["on"])
            client.close()
            kernel.stop()
        finally:
            driver.close()


if __name__ == "__main__":
    unittest.main()
