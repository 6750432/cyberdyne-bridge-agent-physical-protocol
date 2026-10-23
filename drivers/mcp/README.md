# MCP driver · 把真实 MCP MC Agent 变成 CBAP 外设

第一刀选择 **MCP**，目标是 [`swaynos/mineflayer-mcp`](https://github.com/swaynos/mineflayer-mcp)：

- 它是一个真实的外部进程，自带 Mineflayer bot；
- 官方 API 是标准 MCP stdio（JSON-RPC 2.0）；
- 9 个工具 / 6 个资源，正好能映射到 CBAP 的 body / world / inventory / chat；
- 需要一个小的 `place` 兼容 patch（见下）；`bridge.py` 和 `node/server.js` 不改。

## 为什么不是 Mindcraft

Mindcraft 是“LLM 规划器 + Mineflayer 动作库”，要把它变成外设，必须截获它内部的动作队列/状态对象，侵入性更高。MCP server 已经有稳定的公开工具边界，第一刀风险更低。

## 安装外部 server

```bash
git clone https://github.com/swaynos/mineflayer-mcp.git
cd mineflayer-mcp
npm install
```

外部 server 需要一个合法的 Minecraft 用户名（只能用字母/数字/下划线，不能有 `-`）。本项目实测：

```bash
node src/index.js \
  --host 127.0.0.1 --port 25565 \
  --username MCPBody --version 1.21.1 \
  --lock /tmp/cbap-mcp.lock --log-level warn
```

## MCP place patch（必要）

原版 `mineflayer-mcp` 在生存模式下会把手中的镐子当方块发送，导致
`server did not confirm placement ... block is "air"`。

应用本仓库补丁：

```bash
cd /path/to/mineflayer-mcp
patch -p1 < /path/to/cyberdyne-bridge/drivers/mcp/patches/mineflayer-mcp-place.patch
node --check src/bot.js
node --check src/tools.js
```

修复内容：只选可放置方块、可选 `itemName`、hotbar 直接选择、
公开 `bot.placeBlock` + `_genericPlace` 回退、300ms 确认等待。
详见 `docs/CBAP-MCP-place修复.md`。

## 启动 CBAP dashboard

```bash
export CBAP_MCP_SERVER=/path/to/mineflayer-mcp
export CBAP_NODE_BIN=$(command -v node)
python3 tools/mcp_dashboard.py \
  --server-path "$CBAP_MCP_SERVER" \
  --node "$CBAP_NODE_BIN" \
  --http-port 8123
```

打开 `http://127.0.0.1:8123`。它会：

1. 拉起外部 MCP server；
2. 通过 stdio 调 `initialize` / `tools/list`；
3. 用 `status`、`observe`、`inventory` 建立 CBAP state；
4. 通过 CBAP `write` 注入真实 `chat` 和 `move`；
5. 把 MCP 工具流量、CBAP syscall、健康状态画在 dashboard 上。

## Dashboard 控制接口

`tools/mcp_dashboard.py` 还暴露了本机控制端点，方便 Agent 直接当 LLM 用：

```bash
# 观察
curl -s -X POST http://127.0.0.1:8123/api/observe \
  -H 'Content-Type: application/json' \
  -d '{"target":"blocks","blockTypes":["spruce_log"],"maxDistance":64,"maxCount":16}'

# 动作
curl -s -X POST http://127.0.0.1:8123/api/act \
  -H 'Content-Type: application/json' \
  -d '{"frame":{"channel":"body","op":"move","args":{"p":[34,65,-52]}}}'

# 状态
curl -s http://127.0.0.1:8123/api/state

# 硬停
curl -s -X POST http://127.0.0.1:8123/api/estop \
  -H 'Content-Type: application/json' -d '{"reason":"manual"}'
```

真实任务记录见 `docs/CBAP-真实MCP-LLM任务.md`。

外部 LLM 自主性验证见 `docs/CBAP-外部LLM自主性验证.md`：
`tools/llm_autonomy.py` 用本地 Qwen3-4B 独立规划，经 CBAP 执行。

## 自动恢复 / cancel

`MCPDriver` 默认：

```text
auto_restart=True
restart_delay=0.8s
```

MCP 进程退出或 cancel 终止后，poll loop 会重启外部 server；崩溃会释放
Kernel 租约，恢复后客户端必须重新 `lease`。

```text
cancel：terminate MCP process → E_CANCELED → auto restart
```

记录见 `docs/CBAP-cancel与MCP恢复.md`。

## 驱动接口

```python
from drivers.mcp.driver import MCPDriver
from kernel.legacy_runtime.server import KernelServer

drv = MCPDriver(
    server_path="/path/to/mineflayer-mcp",
    node_bin="/path/to/node",
    username="MCPBody",
    version="1.21.1",
)
kernel = KernelServer(drivers=[drv], socket_path="./cbap.sock")
```

支持：

```text
read:  status / observe position / observe blocks / inventory inspect / observe chat
write: move / goto / dig / place / chat / attack / use / craft / equip
poll:  CBAP state，500 ms
estop: 终止外部 MCP 进程并断开 bot
```

不支持：

```text
stop：MCP server 没有 stop 工具；用 estop 做硬停。
collect / chest / furnace：当前 MCP server 没有对应工具。

工作台链路已经实测：`craft spruce_planks → craft crafting_table →
equip crafting_table → place → craft stick → craft wooden_pickaxe`。
记录见 `docs/CBAP-真实MCP-木镐任务.md`。

石镐/熔炉链路：木镐挖 cobblestone → `craft stone_pickaxe` →
`craft furnace` → `equip stone_pickaxe`。熔炉放置需要服务端确认，
当前 MCP `place` 在本世界两次未确认，因此熔炉保留在背包。
记录见 `docs/CBAP-真实MCP-石镐熔炉任务.md`。
```

## 集成测试

```bash
python3 -m unittest -v tests.cbap.test_mcp_driver
```

用 `tests/cbap/fake_mcp_server.py` 跑协议层；真实 MCP 的截图由 `tools/mcp_dashboard.py` 跑。
