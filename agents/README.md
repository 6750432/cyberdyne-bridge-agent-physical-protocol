# Agent sub-repositories

This directory is the logical sub-repository layer. It does **not** change
runtime imports yet; the physical code move happens after the driver plugin
boundary is covered by tests.

## Active four

| id | ownership | device | surface | runtime |
|---|---|---|---|---|
| `cyberdyne` | ours | `mc://bot/DeepSeek` | legacy brain/hand | direct UDS; hand can be wrapped by `McDriver` |
| `mcp-mineflayer` | external | `mcp://mc/MCPBody` | MCP tools | MCP stdio JSON-RPC |
| `mindcraft` | external | `mc://mind/Mindy` | state / prompt / stop | MindServer socket.io |
| `voyager` | external | `mc://voyager/bot` | state / exec / forward / say / stop | HTTP bridge |

## Archived

`alice` is under `archive/alice`, not active: source-only, not compiled, not
smoke-tested.

## Boundary

Main repository owns:

```text
CBAP protocol / kernel / leases / safety / audit / conformance / driver API
```

Agent sub-repository owns:

```text
adapter or driver implementation
device.json / mapping.json
upstream patches
launch / smoke test / agent-specific docs
```

## Migration rule

Until the physical move is complete:

```text
do not move bridge.py / node/
do not move drivers/mcp|mindcraft|voyager
keep existing imports and tests green
```

The `agent.json` manifests are the contract for the future loader.
