#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6: per-device contract/conformance checks for host devices."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from drivers.host_desktop.devices import (
    HostDisplayDriver, HostFilesystemDriver, HostInputDriver,
    HostKeyboardDriver, HostMouseDriver,
)
from drivers.mc.driver import McDriver


class HostDeviceConformanceTest(unittest.TestCase):
    def test_mc_and_host_descriptors_are_declared(self):
        mc = McDriver()
        d = mc.describe()
        self.assertEqual(d["contract"], "cbap-device-v1")
        self.assertFalse(d["legacy"])
        self.assertEqual(d["class"], "actuator")
        self.assertIn("move", d["actions"])
        self.assertGreaterEqual(d["resources"]["max_bytes"], 65536)

        with tempfile.TemporaryDirectory() as td:
            fs = HostFilesystemDriver(td)
            fd = fs.describe()
            self.assertEqual(fd["class"], "filesystem")
            self.assertFalse(fd["legacy"])
            self.assertTrue(fd["trust"]["source"])
            self.assertFalse(fd["trust"]["independent"])
            self.assertIn("write_file", fd["actions"])

    def test_host_fs_actions_and_escape_denial(self):
        with tempfile.TemporaryDirectory() as td:
            drv = HostFilesystemDriver(td)
            out = []
            drv.on_result = lambda c, ok, why, extra: out.append((ok, why, extra))
            drv.send(drv.map_action({"op": "write_file", "args": {
                "path": "nested/a.txt", "content": "hello"}}))
            self.assertTrue(out[-1][0], out[-1])
            drv.send(drv.map_action({"op": "list", "args": {"path": "nested"}}))
            self.assertTrue(out[-1][0], out[-1])
            drv.send(drv.map_action({"op": "write_file", "args": {
                "path": "../../escape", "content": "x"}}))
            self.assertFalse(out[-1][0], out[-1])
            self.assertIn("E_PERM", out[-1][1] or "")

    def test_display_and_input_fail_closed_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            disp = HostDisplayDriver(td, enable=False)
            calls = []
            disp.on_result = lambda c, ok, why, extra: calls.append((ok, why))
            disp.send(disp.map_action({"op": "screenshot", "args": {}}))
            self.assertFalse(calls[-1][0])
            self.assertIn("E_SAFETY", calls[-1][1] or "")
            self.assertEqual(disp.describe()["class"], "display")
            self.assertTrue(disp.describe()["safety"]["estop"])

            for drv in (HostMouseDriver(False), HostKeyboardDriver(False)):
                calls = []
                drv.on_result = lambda c, ok, why, extra: calls.append((ok, why))
                action = "position" if drv.KIND == "mouse" else "type"
                drv.send(drv.map_action({"op": action, "args": {}}))
                self.assertFalse(calls[-1][0])
                self.assertIn("E_SAFETY", calls[-1][1] or "")

    def test_portal_backend_is_declared_not_default(self):
        portal_mouse = HostMouseDriver(False, backend="portal")
        d = portal_mouse.describe()
        self.assertEqual(d["transport"], "wayland-portal")
        self.assertEqual(d["isolation"]["sandbox"], "portal")
        self.assertTrue(d["wayland_native"])
        self.assertIn("move_relative", d["actions"])
        self.assertNotIn("move", d["actions"])
        # X11 remains the default; portal is a separate explicit selection.
        self.assertEqual(HostMouseDriver(False).describe()["transport"],
                         "x11/xwayland")


if __name__ == "__main__":
    unittest.main()
