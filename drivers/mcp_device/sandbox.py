#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional OS-level sandbox wrapper for MCP stdio children.

This is deliberately opt-in: CBAP runs in many environments where bwrap or
nsjail is unavailable.  When requested, absence is a hard failure, not a
silent fallback.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    pass


def wrap_command(command: list[str], spec: dict | None,
                 cwd: str | None) -> list[str]:
    if not spec:
        return list(command)
    if isinstance(spec, str):
        spec = {"type": spec}
    kind = str(spec.get("type") or "").strip()
    if not kind or kind == "none":
        return list(command)
    if kind == "bwrap":
        exe = shutil.which("bwrap")
        if not exe:
            raise SandboxUnavailable("bwrap requested but not installed")
        args = [exe, "--die-with-parent", "--new-session",
                "--unshare-pid", "--unshare-net",
                "--ro-bind", "/", "/", "--dev", "/dev",
                "--proc", "/proc", "--tmpfs", "/tmp"]
        if cwd:
            args += ["--chdir", str(cwd)]
            if spec.get("writable_cwd"):
                args += ["--bind", str(cwd), str(cwd)]
        return args + ["--"] + list(command)
    if kind == "nsjail":
        exe = shutil.which("nsjail")
        if not exe:
            raise SandboxUnavailable("nsjail requested but not installed")
        args = [exe, "--quiet", "--disable_clone_newnet",
                "--time_limit", str(int(spec.get("time_limit_s", 300)))]
        if cwd:
            args += ["--cwd", str(cwd)]
        return args + ["--"] + list(command)
    raise SandboxUnavailable(f"unknown sandbox type: {kind}")
