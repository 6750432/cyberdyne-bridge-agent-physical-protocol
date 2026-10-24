#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared onboarding registry helpers for Kernel and Console."""
from __future__ import annotations

import json
import os
from pathlib import Path


def state_path(registry_dir: str | os.PathLike) -> Path:
    return Path(registry_dir) / "registry.json"


def load_state(registry_dir: str | os.PathLike) -> dict:
    try:
        data = json.loads(state_path(registry_dir).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("devices"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"devices": {}}


def enabled(name: str, state: dict | None = None) -> bool:
    state = state or {}
    item = (state.get("devices") or {}).get(name) or {}
    return bool(item.get("enabled", True))


def enabled_manifests(registry_dir: str | os.PathLike) -> list[Path]:
    root = Path(registry_dir)
    state = load_state(root)
    out: list[Path] = []
    try:
        paths = sorted(root.glob("*.json"))
    except OSError:
        return out
    for p in paths:
        if p.name == "registry.json" or not enabled(p.stem, state):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("device_id"):
            out.append(p)
    return out
