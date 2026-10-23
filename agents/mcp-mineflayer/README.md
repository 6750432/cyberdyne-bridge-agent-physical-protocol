# MCP Mineflayer body

Status: **active / external**

```text
upstream:  external/mineflayer-mcp
driver:    drivers/mcp
device:    mcp://mc/MCPBody
transport: MCP stdio JSON-RPC 2.0
```

The `MCPDriver` is still in the main repository during the migration window.
Its current paths and imports must not change until the plugin boundary is
tested.

The upstream place patch is kept at
`drivers/mcp/patches/mineflayer-mcp-place.patch`.
