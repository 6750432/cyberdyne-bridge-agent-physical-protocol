#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Additional host devices for the CBAP microkernel test surface.

Device IDs:
  host://fs        allowlisted filesystem (alias/peer of host://desktop)
  host://display   read-only screenshot into the allowlist
  host://input/mouse     opt-in X11/XWayland pointer controls
  host://input/keyboard  opt-in X11/XWayland key/text controls

Input devices are CLOSED by default. The host bridge must pass
--enable-input; otherwise their actions return E_SAFETY. They are a local
prototype, not a production remote-control service.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from pathlib import Path

from .driver import HostActionError, HostDesktopDriver

DEFAULT_SAFETY = {"estop": True, "watchdog_ms": 10000, "safe_state": "on"}


class _HostBase:
    DEVICE_ID = "host://device"
    NAME = "CBAP host device"

    def __init__(self):
        self.connected = True
        self._safe = False
        self._last_state = None
        self._last_state_at = 0.0
        self.on_state = None
        self.on_result = None
        self.on_event = None
        self.on_connect = None
        self.on_disconnect = None

    def describe(self) -> dict:
        return {
            "device_id": self.DEVICE_ID,
            "type": self.DEVICE_ID.split("://", 1)[1].split("/", 1)[0],
            "name": self.NAME,
            "transport": "host-local",
            "safety": dict(DEFAULT_SAFETY),
        }

    def health(self) -> dict:
        return {
            "ok": bool(self.connected and not self._safe),
            "connected": bool(self.connected),
            "safe": bool(self._safe),
            "state_age_ms": self.state_age_ms(),
            "device_id": self.DEVICE_ID,
        }

    def latest_state(self):
        return dict(self._last_state) if self._last_state else None

    def state_age_ms(self):
        if not self._last_state_at:
            return None
        return int((time.time() - self._last_state_at) * 1000)

    def wait_state(self, timeout_s: float):
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while self._last_state is None and time.monotonic() < deadline:
            time.sleep(0.02)
        return dict(self._last_state) if self._last_state else None

    def estop(self) -> bool:
        self._safe = True
        self._touch({"estop": True})
        return True

    def close(self):
        self.connected = False
        if self.on_disconnect:
            try:
                self.on_disconnect("host device closed")
            except Exception:
                pass

    def _touch(self, extra=None):
        self._last_state_at = time.time()
        self._last_state = {
            "type": "state", "device_id": self.DEVICE_ID,
            "body": {"device": self.DEVICE_ID, **(extra or {})},
            "legacy_seq": int(self._last_state_at * 1000),
        }
        if self.on_state:
            try:
                self.on_state(dict(self._last_state))
            except Exception:
                pass

    def _emit(self, cmd, ok, why, extra):
        if self.on_result:
            try:
                payload = dict(extra or {})
                payload["independent"] = False
                self.on_result(cmd, ok, why, payload)
            except Exception:
                pass


class HostFilesystemDriver(HostDesktopDriver):
    DEVICE_ID = "host://fs"

    def describe(self):
        d = super().describe()
        d["device_id"] = self.DEVICE_ID
        d["type"] = "filesystem"
        d["name"] = "CBAP Host Filesystem (allowlist)"
        return d


class HostDisplayDriver(_HostBase):
    DEVICE_ID = "host://display"
    NAME = "CBAP Host Display"

    def __init__(self, root: str | os.PathLike[str], enable: bool = True):
        super().__init__()
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.enabled = bool(enable)

    def describe(self):
        d = super().describe()
        d["actions"] = ["screenshot", "stat"]
        d["read_only"] = True
        d["root"] = str(self.root)
        return d

    def map_action(self, frame):
        op = (frame or {}).get("op")
        args = (frame or {}).get("args") or {}
        if op not in ("screenshot", "stat"):
            raise HostActionError("E_NOTSUP", f"display op not supported: {op}")
        return {"cmd": op, "args": args}

    def send(self, command):
        cmd = str((command or {}).get("cmd") or "")
        args = (command or {}).get("args") or {}
        if self._safe:
            self._emit(cmd, False, "E_SAFETY: display is stopped", {})
            return True
        if not self.enabled:
            self._emit(cmd, False, "E_SAFETY: display capture is disabled", {})
            return True
        try:
            if cmd == "stat":
                p = self._path(args.get("path", ""))
                if not p.is_file():
                    raise HostActionError("E_NOENT", "screenshot does not exist")
                return self._ok(cmd, {"path": str(p), "bytes": p.stat().st_size,
                                      "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
            if cmd != "screenshot":
                raise HostActionError("E_NOTSUP", f"unknown display command: {cmd}")
            out = self.root / f"screen-{int(time.time())}.png"
            env = dict(os.environ)
            env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("WAYLAND_DISPLAY", "wayland-0")
            # KDE Spectacle captures the Wayland desktop through the portal.
            proc = subprocess.run(
                ["spectacle", "-b", "-n", "-f", "-o", str(out)],
                capture_output=True, text=True, timeout=12, env=env,
                cwd=str(self.root),
            )
            if proc.returncode != 0 or not out.exists():
                raise HostActionError(
                    "E_IO", f"spectacle failed: {proc.stderr[-160:] or proc.stdout[-160:]}")
            data = out.read_bytes()
            self._touch({"last_capture": str(out), "bytes": len(data)})
            return self._ok(cmd, {
                "path": str(out), "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        except HostActionError as e:
            self._emit(cmd, False, f"{e.code}: {e.message}", {})
            return True
        except Exception as e:
            self._emit(cmd, False, f"E_IO: {type(e).__name__}: {e}", {})
            return True

    def _path(self, rel):
        if not isinstance(rel, str) or not rel or os.path.isabs(rel):
            raise HostActionError("E_INVAL", "relative path required")
        p = (self.root / rel).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise HostActionError("E_PERM", "path escapes display root")
        if p.is_symlink() or p.parent.is_symlink():
            raise HostActionError("E_PERM", "symlink not allowed")
        return p

    def _ok(self, cmd, extra):
        self._touch({"last_cmd": cmd})
        self._emit(cmd, True, None, extra)
        return True


class HostInputDriver(_HostBase):
    KIND = "mouse"
    DEVICE_ID = "host://input/mouse"
    NAME = "CBAP Host Mouse"

    def __init__(self, enable: bool = False):
        super().__init__()
        self.enabled = bool(enable)
        self.display = os.environ.get("DISPLAY", "")

    def describe(self):
        d = super().describe()
        d["transport"] = "x11/xwayland"
        d["actions"] = ["position", "move", "click", "scroll"] if self.KIND == "mouse" else ["type", "key"]
        d["enabled"] = self.enabled
        d["wayland_native"] = False
        return d

    def map_action(self, frame):
        op = (frame or {}).get("op")
        args = (frame or {}).get("args") or {}
        allowed = {"position", "move", "click", "scroll"} if self.KIND == "mouse" else {"type", "key"}
        if op not in allowed:
            raise HostActionError("E_NOTSUP", f"{self.KIND} op not supported: {op}")
        if not isinstance(args, dict):
            raise HostActionError("E_INVAL", "args must be object")
        return {"cmd": op, "args": args}

    def send(self, command):
        cmd = str((command or {}).get("cmd") or "")
        args = (command or {}).get("args") or {}
        if self._safe:
            self._emit(cmd, False, "E_SAFETY: input is stopped", {})
            return True
        if not self.enabled:
            self._emit(cmd, False, "E_SAFETY: input is disabled (--enable-input)", {})
            return True
        if not self.display:
            self._emit(cmd, False, "E_IO: DISPLAY is not set (X11/XWayland only)", {})
            return True
        try:
            if self.KIND == "mouse":
                if cmd == "position":
                    p = subprocess.run(["xdotool", "getmouselocation", "--shell"],
                                       capture_output=True, text=True, timeout=3,
                                       env=os.environ, check=False)
                    vals = dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)
                    return self._ok(cmd, {"x": int(vals.get("X", 0)), "y": int(vals.get("Y", 0))})
                if cmd == "move":
                    x, y = int(args.get("x")), int(args.get("y"))
                    if not (0 <= x <= 10000 and 0 <= y <= 10000):
                        raise HostActionError("E_INVAL", "x/y out of local bounds")
                    self._run(["xdotool", "mousemove", str(x), str(y)])
                    return self._ok(cmd, {"x": x, "y": y})
                if cmd == "click":
                    button = int(args.get("button", 1))
                    if button not in (1, 2, 3):
                        raise HostActionError("E_INVAL", "button must be 1..3")
                    self._run(["xdotool", "click", str(button)])
                    return self._ok(cmd, {"button": button})
                if cmd == "scroll":
                    direction = str(args.get("direction", "down"))
                    button = "4" if direction == "up" else "5" if direction == "down" else None
                    if not button:
                        raise HostActionError("E_INVAL", "direction must be up/down")
                    self._run(["xdotool", "click", button])
                    return self._ok(cmd, {"direction": direction})
            else:
                if cmd == "type":
                    text = args.get("text")
                    if not isinstance(text, str) or not text or len(text) > 200:
                        raise HostActionError("E_INVAL", "text must be 1..200 chars")
                    self._run(["xdotool", "type", "--clearmodifiers", "--delay", "8", "--", text])
                    return self._ok(cmd, {"chars": len(text)})
                if cmd == "key":
                    key = args.get("key")
                    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9+_-]{1,40}", key):
                        raise HostActionError("E_INVAL", "invalid key chord")
                    self._run(["xdotool", "key", "--clearmodifiers", key])
                    return self._ok(cmd, {"key": key})
        except HostActionError as e:
            self._emit(cmd, False, f"{e.code}: {e.message}", {})
            return True
        except Exception as e:
            self._emit(cmd, False, f"E_IO: {type(e).__name__}: {e}", {})
            return True
        self._emit(cmd, False, "E_NOTSUP", {})
        return True

    def _run(self, argv):
        p = subprocess.run(argv, capture_output=True, text=True, timeout=5,
                           env=os.environ, check=False)
        if p.returncode != 0:
            raise HostActionError("E_IO", p.stderr[-160:] or "xdotool failed")

    def _ok(self, cmd, extra):
        self._touch({"last_cmd": cmd})
        self._emit(cmd, True, None, extra)
        return True


class HostKeyboardDriver(HostInputDriver):
    KIND = "keyboard"
    DEVICE_ID = "host://input/keyboard"
    NAME = "CBAP Host Keyboard"


class HostMouseDriver(HostInputDriver):
    KIND = "mouse"
    DEVICE_ID = "host://input/mouse"
    NAME = "CBAP Host Mouse"
