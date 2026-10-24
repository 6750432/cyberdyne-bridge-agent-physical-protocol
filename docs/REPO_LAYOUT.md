# Repository layout and migration boundary

Status: **M4 — own-agent root shims removed; legacy source frozen**

## Current

```text
cyberdyne-bridge/                  main repository = CBAP
  kernel/                          protocol, kernel, leases, safety, audit
  console/                         local operator host (status + estop)
  spec/                            CBAP contracts
  tests/                           conformance tests
  tools/                           generic CBAP + integration probes
  docs/
  agents/
    cyberdyne/
      brain/bridge.py
      hand/node/server.js
      plugins/
      tools/
      config.json
      smoke.py
      agent.json
    mcp-mineflayer/
      driver/
      tools/
      docs/
      smoke.py
      agent.json
    mindcraft/
      adapter/
      tools/
      docs/
      smoke.py
      agent.json
    voyager/
      adapter/
      tools/
      docs/
      smoke.py
      agent.json
  archive/
    alice/
      bridge/CbapBridge.java
      agent.json                 # archived, not active
```

## Active agents

```text
cyberdyne       legacy brain, CBAP wrapper entrypoint; hand via McDriver
mcp-mineflayer  MCP body; MCP stdio JSON-RPC
mindcraft       autonomous agent; state / prompt / stop
voyager         bridge only; not Voyager Python agent
```

Alice is archived: source-only, not compiled, not smoke-tested.

## Compatibility shims

M4 removed the own-agent root shims:

```text
bridge.py / config.json / node / 外挂   removed
```

Use physical paths or the CBAP wrapper:

```text
agents/cyberdyne/brain/bridge_cbap.py
agents/cyberdyne/tools/启动大脑.sh
agents/cyberdyne/tools/启动手.sh
```

MCP, Mindcraft, Voyager and Alice are addressed by their real paths.
The old direct brain remains frozen under its physical path for reference.

## Migration status

```text
1. Driver API + manifest discovery                     [done]
2. Physical agent code moved                           [done]
3. Compatibility shims for existing paths              [done]
4. Agent tools/docs moved into agent subrepos          [done]
5. Independent per-agent smoke tests                   [done]
6. External callers moved off shims                    [done]
7. External agent shims removed                        [done]
8. Own legacy path constants migrated                  [done]
9. M4 legacy bridge frozen / CBAP wrapper              [done]
10. Root own-agent shims removed                       [done]
11. Old direct source retained as frozen archive       [done]
12. Decide whether to use real git submodules/remotes  [later]
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
agent-specific smoke test / tools / docs
```

The authoritative machine-readable manifests live in:

```text
agents/*/agent.json
archive/alice/agent.json
```

Discovery is implemented in `kernel/driver_api.py`; it only reads manifests
and imports a factory on explicit request.

## Verification (2026-10-24)

```text
CBAP conformance: 101/101 passed
console tests:    5 passed (login / approvals / onboarding / history)
console TLS:      1 passed (mTLS operator identity)
registry hotplug: 1 passed (load / disable / unload)
legacy wrapper:   1 passed (bridge_cbap boundary)
transport tests:  2 passed (TCP/TLS/mTLS)
security tests:   14 passed (socket/token/policy/audit/fencing/limits)
MCP device tests: 14 passed
brain launcher:   bash agents/cyberdyne/tools/启动大脑.sh --help  -> ok
legacy brain:     agents/cyberdyne/brain/bridge_cbap.py --help -> ok
launcher syntax:  bash -n on all three root launch shims -> ok
Alice probe:      archive/alice/tools/alice_bridge_probe.py --help -> ok
JS tests:         22 + 6 + 8 passed
external shims:   drivers/{mcp,mindcraft,voyager,alice},
                  tools/{mcp_dashboard,mindcraft_cbap,voyager_*,alice_bridge_probe}
                  are removed
```

The legacy suite is archived at `archive/legacy-bridge/跑全部.sh`; it is not
part of the main CI. The frozen direct source still has pre-existing
functional failures (8 assertions), recorded as legacy state:

```text
测工具查表.py      D2 pre-existing
测常识.py          N1/N3/N4 pre-existing
测生存常识.py      B15b/G2/C13/R5b pre-existing
```

The old fingerprint assertions were stale: they expected `a649...` although
the checked-in bridge changed in `2ef1ab5`. Tests/docs were updated to the
current baseline; the frozen direct source itself was not touched.

The JS path failure was caused by the move (block-table lookup was three
directories up); `proto_body.js` now also looks in
`agents/cyberdyne/plugins/常识/方块交互表.json`, and all 22 JS tests pass.

M4 moved the default brain entrypoint to
`agents/cyberdyne/brain/bridge_cbap.py`, which keeps the old brain and swaps
only `接线口` for `CBAPHandAdapter`. Root shims are gone. The old direct
source remains frozen under its physical path and is not a controller.
