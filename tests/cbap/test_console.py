#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the local CBAP operator console."""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import sys
import threading
import time
import unittest

from console.backend import ConsoleBackend
from console.server import ConsoleHTTPServer, Handler
from kernel.legacy_runtime.client import CBAPClient
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
        if self.on_result:
            def done():
                time.sleep(0.01)
                self.on_result(str((command or {}).get("cmd") or "unknown"),
                               True, None, {})
            threading.Thread(target=done, daemon=True).start()
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
            self.driver, socket_path=self.sock, audit_path=self.audit,
            policy={
                "default": {
                    "devices": ["test://console/light-01"],
                    "capabilities": ["read", "write", "lease"],
                },
                "approvals": {
                    "devices": ["test://console/light-01"],
                    "ops": ["move"], "ttl_ms": 10000,
                    "required_approvals": 2, "sla_ms": 100,
                },
            })
        self.assertTrue(self.kernel.start())
        self.history_path = os.path.join(self.tmp, "console-history.jsonl")
        self.backend = ConsoleBackend(self.sock, audit_path=self.audit,
                                      history_path=self.history_path)
        self.operator_token = "console-test-operator"
        self.httpd = ConsoleHTTPServer(
            ("127.0.0.1", 0), Handler, backend=self.backend,
            operator_token=self.operator_token)
        self.port = self.httpd.server_port
        self.cookie = None
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
        }
        if token and self.cookie:
            headers["Cookie"] = self.cookie
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
        self.assertNotIn(self.operator_token.encode(), data)
        self.login()
        status, data = self.req("GET", "/api/status")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["devices"][0]["device_id"],
                         "test://console/light-01")
        self.assertFalse(payload["devices"][0]["safe"])
        self.backend.refresh()
        restarted = ConsoleBackend(self.sock, audit_path=self.audit,
                                   history_path=self.history_path)
        try:
            hist = restarted.history("test://console/light-01")
            self.assertTrue(hist["ok"])
            self.assertGreaterEqual(len(hist["samples"]), 1, hist)
        finally:
            restarted.close()

    def login(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps({"token": self.operator_token}).encode()
        c.request("POST", "/api/login", body=body, headers={
            "Host": f"127.0.0.1:{self.port}",
            "Origin": f"http://127.0.0.1:{self.port}",
            "Content-Type": "application/json",
        })
        r = c.getresponse()
        raw = r.getheader("Set-Cookie")
        data = r.read(); c.close()
        self.assertEqual(r.status, 200, data)
        self.assertIn("cbap_console_session=", raw or "")
        self.cookie = raw.split(";", 1)[0]

    def test_api_guards(self):
        self.assertEqual(self.req("GET", "/api/status", token=False)[0], 401)
        self.assertEqual(self.req("GET", "/api/status",
                                  host="evil.example")[0], 403)
        self.assertEqual(self.req("GET", "/api/status",
                                  origin="http://evil.example")[0], 403)
        self.login()
        self.assertEqual(self.req("GET", "/api/status",
                                  origin=f"http://127.0.0.1:{self.port}")[0], 200)

    def test_per_device_estop_and_audit(self):
        self.login()
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
        resumed = self.backend.resume("test://console/light-01",
                                      reason="unit-test recovery")
        self.assertTrue(resumed["ok"], resumed)
        self.assertFalse(resumed["status"]["devices"][0]["safe"], resumed)
        self.assertTrue(any(r.get("event") == "resume"
                            for r in self.backend.audit(20)["rows"]))


    def test_approve_and_release_lease(self):
        self.login()
        agent = CBAPClient(self.sock, agent_id="approval-agent")
        agent.connect()
        try:
            agent.hello(token=self.kernel.token)
            opened = agent.open("test://console/light-01", mode="rw")
            fd = opened["payload"]["fd"]
            agent.lease(fd)
            rid = agent.request("write", {
                "fd": fd,
                "frame": {"channel": "body", "op": "move", "args": {}},
            })
            agent.wait_ack(rid, 2)
            time.sleep(0.15)
            pending = self.backend.approvals()
            self.assertTrue(pending["ok"], pending)
            self.assertEqual(len(pending["approvals"]), 1, pending)
            notes = self.backend.notifications()
            self.assertTrue(any(n.get("type") == "approval_sla"
                                for n in notes["notifications"]), notes)
            aid = pending["approvals"][0]["approval_id"]
            first = self.backend.approve(aid, approver="operator-1")
            self.assertTrue(first["ok"], first)
            self.assertTrue(first["result"].get("pending"), first)
            self.assertEqual(len(self.backend.approvals()["approvals"]), 1)
            repeat = self.backend.approve(aid, approver="operator-1")
            self.assertFalse(repeat["ok"], repeat)
            second = self.backend.approve(aid, approver="operator-2")
            self.assertTrue(second["ok"], second)
            self.assertFalse(second["result"].get("pending"), second)
            result = agent.wait(rid, 3)
            self.assertTrue(result.get("ok"), result)
            self.assertEqual(self.backend.approvals()["approvals"], [])
            status, data = self.req("POST", "/api/lease/release",
                                    {"device_id": "test://console/light-01"},
                                    origin=f"http://127.0.0.1:{self.port}")
            self.assertEqual(status, 200, data)
            self.assertTrue(json.loads(data)["ok"])
            self.assertIn("admin_release",
                          [r.get("event") for r in self.backend.audit(20)["rows"]])
        finally:
            agent.close()

    def test_onboard_scan_create_probe(self):
        fake = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")
        registry = os.path.join(self.tmp, "onboarded")
        backend = ConsoleBackend(self.sock, audit_path=self.audit,
                                 registry_dir=registry)
        try:
            scan = backend.onboard_scan({"command": [sys.executable, fake]})
            self.assertTrue(scan["ok"], scan)
            self.assertIn("status", [t["name"] for t in scan["tools"]])
            made = backend.onboard_create({
                "device_id": "mcp://onboard/fake-01",
                "command": [sys.executable, fake],
                "tools": [{"cbap_op": "status", "tool": "status"}],
                "facts": {"source": "tool", "tool": "status"},
            })
            self.assertTrue(made["ok"], made)
            self.assertTrue(os.path.exists(made["path"]))
            listed = backend.onboard_list()
            self.assertTrue(any(d["name"] == "mcp:_onboard_fake-01"
                                for d in listed["devices"]), listed)
            probed = backend.onboard_probe({"name": "mcp:_onboard_fake-01"})
            self.assertTrue(probed["ok"], probed)
            self.assertTrue(probed["health"]["ok"], probed)
            toggled = backend.onboard_toggle({"name": "mcp:_onboard_fake-01",
                                               "enabled": False})
            self.assertTrue(toggled["ok"], toggled)
            disabled = backend.onboard_probe({"name": "mcp:_onboard_fake-01"})
            self.assertFalse(disabled["ok"], disabled)
            self.assertTrue(backend.onboard_toggle({
                "name": "mcp:_onboard_fake-01", "enabled": True})["ok"])
            old = os.environ.get("CBAP_MANIFEST_KEY")
            os.environ["CBAP_MANIFEST_KEY"] = "onboard-test-key"
            try:
                signed = backend.onboard_sign({"name": "mcp:_onboard_fake-01"})
                self.assertTrue(signed["ok"], signed)
                with open(made["path"], encoding="utf-8") as f:
                    self.assertTrue(json.loads(f.read()).get("signature"))
            finally:
                if old is None:
                    os.environ.pop("CBAP_MANIFEST_KEY", None)
                else:
                    os.environ["CBAP_MANIFEST_KEY"] = old
            self.backend.refresh()
            hist = self.backend.history("test://console/light-01")
            self.assertTrue(hist["ok"])
            self.assertGreaterEqual(len(hist["samples"]), 1, hist)
        finally:
            backend.close()

if __name__ == "__main__":
    unittest.main()
