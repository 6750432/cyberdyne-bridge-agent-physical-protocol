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
