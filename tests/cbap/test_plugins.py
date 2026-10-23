#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the driver API and agent manifest boundary."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from kernel.driver_api import AgentManifest, DeviceDriver, DriverRegistry

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "agents"
ARCHIVE_ALICE = ROOT / "archive" / "alice" / "agent.json"


class FakeDriver:
    def describe(self):
        return {"device_id": "fake://one"}

    def health(self):
        return {"ok": True}

    def send(self, command):
        return True

    def estop(self):
        return True

    def close(self):
        return None


class PluginBoundaryTest(unittest.TestCase):
    def test_active_agent_manifests(self):
        manifests = DriverRegistry(AGENTS).discover()
        self.assertEqual(set(manifests), {
            "cyberdyne", "mcp-mineflayer", "mindcraft", "voyager",
        })
        self.assertEqual({m.id for m in manifests.values() if m.active}, {
            "cyberdyne", "mcp-mineflayer", "mindcraft", "voyager",
        })
        for manifest in manifests.values():
            self.assertEqual(manifest.status, "active")
            self.assertEqual(manifest.validate(), [])
            self.assertTrue(manifest.cbap.get("device_id"))

    def test_alice_is_archived_not_active(self):
        manifest = AgentManifest.read(ARCHIVE_ALICE)
        self.assertEqual(manifest.status, "archived")
        self.assertFalse(manifest.active)
        self.assertNotIn(manifest.id, DriverRegistry(AGENTS).active())

    def test_fake_driver_matches_protocol(self):
        self.assertIsInstance(FakeDriver(), DeviceDriver)

    def test_python_factory_is_available_on_demand(self):
        manifest = DriverRegistry(AGENTS).get("cyberdyne")
        factory = manifest.resolve_factory()
        self.assertTrue(callable(factory))
        self.assertEqual(factory.__name__, "McDriver")


if __name__ == "__main__":
    unittest.main()
