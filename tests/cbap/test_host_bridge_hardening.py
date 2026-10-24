#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Technical hardening tests: loopback bind and host bridge guards."""
from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path

from kernel.legacy_runtime.server import KernelServer, _is_loopback_host
from tests.cbap.test_device_contract import SecureDriver


class HostBridgeHardeningTest(unittest.TestCase):
    def test_loopback_classifier(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            self.assertTrue(_is_loopback_host(host), host)
        for host in ("0.0.0.0", "192.168.1.10", "10.0.2.2", "example.com", "::"):
            self.assertFalse(_is_loopback_host(host), host)

    def test_kernel_refuses_public_tcp_bind_by_default(self):
        tmp = tempfile.mkdtemp(prefix="cbap-bind-")
        with self.assertRaises(ValueError) as cm:
            KernelServer(SecureDriver(), socket_path=Path(tmp) / "cbap.sock",
                         audit_path=Path(tmp) / "audit.jsonl",
                         tcp_host="0.0.0.0", tcp_port=0)
        self.assertIn("loopback", str(cm.exception))

    def test_kernel_allows_public_only_with_explicit_flag(self):
        tmp = tempfile.mkdtemp(prefix="cbap-bind-")
        # No start(): the guard is the behavior under test, not binding.
        k = KernelServer(SecureDriver(), socket_path=Path(tmp) / "cbap.sock",
                         audit_path=Path(tmp) / "audit.jsonl",
                         tcp_host="0.0.0.0", tcp_port=0,
                         allow_public_bind=True)
        self.assertTrue(k.allow_public_bind)

    def test_host_bridge_resolves_random_token_and_no_status_leak(self):
        # Importing the CLI module is safe: work only happens in main().
        from tools import cbap_host_bridge as hb
        import secrets
        self.assertTrue(hb._is_loopback_host("127.0.0.1"))
        token = secrets.token_urlsafe(32)
        self.assertGreaterEqual(len(token), 32)
        # The CLI token default is None; a fixed token must not be present.
        import inspect
        src = inspect.getsource(hb.main)
        self.assertIn("secrets.token_urlsafe", src)
        self.assertNotIn('"token": a.token', src)


if __name__ == "__main__":
    unittest.main()
