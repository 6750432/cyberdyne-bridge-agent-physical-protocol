#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the local CBAP operator console."""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import time
import unittest

from console.backend import ConsoleBackend
from console.server import ConsoleHTTPServer, Handler
from kernel.legacy_runtime.server import KernelServer


class ConsoleDriver:
    def __init__(self):
        self.connected = True
        self.state = {"on": False, "level": 0}
        self.seq = 0
        self.estop_count = 0
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_disconnect = None

    def describe(self):
        return {
            "device_id": "test://console/light-01",
            "type": "test-light",
            "name": "Console test light",
            "safety": {"estop": True, "watchdog_ms": 5000,
                       "safe_state": "off"},
        }

    def health(self):
        return {"ok": True, "device_id": self.describe()["device_id"],
                "state_age_ms": 0}

    def wait_state(self, timeout_s):
        self.seq += 1
        return dict(self.state, seq=self.seq, t=time.time())

    def estop(self):
        self.estop_count += 1
        self.state["on"] = False
        return True

    def send(self, command):
        return True

    def map_action(self, frame):
        return {"cmd": str((frame or {}).get("op") or "unknown")}


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-console-test-")
        self.sock = os.path.join(self.tmp, "cbap.sock")
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self.driver = ConsoleDriver()
        self.kernel = KernelServer(
            self.driver, socket_path=self.sock, audit_path=self.audit)
        self.assertTrue(self.kernel.start())
        self.backend = ConsoleBackend(self.sock, audit_path=self.audit)
        self.token = "console-test-token"
        self.httpd = ConsoleHTTPServer(
            ("127.0.0.1", 0), Handler, backend=self.backend, token=self.token)
        self.port = self.httpd.server_port
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.backend.close()
        self.kernel.stop()

    def req(self, method, path, body=None, *, token=True, host=None,
            origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {
            "Host": host or f"127.0.0.1:{self.port}",
            "X-CBAP-Token": self.token if token else "",
        }
        if origin:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode("utf-8")
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_index_and_status(self):
        status, data = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"CBAP", data)
        self.assertIn(self.token.encode(), data)
        status, data = self.req("GET", "/api/status")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["devices"][0]["device_id"],
                         "test://console/light-01")
        self.assertFalse(payload["devices"][0]["safe"])

    def test_api_guards(self):
        self.assertEqual(self.req("GET", "/api/status", token=False)[0], 403)
        self.assertEqual(self.req("GET", "/api/status",
                                  host="evil.example")[0], 403)
        self.assertEqual(self.req("GET", "/api/status",
                                  origin="http://evil.example")[0], 403)
        self.assertEqual(self.req("GET", "/api/status",
                                  origin=f"http://127.0.0.1:{self.port}")[0], 200)

    def test_per_device_estop_and_audit(self):
        status, data = self.req("GET", "/api/status")
        fd = json.loads(data)["devices"][0]["fd"]
        status, data = self.req(
            "POST", "/api/estop",
            {"fd": fd, "reason": "unit-test"},
            origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(status, 200, data)
        self.assertTrue(json.loads(data)["ok"])
        self.assertEqual(self.driver.estop_count, 1)
        status, data = self.req("GET", "/api/audit?limit=20")
        self.assertEqual(status, 200)
        rows = json.loads(data)["rows"]
        self.assertTrue(any(r.get("event") == "estop" for r in rows))


if __name__ == "__main__":
    unittest.main()
