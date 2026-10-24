#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sign an MCP device manifest with HMAC-SHA256.

Usage:
  CBAP_MANIFEST_KEY=... python3 tools/sign_mcp_manifest.py manifest.json
  python3 tools/sign_mcp_manifest.py manifest.json --key ... --write

The signature covers the manifest without `signature` and `_manifest_path`.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def sign(manifest: dict, key: str) -> str:
    body = {k: v for k, v in manifest.items()
            if k not in ("signature", "_manifest_path")}
    return hmac.new(key.encode("utf-8"), canonical(body).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--key", default=os.environ.get("CBAP_MANIFEST_KEY", ""))
    ap.add_argument("--write", action="store_true",
                    help="write signature into the manifest atomically")
    a = ap.parse_args()
    if not a.key:
        print("CBAP_MANIFEST_KEY or --key is required", file=sys.stderr)
        return 2
    p = Path(a.manifest)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("manifest must be a JSON object", file=sys.stderr)
        return 2
    sig = sign(data, a.key)
    if not a.write:
        print(sig)
        return 0
    data["signature"] = sig
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
    print(sig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
