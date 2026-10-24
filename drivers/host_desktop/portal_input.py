#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Native Wayland input through xdg-desktop-portal RemoteDesktop.

This is deliberately a *consent-first* backend:

  * it never uses uinput or root
  * the portal shows the compositor's own permission dialog
  * it is created only when the host bridge is started with
    --enable-input --input-backend portal
  * if the portal is unavailable or the user cancels, every action fails
    closed with E_SAFETY

The tests only exercise availability/default-deny paths.  A real test of
Notify* requires a logged-in Wayland session and an operator clicking the
portal prompt; claiming otherwise would be dishonest.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"


class PortalError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def portal_session_bus() -> Any:
    """Connect to the logged-in user's session bus, not the agent shell bus."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
    os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
    try:
        import dbus  # type: ignore
        import dbus.mainloop.glib  # type: ignore  # noqa: F401
        from gi.repository import GLib  # type: ignore
    except Exception as e:  # pragma: no cover - environment dependent
        raise PortalError("E_NOTSUP", f"dbus/gi unavailable: {e}") from e
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    return dbus, GLib


class PortalRemoteDesktop:
    def __init__(self, timeout_s: float = 60.0):
        self.timeout_s = max(5.0, float(timeout_s))
        self.dbus, self.GLib = portal_session_bus()
        self.bus = self.dbus.SessionBus()
        if not self.bus.name_has_owner(PORTAL_BUS):
            raise PortalError("E_SAFETY", "xdg-desktop-portal is not running")
        self.obj = self.bus.get_object(PORTAL_BUS, PORTAL_PATH)
        self.remote = self.dbus.Interface(self.obj, REMOTE_DESKTOP)
        self._responses: dict[str, tuple[int, dict]] = {}
        self._loop = None
        self.bus.add_signal_receiver(
            self._on_response, signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path_keyword="path")
        self.session_handle: str | None = None
        self.streams: list = []

    def _on_response(self, response, results, path=None):
        self._responses[str(path or "")] = (int(response), dict(results or {}))
        if self._loop is not None and self._loop.is_running():
            self._loop.quit()

    def available_device_types(self) -> int:
        try:
            props = self.dbus.Interface(self.obj,
                                        "org.freedesktop.DBus.Properties")
            return int(props.Get(REMOTE_DESKTOP, "AvailableDeviceTypes"))
        except Exception as e:
            raise PortalError("E_SAFETY", f"portal property failed: {e}") from e

    def _request(self, method, *args, timeout_s: float | None = None) -> dict:
        token = "cbap_" + uuid.uuid4().hex
        # Add handle_token to the final options dict when present.
        args = list(args)
        if args and isinstance(args[-1], dict):
            opts = dict(args[-1])
            opts.setdefault("handle_token", token)
            args[-1] = opts
        request_path = str(method(*args))
        deadline = time.monotonic() + (timeout_s or self.timeout_s)
        if request_path not in self._responses:
            self._loop = self.GLib.MainLoop()
            def expire():
                if self._loop is not None and self._loop.is_running():
                    self._loop.quit()
                return False
            timer = self.GLib.timeout_add(
                max(1, int((deadline - time.monotonic()) * 1000)), expire)
            self._loop.run()
            try:
                self.GLib.source_remove(timer)
            except Exception:
                pass
        if request_path not in self._responses:
            raise PortalError("E_TIMEOUT", "portal response timeout")
        response, results = self._responses.pop(request_path)
        if response != 0:
            raise PortalError("E_SAFETY",
                              f"portal request was not approved (response={response})")
        return results

    def start(self) -> None:
        if self.session_handle:
            return
        # CreateSession can complete without a user prompt.
        results = self._request(
            self.remote.CreateSession, self.dbus.Dictionary({}, signature="sv"))
        handle = results.get("session_handle")
        if not handle:
            raise PortalError("E_SAFETY", "portal did not return a session handle")
        session = str(handle)
        # keyboard (1) + pointer (2)
        self._request(
            self.remote.SelectDevices, self.dbus.ObjectPath(session),
            self.dbus.Dictionary({"types": self.dbus.UInt32(3),
                                  "handle_token": "cbap_devices_" +
                                  uuid.uuid4().hex}, signature="sv"))
        # This is the compositor's explicit user-consent dialog.
        results = self._request(
            self.remote.Start, self.dbus.ObjectPath(session), "",
            self.dbus.Dictionary({"handle_token": "cbap_start_" +
                                  uuid.uuid4().hex}, signature="sv"),
            timeout_s=self.timeout_s)
        self.session_handle = session
        streams = results.get("streams") or []
        self.streams = list(streams)

    def _session(self) -> Any:
        self.start()
        return self.dbus.ObjectPath(self.session_handle)

    def motion_relative(self, dx: float, dy: float) -> None:
        self.remote.NotifyPointerMotion(
            self._session(), self.dbus.Dictionary({}, signature="sv"),
            float(dx), float(dy))

    def button(self, button: int, pressed: bool) -> None:
        self.remote.NotifyPointerButton(
            self._session(), self.dbus.Dictionary({}, signature="sv"),
            int(button), self.dbus.UInt32(1 if pressed else 0))

    def axis(self, dx: float, dy: float) -> None:
        self.remote.NotifyPointerAxis(
            self._session(), self.dbus.Dictionary({}, signature="sv"),
            float(dx), float(dy))

    def keysym(self, keysym: int, pressed: bool) -> None:
        self.remote.NotifyKeyboardKeysym(
            self._session(), self.dbus.Dictionary({}, signature="sv"),
            int(keysym), self.dbus.UInt32(1 if pressed else 0))

    def close(self) -> None:
        if not self.session_handle:
            return
        try:
            session = self.bus.get_object(PORTAL_BUS, self.session_handle)
            self.dbus.Interface(session, "org.freedesktop.portal.Session").Close()
        except Exception:
            pass
        self.session_handle = None


# Small, explicit keysym table.  Text typing is intentionally not mapped:
# arbitrary text through a remote desktop portal needs a full keyboard layout
# policy and is not part of this first native-Wayland slice.
KEYSYMS = {
    "return": 0xFF0D, "enter": 0xFF0D, "escape": 0xFF1B, "esc": 0xFF1B,
    "tab": 0xFF09, "space": 0x20, "backspace": 0xFF08, "delete": 0xFFFF,
    "home": 0xFF50, "end": 0xFF57, "pageup": 0xFF55, "pagedown": 0xFF56,
    "left": 0xFF51, "right": 0xFF53, "up": 0xFF52, "down": 0xFF54,
    "ctrl": 0xFFE3, "control": 0xFFE3, "shift": 0xFFE1, "alt": 0xFFE9,
    "super": 0xFFEB, "meta": 0xFFEB,
}


def parse_chord(chord: str) -> list[int]:
    """Map a conservative key chord to keysyms (no text/Unicode injection)."""
    parts = [p.lower() for p in str(chord).split("+") if p.strip()]
    if not parts or len(parts) > 4:
        raise PortalError("E_INVAL", "unsupported key chord")
    out = []
    for p in parts:
        if p in KEYSYMS:
            out.append(KEYSYMS[p])
        elif len(p) == 1 and p.isalnum():
            out.append(ord(p.lower()))
        else:
            raise PortalError("E_INVAL", f"unsupported portal key: {p}")
    return out
