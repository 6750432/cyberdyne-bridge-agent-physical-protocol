# Repository layout and migration boundary

Status: **phase 2 — physical agent code moved; compatibility shims in place**

## Current

```text
cyberdyne-bridge/                  main repository = CBAP
  kernel/                          protocol, kernel, leases, safety, audit
  spec/                            CBAP contracts
  tests/                           conformance tests
  tools/                           generic CBAP + integration probes
  docs/
  agents/
    cyberdyne/
      brain/bridge.py
      hand/node/server.js
      plugins/
      config.json
      agent.json
    mcp-mineflayer/
      driver/
      agent.json
    mindcraft/
      adapter/
      agent.json
    voyager/
      adapter/
      agent.json
  archive/
    alice/
      bridge/CbapBridge.java
      agent.json                 # archived, not active
```

## Active agents

```text
cyberdyne       our own brain/hand; direct UDS is legacy, hand can be wrapped by McDriver
mcp-mineflayer  MCP body; MCP stdio JSON-RPC
mindcraft       autonomous agent; state / prompt / stop
voyager         bridge only; not Voyager Python agent
```

Alice is archived: source-only, not compiled, not smoke-tested.

## Compatibility shims

Old paths are symlinks, so services, imports, and tests keep working:

```text
bridge.py             -> agents/cyberdyne/brain/bridge.py
config.json           -> agents/cyberdyne/config.json
node                  -> agents/cyberdyne/hand/node
外挂                   -> agents/cyberdyne/plugins
drivers/mcp           -> agents/mcp-mineflayer/driver
drivers/mindcraft     -> agents/mindcraft/adapter
drivers/voyager       -> agents/voyager/adapter
drivers/alice         -> archive/alice/bridge
```

## Why shims instead of changing imports now

The current kernel/tests/tools still use concrete paths such as:

```text
drivers.mcp.driver
drivers.mc.driver
tools/mindcraft_cbap.py
node/server.js
```

The symlinks preserve those paths while the physical files are separated.
Removing a shim is a separate migration after every caller has moved.

## Migration status

```text
1. Driver API + manifest discovery                     [done]
2. Physical agent code moved                           [done]
3. Compatibility shims for existing paths              [done]
4. Full conformance suite                              [60/60 passed]
5. Remove shims after callers migrate                  [next]
6. Decide whether to use real git submodules/remotes   [later]
```

## Contract

Main owns:

```text
CBAP-U: agent-facing UDS newline JSON
CBAP-D: driver-facing adapter boundary
leases, FIFO waiters, release, estop, recovery
facts + verify
audit
```

Agent owns:

```text
transport adapter / driver
device/mapping
upstream patch
agent-specific smoke test
```

The authoritative machine-readable manifests live in:

```text
agents/*/agent.json
archive/alice/agent.json
```

Discovery is implemented in `kernel/driver_api.py`; it only reads manifests
and imports a factory on explicit request.
