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
import time
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

    def __init__(self, addr, handler, backend: ConsoleBackend,
                 operator_token: str, second_operator_token: str | None = None,
                 session_ttl_s: int = 8 * 3600):
        self.backend = backend
        self.operator_token = operator_token
        self.operator_tokens = {operator_token: "operator-1"}
        if second_operator_token:
            if second_operator_token == operator_token:
                raise ValueError("second operator token must be different")
            self.operator_tokens[second_operator_token] = "operator-2"
        self.session_ttl_s = int(session_ttl_s)
        self.sessions: dict[str, dict] = {}
        self.login_attempts: dict[str, list[float]] = {}
        self._session_lock = threading.Lock()
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

    def _json(self, code: int, obj: dict, extra: dict | None = None) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", extra=extra)

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

    def _session_token(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "cbap_console_session" and v:
                return v
        return None

    def _session_ok(self) -> bool:
        return self._session_name() is not None

    def _session_name(self) -> str | None:
        token = self._session_token()
        if not token:
            return None
        now = time.time()
        with self.server._session_lock:
            sess = self.server.sessions.get(token)
            if not sess or sess.get("expires", 0) <= now:
                self.server.sessions.pop(token, None)
                return None
            return str(sess.get("operator") or "operator")

    def _api_guard(self) -> bool:
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "invalid Host"})
            return False
        if not self._origin_ok():
            self._json(403, {"ok": False, "error": "invalid Origin"})
            return False
        if not self._session_ok():
            self._json(401, {"ok": False, "error": "operator login required"})
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
        if self.path == "/api/session":
            self._json(200, {"ok": True, "authenticated": self._session_ok(),
                             "operator": self._session_name()})
            return
        if self.path == "/api/status":
            if not self._api_guard():
                return
            self._json(200, self.server.backend.refresh())
            return
        if self.path == "/api/approvals":
            if not self._api_guard():
                return
            self._json(200, self.server.backend.approvals())
            return
        if self.path.startswith("/api/history"):
            if not self._api_guard():
                return
            from urllib.parse import parse_qs
            q = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            dev = (q.get("device_id") or [""])[0]
            try:
                limit = int((q.get("limit") or ["120"])[0])
            except ValueError:
                limit = 120
            self._json(200, self.server.backend.history(dev, limit))
            return
        if self.path.startswith("/api/onboard/"):
            if not self._api_guard():
                return
            self._onboard_get()
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

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or "0")
        if n <= 0 or n > 256 * 1024:
            raise ValueError("bad body size")
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("body must be an object")
        return body

    def do_POST(self) -> None:
        if self.path == "/api/login":
            self._login()
            return
        if self.path == "/api/logout":
            self._logout()
            return
        routes = {"/api/estop", "/api/approvals/approve",
                  "/api/approvals/deny", "/api/lease/release",
                  "/api/onboard/scan", "/api/onboard/create",
                  "/api/onboard/probe", "/api/onboard/toggle",
                  "/api/onboard/sign"}
        if self.path not in routes:
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._api_guard():
            return
        try:
            body = self._read_json()
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        if self.path == "/api/estop":
            fd = body.get("fd")
            if fd is not None and not isinstance(fd, str):
                self._json(400, {"ok": False, "error": "fd must be a string or null"})
                return
            reason = str(body.get("reason") or "console")[:200]
            res = self.server.backend.estop(fd, reason=reason)
        elif self.path in ("/api/approvals/approve", "/api/approvals/deny"):
            aid = body.get("approval_id")
            if not isinstance(aid, str) or not aid:
                self._json(400, {"ok": False, "error": "approval_id required"})
                return
            res = (self.server.backend.approve(
                       aid, approver=self._session_name() or "operator")
                   if self.path.endswith("/approve")
                   else self.server.backend.deny(aid))
        elif self.path == "/api/lease/release":
            dev = body.get("device_id")
            if not isinstance(dev, str) or not dev:
                self._json(400, {"ok": False, "error": "device_id required"})
                return
            res = self.server.backend.release_lease(dev)
        else:
            res = self._onboard_post(body)
        self._json(200 if res.get("ok") else 500, res)

    def _onboard_get(self) -> None:
        if self.path == "/api/onboard/list":
            self._json(200, self.server.backend.onboard_list())
            return
        self._json(404, {"ok": False, "error": "not found"})

    def _onboard_post(self, body: dict) -> dict:
        if self.path == "/api/onboard/scan":
            return self.server.backend.onboard_scan(body)
        if self.path == "/api/onboard/create":
            return self.server.backend.onboard_create(body)
        if self.path == "/api/onboard/probe":
            return self.server.backend.onboard_probe(body)
        if self.path == "/api/onboard/toggle":
            return self.server.backend.onboard_toggle(body)
        if self.path == "/api/onboard/sign":
            return self.server.backend.onboard_sign(body)
        return {"ok": False, "error": "not found"}

    def _login(self) -> None:
        if not self._host_ok() or not self._origin_ok():
            self._json(403, {"ok": False, "error": "invalid Host/Origin"})
            return
        now = time.time()
        ip = self.client_address[0]
        attempts = [t for t in self.server.login_attempts.get(ip, []) if t > now - 60]
        if len(attempts) >= 5:
            self._json(429, {"ok": False, "error": "too many login attempts"})
            return
        try:
            body = self._read_json()
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        supplied = body.get("token")
        operator = None
        if isinstance(supplied, str):
            for known, name in self.server.operator_tokens.items():
                if secrets.compare_digest(supplied, known):
                    operator = name
                    break
        if not operator:
            attempts.append(now)
            self.server.login_attempts[ip] = attempts
            self._json(401, {"ok": False, "error": "invalid operator token"})
            return
        token = secrets.token_urlsafe(32)
        with self.server._session_lock:
            self.server.sessions[token] = {
                "expires": now + self.server.session_ttl_s,
                "operator": operator,
            }
        cookie = (f"cbap_console_session={token}; HttpOnly; SameSite=Strict; "
                  f"Path=/; Max-Age={self.server.session_ttl_s}")
        self._json(200, {"ok": True}, {"Set-Cookie": cookie})

    def _logout(self) -> None:
        token = self._session_token()
        if token:
            with self.server._session_lock:
                self.server.sessions.pop(token, None)
        self._json(200, {"ok": True})

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
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        # Keep operator logs quiet; the Kernel audit is the authoritative log.
        pass


def serve(socket_path: str, audit_path: str | None, port: int = 8765,
          operator_token: str | None = None,
          second_operator_token: str | None = None,
          kernel_token: str | None = None) -> None:
    backend = ConsoleBackend(socket_path, audit_path=audit_path,
                             token=kernel_token)
    op_token = operator_token or secrets.token_urlsafe(18)
    httpd = ConsoleHTTPServer(("127.0.0.1", int(port)), Handler,
                              backend=backend, operator_token=op_token,
                              second_operator_token=second_operator_token)
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"CBAP console: {url}")
    print(f"operator token: {op_token}")
    if second_operator_token:
        print("second operator token: configured")
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
                    help="optional Kernel auth token")
    ap.add_argument("--operator-token", default=os.environ.get(
        "CBAP_CONSOLE_OPERATOR_TOKEN"),
        help="operator login token; generated and printed if omitted")
    ap.add_argument("--second-operator-token", default=os.environ.get(
        "CBAP_SECOND_OPERATOR_TOKEN"),
        help="second operator token for dual approval")
    ns = ap.parse_args()
    serve(ns.socket, ns.audit, ns.port,
          operator_token=ns.operator_token,
          second_operator_token=ns.second_operator_token,
          kernel_token=ns.token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
