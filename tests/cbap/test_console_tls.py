#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remote-console mTLS identity tests (loopback transport)."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest

from console.backend import ConsoleBackend
from console.server import ConsoleHTTPServer, Handler
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.test_console import ConsoleDriver


class ConsoleTLSTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-console-tls-")
        self.sock = os.path.join(self.tmp, "cbap.sock")
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self.kernel = KernelServer(ConsoleDriver(), socket_path=self.sock,
                                   audit_path=self.audit)
        self.assertTrue(self.kernel.start())
        self.backend = ConsoleBackend(
            self.sock, audit_path=self.audit,
            history_path=os.path.join(self.tmp, "history.jsonl"))
        self.operator = "tls-operator-token"
        self.server_crt, self.server_key, self.client_crt, self.client_key = \
            self._certs()
        sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sctx.load_cert_chain(self.server_crt, self.server_key)
        sctx.load_verify_locations(self.client_crt)
        sctx.verify_mode = ssl.CERT_REQUIRED
        self.httpd = ConsoleHTTPServer(
            ("127.0.0.1", 0), Handler, backend=self.backend,
            operator_token=self.operator, tls_context=sctx)
        self.httpd.allowed_hosts.add(f"127.0.0.1:{self.httpd.server_port}")
        self.port = self.httpd.server_port
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.cookie = None

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        self.thread.join(timeout=2)
        self.backend.close(); self.kernel.stop()

    def _certs(self):
        openssl = shutil.which("openssl")
        if not openssl:
            self.skipTest("openssl not installed")
        def run(*args):
            subprocess.run([openssl, *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sc = os.path.join(self.tmp, "server.crt")
        sk = os.path.join(self.tmp, "server.key")
        cc = os.path.join(self.tmp, "client.crt")
        ck = os.path.join(self.tmp, "client.key")
        run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", sk, "-out", sc, "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1")
        run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", ck, "-out", cc, "-subj", "/CN=remote-operator")
        return sc, sk, cc, ck

    def _conn(self, with_cert=True):
        ctx = ssl.create_default_context(cafile=self.server_crt)
        if with_cert:
            ctx.load_cert_chain(self.client_crt, self.client_key)
        return http.client.HTTPSConnection("127.0.0.1", self.port,
                                           context=ctx, timeout=5)

    def _req(self, method, path, body=None):
        c = self._conn()
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode()
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse(); data = r.read(); c.close()
        return r, data

    def test_client_cert_identity_and_login(self):
        r, data = self._req("POST", "/api/login", {"token": self.operator})
        self.assertEqual(r.status, 200, data)
        self.cookie = r.getheader("Set-Cookie").split(";", 1)[0]
        r, data = self._req("GET", "/api/session")
        self.assertEqual(r.status, 200, data)
        body = json.loads(data)
        self.assertEqual(body["operator"], "operator-1@remote-operator")
        r, data = self._req("GET", "/api/status")
        self.assertEqual(r.status, 200, data)



if __name__ == "__main__":
    unittest.main()
