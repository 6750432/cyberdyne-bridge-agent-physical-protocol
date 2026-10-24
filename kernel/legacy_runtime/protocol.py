#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP v1 wire helpers. Standard library only.

This module only knows the envelope; it does not know Minecraft.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

PROTOCOL_VERSION = "1.0"
MAX_FRAME = 64 * 1024
SUPPORTED_FEATURES = ("poll_filter",)

ERROR_CODES = frozenset({
    "E_VERSION", "E_PROTOCOL", "E_AUTH", "E_PERM", "E_NOENT", "E_BUSY",
    "E_AGAIN", "E_TIMEOUT", "E_INVAL", "E_NOTSUP", "E_IO", "E_CANCELED",
    "E_SAFETY", "E_STALE", "E_FRAME", "E_INTERNAL",
})


def now_ms() -> int:
    return int(time.time() * 1000)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def new_id(prefix: str = "m") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def error(code: str, message: str, retryable: bool = False,
          detail: dict | None = None) -> dict:
    if code not in ERROR_CODES:
        raise ValueError(f"unknown CBAP error code: {code}")
    out: dict[str, Any] = {"code": code, "message": str(message)[:500],
                           "retryable": bool(retryable)}
    if detail:
        out["detail"] = detail
    return out


def base(type_: str, **fields: Any) -> dict:
    msg: dict[str, Any] = {"v": PROTOCOL_VERSION, "type": type_, "ts": now_ms()}
    msg.update(fields)
    return msg


def result(req_id: str, ok: bool, payload: dict | None = None,
           facts: dict | None = None, err: dict | None = None) -> dict:
    msg = base("result", id=req_id, ok=bool(ok))
    if payload:
        msg["payload"] = payload
    if facts:
        msg["facts"] = facts
    if err:
        msg["error"] = err
    return msg


def event(kind: str, payload: dict | None = None, seq: int = 0) -> dict:
    msg = base("event", seq=int(seq), kind=str(kind))
    if payload:
        msg["payload"] = payload
    return msg


def state(seq: int, device_id: str, payload: dict,
          t_mono: int | None = None) -> dict:
    msg = base("state", seq=int(seq), device_id=device_id,
               payload=payload)
    if t_mono is not None:
        msg["t_mono"] = int(t_mono)
    return msg


def encode(obj: dict) -> bytes:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_FRAME:
        raise ValueError(f"frame too large: {len(data)} > {MAX_FRAME}")
    return data + b"\n"


def send_line(sock, obj: dict) -> None:
    sock.sendall(encode(obj))


def parse_line(line: bytes) -> dict:
    if len(line) > MAX_FRAME:
        raise ValueError("frame too large")
    obj = json.loads(line.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("message must be an object")
    return obj
