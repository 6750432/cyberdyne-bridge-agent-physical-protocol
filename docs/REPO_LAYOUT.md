# Repository layout and migration boundary

Status: **phase 4 — external agent shims removed; own legacy shims remain**

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
cyberdyne       our own brain/hand; direct UDS is legacy, hand can be wrapped by McDriver
mcp-mineflayer  MCP body; MCP stdio JSON-RPC
mindcraft       autonomous agent; state / prompt / stop
voyager         bridge only; not Voyager Python agent
```

Alice is archived: source-only, not compiled, not smoke-tested.

## Compatibility shims

External agent shims are removed. Remaining root shims are only for our own
legacy brain/hand/plugin constants:

```text
bridge.py   -> agents/cyberdyne/brain/bridge.py
config.json -> agents/cyberdyne/config.json
node        -> agents/cyberdyne/hand/node
外挂         -> agents/cyberdyne/plugins
```

MCP, Mindcraft, Voyager and Alice are addressed by their real paths.

## Why shims instead of changing imports now

The current kernel/tests/tools still use concrete paths such as:

```text
drivers.mc.driver
agents/mcp-mineflayer.driver.driver
agents/mindcraft/tools/mindcraft_cbap.py
agents/cyberdyne/hand/node/server.js
```

The symlinks preserve those paths while the physical files are separated.
Removing a shim is a separate migration after every caller has moved.

## Migration status

```text
1. Driver API + manifest discovery                     [done]
2. Physical agent code moved                           [done]
3. Compatibility shims for existing paths              [done]
4. Agent tools/docs moved into agent subrepos          [done]
5. Independent per-agent smoke tests                   [done]
6. External callers moved off shims                    [done]
7. External agent shims removed                        [done]
8. Own legacy path constants migrated                  [next]
9. Decide whether to use real git submodules/remotes   [later]
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
CBAP conformance: 98/98 passed
console tests:    5 passed (login / Host+Origin / estop+audit)
transport tests:  2 passed (TCP/TLS/mTLS)
security tests:   14 passed (socket/token/policy/audit/fencing/limits)
MCP device tests: 14 passed
brain launcher:   bash tools/启动大脑.sh --help  -> ok
launcher syntax:  bash -n on all three root launch shims -> ok
Alice probe:      archive/alice/tools/alice_bridge_probe.py --help -> ok
JS tests:         22 + 6 + 8 passed
external shims:   drivers/{mcp,mindcraft,voyager,alice},
                  tools/{mcp_dashboard,mindcraft_cbap,voyager_*,alice_bridge_probe}
                  are removed
```

`tools/跑全部.sh` now passes the bridge fingerprint gate (`658c947ec7f33d37`)
and all JS tests. Three legacy files still have pre-existing functional
failures (8 assertions); they are not CBAP conformance failures:

```text
测工具查表.py      D2 pre-existing
测常识.py          N1/N3/N4 pre-existing
测生存常识.py      B15b/G2/C13/R5b pre-existing
```

The old fingerprint assertions were stale: they expected `a649...` although
the checked-in bridge changed in `2ef1ab5`. Tests/docs were updated to the
current baseline; `bridge.py` itself was not touched.

The JS path failure was caused by the move (block-table lookup was three
directories up); `proto_body.js` now also looks in
`agents/cyberdyne/plugins/常识/方块交互表.json`, and all 22 JS tests pass.

Own legacy shims remain because `bridge.py`, `node` and `外挂` are still
hardcoded by the old brain/hand/plugin code. They are not external-agent
shims.
