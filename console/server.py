#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local-only web console for CBAP.

Security posture:
  * binds 127.0.0.1 only
  * validates Host and Origin (DNS-rebinding / CSRF)
  * requires a per-process token on every API call
  * exposes exactly two mutations: per-device estop and global estop
  * has no resume endpoint
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from console.backend import ConsoleBackend
except ImportError:  # direct execution
    from backend import ConsoleBackend

STATIC = Path(__file__).resolve().parent / "static"


class ConsoleHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, backend: ConsoleBackend, token: str):
        self.backend = backend
        self.token = token
        super().__init__(addr, handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "cbap-console/0.1"
    sys_version = ""

    # ── helpers ──────────────────────────────────────────────
    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; "
                         "style-src 'self'; img-src 'self' data:; "
                         "connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        port = self.server.server_port
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # native/curl client; token still required
        port = self.server.server_port
        return origin in {f"http://127.0.0.1:{port}",
                          f"http://localhost:{port}"}

    def _token_ok(self) -> bool:
        supplied = self.headers.get("X-CBAP-Token", "")
        return secrets.compare_digest(supplied, self.server.token)

    def _api_guard(self) -> bool:
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "invalid Host"})
            return False
        if not self._origin_ok():
            self._json(403, {"ok": False, "error": "invalid Origin"})
            return False
        if not self._token_ok():
            self._json(403, {"ok": False, "error": "invalid console token"})
            return False
        return True

    # ── routes ───────────────────────────────────────────────
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._index()
            return
        if self.path == "/static/app.js":
            self._file(STATIC / "app.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/static/style.css":
            self._file(STATIC / "style.css", "text/css; charset=utf-8")
            return
        if self.path == "/api/status":
            if not self._api_guard():
                return
            self._json(200, self.server.backend.refresh())
            return
        if self.path.startswith("/api/audit"):
            if not self._api_guard():
                return
            limit = 80
            if "?" in self.path:
                from urllib.parse import parse_qs
                q = parse_qs(self.path.split("?", 1)[1])
                try:
                    limit = int((q.get("limit") or ["80"])[0])
                except ValueError:
                    pass
            self._json(200, self.server.backend.audit(limit))
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/api/estop":
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._api_guard():
            return
        try:
            n = int(self.headers.get("Content-Length") or "0")
            if n <= 0 or n > 8192:
                raise ValueError("bad body size")
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        fd = body.get("fd")
        if fd is not None and not isinstance(fd, str):
            self._json(400, {"ok": False, "error": "fd must be a string or null"})
            return
        reason = str(body.get("reason") or "console")[:200]
        res = self.server.backend.estop(fd, reason=reason)
        self._json(200 if res.get("ok") else 500, res)

    # ── static ───────────────────────────────────────────────
    def _file(self, path: Path, ctype: str) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._json(404, {"ok": False, "error": "not found"})
            return
        self._send(200, data, ctype)

    def _index(self) -> None:
        try:
            html = (STATIC / "index.html").read_text(encoding="utf-8")
        except OSError:
            self._json(500, {"ok": False, "error": "index missing"})
            return
        html = html.replace("__CONSOLE_TOKEN__", self.server.token)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        # Keep operator logs quiet; the Kernel audit is the authoritative log.
        pass


def serve(socket_path: str, audit_path: str | None, port: int = 8765,
          token: str | None = None, kernel_token: str | None = None) -> None:
    backend = ConsoleBackend(socket_path, audit_path=audit_path,
                             token=kernel_token)
    httpd = ConsoleHTTPServer(("127.0.0.1", int(port)), Handler,
                              backend=backend, token=token or secrets.token_urlsafe(24))
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"CBAP console: {url}")
    print(f"kernel socket: {backend.socket_path}")
    print("local-only; no resume endpoint; estop is latched in the Kernel")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        backend.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Local CBAP operator console")
    ap.add_argument("--socket", default=os.environ.get("CBAP_SOCKET",
                                                       str(ROOT / "cbap.sock")))
    ap.add_argument("--audit", default=os.environ.get(
        "CBAP_AUDIT", str(ROOT / "logs" / "cbap-audit.jsonl")))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=None,
                    help="optional Kernel auth token (not the browser token)")
    ns = ap.parse_args()
    serve(ns.socket, ns.audit, ns.port, kernel_token=ns.token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
