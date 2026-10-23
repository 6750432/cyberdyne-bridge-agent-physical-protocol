# Agent sub-repositories

This directory is the logical sub-repository layer. It does **not** change
runtime imports yet; the physical code move happens after the driver plugin
boundary is covered by tests.

## Active four

| id | ownership | device | surface | runtime |
|---|---|---|---|---|
| `cyberdyne` | ours | `mc://bot/DeepSeek` | legacy brain/hand | `agents/cyberdyne/`; direct UDS; hand can be wrapped by `McDriver` |
| `mcp-mineflayer` | external | `mcp://mc/MCPBody` | MCP tools | `agents/mcp-mineflayer/driver/`; MCP stdio JSON-RPC |
| `mindcraft` | external | `mc://mind/Mindy` | state / prompt / stop | `agents/mindcraft/adapter/`; MindServer socket.io |
| `voyager` | external | `mc://voyager/bot` | state / exec / forward / say / stop | `agents/voyager/adapter/`; HTTP bridge |

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

External agent shims are removed. The remaining root shims are only for our own
legacy brain/hand/plugin constants:

```text
bridge.py / node / 外挂 / config.json -> agents/cyberdyne
```

Keep them until bridge/hand/plugin path constants are migrated.

Each active subrepo also owns a local `smoke.py`; the main conformance suite
runs all four through `tests/cbap/test_agent_smoke.py`.

The `agent.json` manifests are the contract for the future loader.
