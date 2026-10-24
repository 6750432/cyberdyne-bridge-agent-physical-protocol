#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional TCP / TLS / mTLS transport regression tests."""
from __future__ import annotations

import os
import shutil
import ssl
import subprocess
import tempfile
import unittest

from kernel.legacy_runtime.client import CBAPClient
from kernel.legacy_runtime.server import KernelServer
from tests.cbap.test_security import SecurityDriver


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cbap-tcp-")
        self.sock = os.path.join(self.tmp, "cbap.sock")

    def tearDown(self):
        for name in os.listdir(self.tmp):
            try:
                os.unlink(os.path.join(self.tmp, name))
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def _kernel(self, **kw):
        k = KernelServer(SecurityDriver(), socket_path=self.sock,
                         audit_path=os.path.join(self.tmp, "audit.jsonl"),
                         token="tcp-token", tcp_host="127.0.0.1",
                         tcp_port=0, **kw)
        self.assertTrue(k.start())
        self.addCleanup(k.stop)
        return k

    def test_tcp_token_round_trip(self):
        k = self._kernel()
        c = CBAPClient(tcp_host="127.0.0.1", tcp_port=k.tcp_port,
                       agent_id="tcp-client")
        c.connect()
        try:
            self.assertTrue(c.hello(token="tcp-token").get("session_id"))
            self.assertTrue(c.device_list().get("ok"))
        finally:
            c.close()

    def test_mtls_round_trip_and_missing_client_cert(self):
        openssl = shutil.which("openssl")
        if not openssl:
            self.skipTest("openssl not installed")
        server_crt, server_key, client_crt, client_key = self._certs(openssl)
        k = self._kernel(tls_cert=server_crt, tls_key=server_key,
                         tls_ca=client_crt, tls_require_client_cert=True)
        ctx = ssl.create_default_context(cafile=server_crt)
        ctx.load_cert_chain(client_crt, client_key)
        c = CBAPClient(tcp_host="127.0.0.1", tcp_port=k.tcp_port,
                       tls_context=ctx, tls_server_hostname="127.0.0.1",
                       agent_id="mtls-client")
        c.connect()
        try:
            self.assertTrue(c.hello(token="tcp-token").get("session_id"))
            self.assertTrue(c.device_list().get("ok"))
        finally:
            c.close()
        no_cert = ssl.create_default_context(cafile=server_crt)
        bad = CBAPClient(tcp_host="127.0.0.1", tcp_port=k.tcp_port,
                         tls_context=no_cert, tls_server_hostname="127.0.0.1")
        with self.assertRaises((ssl.SSLError, OSError, TimeoutError)):
            bad.connect()
            bad.hello(token="tcp-token", timeout=1.0)
        bad.close()

    def _certs(self, openssl):
        def run(*args):
            subprocess.run([openssl, *args], check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        server_crt = os.path.join(self.tmp, "server.crt")
        server_key = os.path.join(self.tmp, "server.key")
        client_crt = os.path.join(self.tmp, "client.crt")
        client_key = os.path.join(self.tmp, "client.key")
        run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", server_key, "-out", server_crt,
            "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1")
        run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", client_key, "-out", client_crt,
            "-subj", "/CN=cbap-client")
        return server_crt, server_key, client_crt, client_key


if __name__ == "__main__":
    unittest.main()
