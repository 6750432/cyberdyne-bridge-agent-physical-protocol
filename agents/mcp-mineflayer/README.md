# MCP Mineflayer body

Status: **active / external**

```text
upstream:  external/mineflayer-mcp
driver:    agents/mcp-mineflayer/driver
device:    mcp://mc/MCPBody
transport: MCP stdio JSON-RPC 2.0
```

This subrepo is imported directly as
`agents.mcp-mineflayer.driver.driver`. There is no `drivers/mcp` shim.

Local smoke: `python3 agents/mcp-mineflayer/smoke.py`
Dashboard: `agents/mcp-mineflayer/tools/mcp_dashboard.py`.

The upstream place patch is kept at
`driver/patches/mineflayer-mcp-place.patch`.
