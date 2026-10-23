# Repository layout and migration boundary

Status: **phase 1 — classification + driver API; runtime paths unchanged**

## Target

```text
cyberdyne-bridge/                  main repository = CBAP only
  kernel/                          protocol, kernel, leases, safety, audit
  spec/                            CBAP contracts
  tests/                           conformance tests
  tools/                           generic CBAP tooling
  docs/
  agents/                          logical agent sub-repositories
    cyberdyne/
    mcp-mineflayer/
    mindcraft/
    voyager/
  archive/
    alice/                         unbuilt, not active
```

## Active agents

```text
cyberdyne       our own brain/hand
mcp-mineflayer  MCP body
mindcraft       autonomous agent, state/prompt/stop
voyager         bridge only, not Voyager Python agent
```

## Why not physically move yet

The current `KernelServer`, tests, and tools still import concrete drivers:

```text
drivers.mc
drivers.mcp
drivers.dataflow
drivers.mindcraft
drivers.voyager
```

Moving them now would break:

```text
tests.cbap.test_gateway
tests.cbap.test_multi_device
tests.cbap.test_mcp_driver
tools/*
```

## Migration sequence

```text
1. Driver API + manifest discovery                     [this phase]
2. Add compatibility shims for existing imports        [next]
3. Move agent-owned adapters behind package boundaries
4. Move tests per agent; keep generic conformance in main
5. Move our own bridge.py / node/ with service-path shims
6. Re-run full suite
7. Only then consider real git submodules / remotes
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
