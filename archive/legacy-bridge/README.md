# Legacy bridge archive boundary

This directory records the legacy direct brain/hand path. It does **not**
duplicate or delete the live source yet.

```text
live physical source:
  agents/cyberdyne/brain/bridge.py
  agents/cyberdyne/hand/node/server.js
  agents/cyberdyne/plugins/

root compatibility shims:
  removed in M4
```

Status:

```text
M4 phase 1: frozen / inventory / migration wrapper available
M4 phase 2: root shims removed; default launcher -> bridge_cbap.py
M4 phase 3: old direct source retained read-only / no root entrypoint
```

The original `bridge.py` is intentionally still byte-for-byte pinned. The
migration wrapper is:

```text
agents/cyberdyne/brain/bridge_cbap.py
```

It preserves the legacy brain classes and replaces only `接线口` with
`CBAPHandAdapter`, so the brain runs through the Kernel instead of directly
opening the hand.

See `docs/M4-Legacy-Decision.md`.
