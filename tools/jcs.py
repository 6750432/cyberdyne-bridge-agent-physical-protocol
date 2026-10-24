#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RFC 8785-style JSON canonicalization for CBAP replay fingerprints.

This is the Python side of the cross-language JCS check. It intentionally
covers the CBAP data types: null/bool/int/float/string/array/object, finite
numbers, UTF-8 strings, and object keys sorted by UTF-16 code units.

Usage:
  python3 tools/jcs.py --canonical '{"b":1,"a":2}'
  python3 tools/jcs.py --hash '{"b":1,"a":2}'
  echo '{"b":1,"a":2}' | python3 tools/jcs.py --hash
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from decimal import Decimal
from typing import Any


def _number(value: int | float) -> str:
    if isinstance(value, bool):
        raise TypeError("bool is not a JSON number")
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, float):
        raise TypeError(f"not a JSON number: {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError("JCS does not allow NaN/Infinity")
    if value == 0:
        return "0"
    abs_value = abs(value)
    # ECMAScript Number::toString uses fixed notation in [1e-6, 1e21).
    if 1e-6 <= abs_value < 1e21:
        text = format(Decimal(repr(value)), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    text = repr(value).lower()
    if "e" in text:
        mantissa, exponent = text.split("e", 1)
        sign = ""
        if exponent.startswith(("+", "-")):
            sign, exponent = exponent[0], exponent[1:]
        exponent = exponent.lstrip("0") or "0"
        return f"{mantissa}e{sign}{exponent}"
    return text


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: str(k).encode("utf-16-be"))
        parts = []
        for key in keys:
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            parts.append(_string(key) + ":" + canonical(value[key]))
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return canonical(value).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs="?", help="JSON text; stdin if omitted")
    ap.add_argument("--canonical", action="store_true", help="print canonical JSON")
    ap.add_argument("--hash", action="store_true", help="print sha256")
    args = ap.parse_args()
    raw = args.json if args.json is not None else sys.stdin.read()
    if args.json is not None and Path(args.json).is_file():
        raw = Path(args.json).read_text(encoding="utf-8")
    value = json.loads(raw)
    if args.canonical:
        print(canonical(value))
    elif args.hash:
        print(fingerprint(value))
    else:
        print(canonical(value))
        print(fingerprint(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
