# Generic MCP device driver

`MCPDeviceDriver` turns one MCP server into one CBAP device.

```text
MCP tool     -> CBAP action
MCP resource -> CBAP fact source
MCP server   -> one device (or a namespaced device group)
```

## Manifest

```json
{
  "device_id": "mcp://lab/light-01",
  "display_name": "Lab light",
  "transport": {
    "type": "stdio",
    "command": ["python3", "/path/light_mcp.py"],
    "cwd": "."
  },
  "tools": {
    "turn_on":  {"tool": "turn_on",  "args": {}},
    "turn_off": {"tool": "turn_off", "args": {}}
  },
  "facts": {
    "source": "tool",
    "tool": "get_state"
  },
  "estop": {"tool": "turn_off"},
  "poll_interval": 0.2
}
```

## Facts, not receipts

A tool call returning `ok: true` is only a receipt. The driver re-reads the
declared fact source after every action.

```python
driver.send({"op": "turn_on", "expect": {"on": True}})
```

The return is `True` only if:

```text
tool call succeeded
AND the independent fact source matches the expectation
```

If no fact source is declared:

```json
{"ok": false, "status": "unverifiable"}
```

## CLI probe

```bash
python3 tools/mcp_device_probe.py device.json \
  --op turn_on --expect '{"on":true}'
```

Exit codes:

```text
0  observed / verified
2  mismatch
3  unverifiable
4  driver / transport error
```

## Scope

Only stdio MCP in v0. HTTP/SSE and MCP resources can be added behind the same
`facts.source` contract.

## Security hardening

### Environment

The child MCP server no longer inherits the full parent environment by
default. It receives only:

```text
PATH, HOME, LANG, LC_ALL, LC_CTYPE, TMPDIR
```

Add explicit values under `transport.env`. To inherit the full environment
(the old behavior), set `transport.inherit_env: true` — not recommended for
third-party servers.

Optional process limits:

```json
"transport": {
  "rlimits": {"RLIMIT_NOFILE": 256}
}
```

### Manifest signature

```json
"signature": "<hmac-sha256 hex>"
```

Set `CBAP_MANIFEST_KEY` to the same key. The signature covers the manifest
without `signature` and `_manifest_path`.

```bash
export CBAP_REQUIRE_SIGNED_MANIFEST=1
```

rejects unsigned manifests.

### Tool / instruction pinning

On connect the driver hashes the advertised tool definitions and
`server/discover.instructions`. Optional pins:

```json
"pin_tools": {
  "tools_sha256": "<hex>",
  "instructions_sha256": "<hex>"
}
```

A mismatch refuses to connect.

### Estop evidence

Declare the postcondition:

```json
"estop": {
  "tool": "turn_off",
  "expect": {"on": false}
}
```

`driver.health()["estop_verified"]` is then `true` only when the fact source
matches. Without `expect`/`verify`, `safe_state` is `unknown`.

### Independent facts

Same MCP server:

```json
"facts": {
  "source": "tool",
  "tool": "get_state",
  "independent": true
}
```

Separate command/sensor (preferred when the MCP server is not trusted):

```json
"facts": {
  "source": "command",
  "command": ["python3", "/opt/sensor/read.py"],
  "independent": true
}
```

The command is argv-only (no shell), gets a small environment allowlist, and
must print one JSON value. `source: "resource"` is also supported.

`independent` is a declaration, not a proof. Use a separate device/sensor
channel when the MCP server itself is untrusted. A Kernel started with
`require_independent_facts=True` rejects results without the marker.

### Hardware estop hook

For a relay/PLC/GPIO path, declare an argv command that runs before the MCP
estop tool:

```json
"estop": {
  "hardware_command": ["/opt/cbap/relay-off"],
  "tool": "turn_off",
  "expect": {"on": false}
}
```

The hook must exit 0. If it fails, the driver returns false and the Kernel
marks `driver_ok=false`; this is still a software-triggered relay, not a
certified physical safety circuit.

### Sandbox

```json
"transport": {
  "sandbox": {"type": "bwrap", "writable_cwd": false}
}
```

`bwrap` or `nsjail` must be installed. If requested and unavailable, the
driver refuses to start. This is optional OS isolation, not a guarantee
against a kernel/hypervisor escape.

### Independent UID/GID

When the Kernel runs as root:

```json
"transport": {
  "run_as_uid": 65534,
  "run_as_gid": 65534,
  "inherit_env": false,
  "env_allowlist": ["PATH", "HOME"]
}
```

The child is dropped to that UID/GID before exec. Non-root requests fail
closed. This is not a full container; combine it with `sandbox` when the
platform supports it.

### Automatic tool pin

If `pin_tools` is absent, the first successful connect writes
`<manifest>.pins.json` (0600). Every later connect must match the advertised
tool definitions and instructions. A manifest `pin_tools` overrides the
sidecar.

### Estop evidence required

`describe.safety.estop` is true only when `estop.expect` or `estop.verify`
exists. An estop tool without a safe-state postcondition is not advertised as
Kernel-registerable safety.
