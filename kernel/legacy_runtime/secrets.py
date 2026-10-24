#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small secret-provider indirection.

Backends:
  env      (default, backwards compatible)
  file     CBAP_SECRET_FILE, a 0600 JSON object
  keyring  optional Python keyring package

A configured backend that is unavailable fails closed; it never silently
falls back to env.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class SecretError(RuntimeError):
    pass


def get_secret(name: str, default: str | None = None) -> str | None:
    backend = (os.environ.get("CBAP_SECRET_BACKEND") or "env").lower()
    if backend == "env":
        return os.environ.get(name, default)
    if backend == "file":
        path = os.environ.get("CBAP_SECRET_FILE")
        if not path:
            raise SecretError("CBAP_SECRET_FILE is required for file backend")
        p = Path(path)
        try:
            st = p.stat()
            if st.st_mode & 0o077:
                raise SecretError("secret file must be mode 0600")
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SecretError(f"cannot read secret file: {e}")
        return str(data.get(name, default)) if data.get(name) is not None else default
    if backend == "keyring":
        try:
            import keyring
        except Exception as e:
            raise SecretError(f"keyring backend unavailable: {e}")
        value = keyring.get_password(os.environ.get("CBAP_KEYRING_SERVICE", "cbap"), name)
        return value if value is not None else default
    raise SecretError(f"unknown secret backend: {backend}")
