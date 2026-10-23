# MCP Mineflayer body

Status: **active / external**

```text
upstream:  external/mineflayer-mcp
driver:    agents/mcp-mineflayer/driver
device:    mcp://mc/MCPBody
transport: MCP stdio JSON-RPC 2.0
```

The root `drivers/mcp` path is a compatibility symlink to this subrepo.
Existing tests and tools continue to import `drivers.mcp.driver`.

The upstream place patch is kept at
`driver/patches/mineflayer-mcp-place.patch`.
