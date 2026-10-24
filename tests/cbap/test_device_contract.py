#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0/P1/P2/P3/P4 contract, policy, quota, facts, and safe-state tests."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest import mock

from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.device_contract import ContractError, normalize_contract
from kernel.legacy_runtime.security import CapabilityPolicy
from kernel.legacy_runtime.server import KernelServer


class SecureDriver:
    def __init__(self, *, max_bytes=65536, max_sessions=4, max_inflight=4,
                 rate_hz=20, trust_independent=False):
        self.connected = True
        self.estop_count = 0
        self.safe = False
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_disconnect = None
        self._max_bytes = max_bytes
        self._max_sessions = max_sessions
        self._max_inflight = max_inflight
        self._rate_hz = rate_hz
        self._trust_independent = trust_independent

    def describe(self):
        return {
            "device_id": "test://parity/light-01",
            "type": "test-light",
            "contract": "cbap-device-v1",
            "class": "actuator",
            "version": "1.0",
            "actions": {
                "move": {"args": {"dir": "string"}, "result": {},
                         "danger": "normal", "idempotent": False},
            },
            "capabilities": ["read", "write", "lease", "estop"],
            "trust": {"source": "test-facts", "independent": self._trust_independent,
                      "attestation": "none", "level": 2 if self._trust_independent else 1},
            "isolation": {"process": "test", "uid": os.getuid(),
                          "sandbox": "none", "network": "local"},
            "resources": {"max_inflight": self._max_inflight,
                          "rate_hz": self._rate_hz,
                          "max_bytes": self._max_bytes,
                          "max_sessions": self._max_sessions},
            "safety": {"estop": True, "watchdog_ms": 5000, "safe_state": "off"},
        }

    def health(self):
        return {"ok": True, "connected": True, "state_age_ms": 0,
                "device_id": "test://parity/light-01"}

    def wait_state(self, timeout_s):
        return {"on": False, "seq": 1}

    def estop(self):
        self.estop_count += 1
        self.safe = True
        return True

    def safe_state(self):
        return "off" if self.safe else "unknown"

    def send(self, command):
        if self.on_result:
            self.on_result(str(command.get("cmd") or "move"), True, None,
                           {"facts": {"observed": True},
                            "independent": self._trust_independent})
        return True

    def map_action(self, frame):
        return {"cmd": str((frame or {}).get("op") or "move")}


class ContractPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-parity-")
        self.sock = os.path.join(self.tmp, "cbap.sock")
        self.audit = os.path.join(self.tmp, "audit.jsonl")

    def kernel(self, driver, **kwargs):
        k = KernelServer(driver, socket_path=self.sock, audit_path=self.audit,
                         token="parity-token", **kwargs)
        self.assertTrue(k.start())
        self.addCleanup(k.stop)
        return k

    def client(self, operator=False):
        c = CBAPClient(self.sock, agent_id="parity")
        c.connect()
        c.hello(operator_token=open(self.sock + ".operator", encoding="ascii").read().strip()
                if operator else "parity-token")
        return c

    def test_contract_rejects_bad_id_and_shape(self):
        with self.assertRaises(ContractError):
            normalize_contract({"device_id": "not-a-device", "safety": {
                "estop": True, "watchdog_ms": 1000}})
        c = normalize_contract({
            "device_id": "test://x/1", "type": "test",
            "safety": {"estop": True, "watchdog_ms": 1000},
            "actions": ["ping"],
        })
        self.assertEqual(c["contract"], "cbap-device-v1")
        self.assertIn("ping", c["actions"])
        self.assertIn("safety", c)
        self.assertIn("trust", c)

    def test_kernel_welcome_exposes_contract_and_rights(self):
        self.kernel(SecureDriver())
        c = self.client()
        try:
            w = c.hello(token="parity-token")
            dev = w["devices"][0]
            self.assertEqual(dev["contract"], "cbap-device-v1")
            self.assertEqual(dev["class"], "actuator")
            self.assertIn("move", dev["actions"])
            self.assertIn("resources", dev)
            self.assertIn("trust", dev)
        finally:
            c.close()

    def test_production_default_is_default_deny(self):
        with mock.patch.dict(os.environ, {"CBAP_TEST_MODE": "0"}):
            p = CapabilityPolicy(None)
            self.assertEqual(p.default_devices, [])
            with mock.patch.dict(os.environ, {"CBAP_TEST_MODE": "0"}):
                k = KernelServer(SecureDriver(), socket_path=self.sock,
                                 audit_path=self.audit, token="parity-token")
                self.assertTrue(k.start())
                self.addCleanup(k.stop)
                c = CBAPClient(self.sock, agent_id="denied")
                c.connect()
                c.hello(token="parity-token")
                r = c.open("test://parity/light-01", "r")
                self.assertFalse(r["ok"])
                self.assertEqual(r["error"]["code"], "E_PERM")
                c.close()

    def test_device_frame_and_session_quotas(self):
        self.kernel(SecureDriver(max_bytes=48, max_sessions=1, rate_hz=100))
        c = self.client()
        try:
            a = c.open("test://parity/light-01", "exclusive")
            self.assertTrue(a["ok"], a)
            fd = a["payload"]["fd"]
            self.assertTrue(c.lease(fd)["ok"])
            big = c.call("write", {"fd": fd, "frame": {
                "op": "move", "args": {"dir": "x" * 200}}})
            self.assertFalse(big["ok"])
            self.assertEqual(big["error"]["code"], "E_INVAL")
            b = c.open("test://parity/light-01", "r")
            self.assertFalse(b["ok"])
            self.assertEqual(b["error"]["code"], "E_BUSY")
        finally:
            c.close()

    def test_facts_carry_trust_and_independent_requirement(self):
        self.kernel(SecureDriver(trust_independent=False))
        c = self.client()
        try:
            r = c.open("test://parity/light-01", "exclusive")
            fd = r["payload"]["fd"]
            c.lease(fd)
            _, _, res = c.write(fd, {"op": "move", "args": {"dir": "north"}})
            self.assertTrue(res["ok"], res)
            self.assertEqual(res["facts"]["trust"]["source"], "test-facts")
            self.assertFalse(res["facts"]["independent"])
            self.assertEqual(res["facts"]["device_id"], "test://parity/light-01")
        finally:
            c.close()
        self.kernel(SecureDriver(trust_independent=True), require_independent_facts=True)
        c = self.client()
        try:
            r = c.open("test://parity/light-01", "exclusive")
            fd = r["payload"]["fd"]
            c.lease(fd)
            _, _, res = c.write(fd, {"op": "move", "args": {"dir": "north"}})
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["facts"]["independent"])
        finally:
            c.close()

    def test_strict_contract_and_isolated_input_gate(self):
        from tests.cbap.test_security import SecurityDriver
        with self.assertRaises(ValueError):
            KernelServer(SecurityDriver(), socket_path=self.sock,
                         audit_path=self.audit, strict_contracts=True)
        from drivers.host_desktop.devices import HostMouseDriver
        with self.assertRaises(ValueError):
            KernelServer(HostMouseDriver(False), socket_path=self.sock,
                         audit_path=self.audit, require_isolated_input=True)

    def test_device_rate_limit_is_per_device(self):
        self.kernel(SecureDriver(rate_hz=1))
        c = self.client()
        try:
            r = c.open("test://parity/light-01", "exclusive")
            fd = r["payload"]["fd"]
            c.lease(fd)
            first = c.call("write", {"fd": fd, "frame": {
                "op": "move", "args": {"dir": "north"}}})
            self.assertTrue(first["ok"], first)
            second = c.call("write", {"fd": fd, "frame": {
                "op": "move", "args": {"dir": "south"}}})
            self.assertFalse(second["ok"], second)
            self.assertEqual(second["error"]["code"], "E_BUSY")
        finally:
            c.close()

    def test_estop_reports_per_device_safe_state_evidence(self):
        self.kernel(SecureDriver())
        c = self.client(operator=True)
        try:
            r = c.open("test://parity/light-01", "exclusive")
            fd = r["payload"]["fd"]
            c.lease(fd)
            res = c.estop(fd, reason="parity test")
            self.assertTrue(res["ok"], res)
            self.assertEqual(res["payload"]["devices"][0]["device_id"],
                             "test://parity/light-01")
            self.assertEqual(res["payload"]["devices"][0]["safe_state"], "off")
            self.assertFalse(res["payload"]["devices"][0]["driver_ok"] is None)
        finally:
            c.close()


class PortalInputTest(unittest.TestCase):
    def test_portal_probe_and_chord_parser(self):
        from drivers.host_desktop.portal_input import (
            PortalError, PortalRemoteDesktop, parse_chord,
        )
        try:
            portal = PortalRemoteDesktop(timeout_s=5)
            types = portal.available_device_types()
        except PortalError as e:
            self.skipTest(f"portal unavailable: {e}")
        self.assertGreaterEqual(types, 0)
        self.assertEqual(parse_chord("ctrl+l"), [0xFFE3, ord("l")])
        with self.assertRaises(PortalError):
            parse_chord("ctrl+€")


if __name__ == "__main__":
    unittest.main()
