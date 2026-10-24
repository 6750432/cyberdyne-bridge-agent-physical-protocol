#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kernel onboarding-registry hot-plug tests."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.test_security import SecurityDriver

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "tests/cbap/fake_mcp_hardware.py"


class RegistryHotplugTest(unittest.TestCase):
    def test_load_disable_and_unload(self):
        tmp = tempfile.mkdtemp(prefix="cbap-registry-")
        reg = Path(tmp) / "onboarded"
        reg.mkdir(mode=0o700)
        manifest = {
            "device_id": "mcp://lab/hotplug-01",
            "display_name": "Hotplug light",
            "transport": {"type": "stdio",
                          "command": [sys.executable, str(FAKE),
                                      "--device", "light"],
                          "cwd": str(ROOT)},
            "tools": {"turn_on": {"tool": "turn_on"},
                      "turn_off": {"tool": "turn_off"}},
            "facts": {"source": "tool", "tool": "get_state"},
            "estop": {"tool": "turn_off", "expect": {"on": False}},
            "poll_interval": 0.05,
        }
        (reg / "hotplug.json").write_text(json.dumps(manifest), encoding="utf-8")
        (reg / "registry.json").write_text(json.dumps({
            "devices": {"hotplug": {"enabled": True}}}), encoding="utf-8")
        sock = os.path.join(tmp, "cbap.sock")
        audit = os.path.join(tmp, "audit.jsonl")
        k = KernelServer(SecurityDriver(), socket_path=sock, audit_path=audit,
                         mcp_registry=str(reg))
        self.assertTrue(k.start())
        c = None
        try:
            c = CBAPClient(sock, agent_id="registry-operator")
            c.connect()
            c.hello(token=k.token, operator_token=k.operator_token)
            listing = c.device_list()
            ids = [d["device_id"] for d in listing["payload"]["devices"]]
            self.assertIn("mcp://lab/hotplug-01", ids, listing)
            (reg / "registry.json").write_text(json.dumps({
                "devices": {"hotplug": {"enabled": False}}}), encoding="utf-8")
            r = c.call("registry_reload", {})
            self.assertTrue(r.get("ok"), r)
            self.assertIn("mcp://lab/hotplug-01",
                          (r.get("payload") or {}).get("unloaded", []), r)
            listing = c.device_list()
            ids = [d["device_id"] for d in listing["payload"]["devices"]]
            self.assertNotIn("mcp://lab/hotplug-01", ids, listing)
        finally:
            if c:
                c.close()
            k.stop()


if __name__ == "__main__":
    unittest.main()
