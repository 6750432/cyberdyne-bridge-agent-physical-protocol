# CBAP v1 规范包

- **状态**：Draft
- **日期**：2026-10-23

## 读的顺序

1. [`cbap-v1.md`](cbap-v1.md) —— 规范正文：角色、传输、消息、系统调用、驱动 ABI、错误、安全、版本。
2. [`schema/message.schema.json`](schema/message.schema.json) —— CBAP-U 消息的 JSON Schema。
3. [`schema/device.schema.json`](schema/device.schema.json) —— 驱动描述符 `device.json` 的 Schema。
4. [`schema/mapping.schema.json`](schema/mapping.schema.json) —— 动作映射 `mapping.json` 的 Schema。
5. [`examples/`](examples/) —— MC / 机械臂描述符、MC 映射、一次完整会话。
6. [`conformance-v1.md`](conformance-v1.md) —— 20 条一致性用例。

## 已验证

- 3 个 Schema 通过 JSON Schema Draft 2020-12 元校验；
- `examples/*.json` 与 `examples/session.ndjson` 全部通过对应 Schema（2026-10-23，`uv run --with jsonschema`）；
- `drivers/mc/device.json` / `mapping.json` 已覆盖真实 legacy hand 的完整命令面（21 个 op，含 collect / chest / furnace / give）；
- `drivers/dataflow/`：外部 MC Agent 的通用数据流驱动；一个 Kernel 可同时挂 legacy hand + dataflow Agent（`KernelServer(drivers=[...])`）；
- `tests/cbap/test_multi_device.py`：同一 Kernel 下两个设备并存、独立租约、独立读写；
- `drivers/mcp/`：真实外部 MCP MC Agent（`swaynos/mineflayer-mcp`）的 stdio adapter；公开 MCP tools → CBAP read/write/poll/estop；
- `tests/cbap/test_data.py`：设备通道、映射、参数类型、legacy 字段名 / dataflow / MCP 8 条数据契约测试通过；
- `tests/cbap/test_mcp_driver.py`：MCP stdio 协议、状态、move/chat、estop 4 条通过；
- `tests/cbap/test_conformance.py`：20 条一致性用例 + D1/D4/D5 驱动安全用例通过；
- 网关/驱动/适配器/数据合计 60 条：`python3 tools/cbap_conformance.py --target fake`；
- 真实 MCP 外设 demo：`python3 tools/mcp_dashboard.py --server-path ...`，截图 `docs/screenshots/cbap-mcp-live.png`；
- 本 Agent 直接当 LLM 的真实任务：`docs/CBAP-真实MCP-LLM任务.md`，截图 `docs/screenshots/cbap-mcp-llm-task.png`（采集 3 个 spruce_log）；
- 完整木镐链路：`docs/CBAP-真实MCP-木镐任务.md`，截图 `docs/screenshots/cbap-mcp-pickaxe.png`（原木 → 木板 → 工作台 → 木棍 → 木镐 → 装备）；
- 石镐/熔炉链路：`docs/CBAP-真实MCP-石镐熔炉任务.md`，截图 `docs/screenshots/cbap-mcp-stone-pickaxe.png`（木镐挖石 → 石镐 → 熔炉）；
- MCP place 修复：`docs/CBAP-MCP-place修复.md`，截图 `docs/screenshots/cbap-mcp-place-fixed.png`；补丁 `drivers/mcp/patches/mineflayer-mcp-place.patch`（只修外部 server 的方块选择/hotbar/确认，不动 bridge/node）；
- 外部 LLM 自主性：`docs/CBAP-外部LLM自主性验证.md`，截图 `docs/screenshots/cbap-mcp-autonomy.png`；Qwen3-4B 独立规划；
- Goal gate 与真实异构并发：`docs/CBAP-goal-gate与并发隔离.md`，截图 `docs/screenshots/cbap-mcp-goalgate.png`；第二次外部规划恰好 3 个 oak_log；MCP + legacy hand 同 Kernel 的租约/结果/estop 隔离通过；
- 双外部 LLM 并发：`docs/CBAP-双外部LLM并发.md`，结果 `docs/dual-agent.json`；两个独立 Qwen planner 通过各自 CBAP fd 驱动两个真实异构设备，动作/结果不串；
- 同设备竞争与故障注入：`docs/CBAP-同设备竞争与故障注入.md`，结果 `docs/contention-fault.json`；lease/E_BUSY、wait_ms FIFO、release 交接、MCP crash→E_IO/unhealthy 14/14 通过；
- Cancel 与 MCP 恢复：`docs/CBAP-cancel与MCP恢复.md`，结果 `docs/cancel-recovery.json`；cancel→E_CANCELED、自动重启、crash→E_IO、恢复后重新 lease 并续写 13/13 通过；
- Mindcraft 接入：`docs/CBAP-Mindcraft接入.md`，截图 `docs/screenshots/cbap-mindcraft.png`，结果 `docs/mindcraft-cbap.json`；真实 Mindy 通过 adapter 暴露 state/prompt/stop，8/8 通过；
- Voyager spike：`docs/CBAP-Voyager-spike.md`，结果 `docs/voyager-spike.json`；Python 3.10 + Voyager bridge + MC 1.19.2 + 手写 JS，5/5 通过（不含 GPT-4/VoyagerEnv）；
- Voyager CBAP 接入：`docs/CBAP-Voyager-CBAP接入.md`，结果 `docs/voyager-cbap.json`；`mc://voyager/bot` 的 state/forward/say/exec/stop 8/8 通过，无付费 API；
- 本地 Qwen 控制 Voyager：`docs/CBAP-Qwen控制Voyager.md`，结果 `docs/voyager-qwen.json`；4 步 forward×2/say/done，无 GPT-4/API；
- Qwen 生成 JS + Voyager exec：`docs/CBAP-Qwen-exec-Voyager.md`，结果 `docs/voyager-qwen-exec.json`；4B 生成 jump+chat JS，onChat 验证通过，无付费 API；
- Alice 最小 bridge：`docs/CBAP-Alice-minimal-bridge.md`，源码 `drivers/alice/bridge/CbapBridge.java`，probe `tools/alice_bridge_probe.py`；未编译/未跑 Forge。

## 还没做

- 让 `bridge.py` 真正通过 `CBAPClient` 调手（现在网关是新 Agent 的入口，`bridge.py` 还走旧 `接线口`）；
- `cbap-pkg` 包管理器规范/实现；
- legacy `cmdResult` 加 `id`，消掉网关的 FIFO 配对限制；
- D2（estop 回 ok 但设备仍动）/ D3（驱动 watchdog）的驱动侧强制用例；当前 D1/D4/D5 已接入一致性执行器；
- MCP server 只是真实身体/工具层；外部 LLM/MCP Agent 的自主规划回路还没接（当前 Kernel 是调用方）；
- MCP 第一刀不支持 stop/collect/chest/furnace（server 没有对应工具），见 `drivers/mcp/README.md`。

## 命名约定

- 线上字段/`op`/错误码 **MUST** 用 ASCII；人类可读文本可本地化。
- 设备 ID 用 `scheme://path`：`mc://bot/DeepSeek`、`robot://arm0`、`robot://dog0`。
- 版本：`v` / `cbap` 用 `MAJOR.MINOR`，v1 为 `"1.0"`。
