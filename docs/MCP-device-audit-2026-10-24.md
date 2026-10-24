# MCP 设备审计 · 2026-10-24

## 结论先说

这次没有把“返回 ok 但没做到”直接叫造假。更准确的分类是：

```text
tool receipt（工具回执） != independent fact（独立事实）
```

CBAP 的 `MCPDeviceDriver` 现在会在动作后重新读事实源；没有事实源就明确标成：

```json
{"ok": false, "status": "unverifiable"}
```

## 本机可执行结果

诚实灯：

```text
tool_ok=true  status=verified  actual.on=true
```

撒谎灯（工具返回 ok，状态没变）：

```text
tool_ok=false status=mismatch  actual.on=false
```

只读温度计：

```text
status=verified  temp_c=23.5
```

这证明探针能区分：

```text
真做到
没做到（mismatch）
没法判断（unverifiable）
```

## Kernel 接入

`MCPDeviceDriver` 已经能通过 CBAP Kernel 的通用通道跑：

```text
open -> lease -> write(channel=mcp, expect={...})
-> independent facts
-> read(channel=state)
```

回归测试：

```text
tests/cbap/test_mcp_device.py
65/65 -> 66/66
```

## `external/mineflayer-mcp` 静态审查

本机没有运行中的 Minecraft 服务端，所以这里只做代码审查，不宣称实机结果。

有几类“成功回执”没有独立事实：

| 工具 | 返回 | 独立事实 |
|---|---|---|
| `chat` | `{ok:true,sent:...}` | 没有服务端回声校验；只有本地发送成功 |
| `use` | `{ok:true,item:...}` | 没有使用效果校验 |
| `dig` | `{ok:true,dug:...}` | 没有重新读方块确认已经变成空气 |
| `drop` | `{ok:true,count:...}` | 没有重新读背包确认数量减少 |
| `attack` | `{ok:true,damageDealt:...}` | 有 entity health 前后对比（这条相对好） |
| `place` | `{ok:true,placed:...}` | 会重新读目标方块（这条相对好） |
| `move` | `{ok:true,reached:...}` | 有 pathfinder 完成 + 位置返回（但仍是自报） |

这些不一定是恶意造假；很多是 MCP 只暴露了“工具调用”而没有暴露“设备事实”。
但如果 Agent 把 `ok:true` 当完成，就会产生成功假象。

## 手机上发现的 `server-memory`

交接件里的两个现象：

```text
A -> GHOST 写入成功，关系悬空
重复删除返回 successfully
```

这是语义缺失，不一定是谎报。CBAP 应该要求：

```json
{"ok": true, "facts": {"deleted": 0}}
{"ok": true, "facts": {"dangling": true}}
```

而不是只返回 `ok`。

## 通用探针

```bash
python3 tools/mcp_device_probe.py manifest.json \
  --op turn_on --expect '{"on":true}'
```

退出码：

```text
0 verified / observed
2 mismatch
3 unverifiable
4 transport error
```

下一步可以把这个探针接到所有已安装的 MCP server 上，统一产出：

```text
server / tool / claimed / actual / status
```

不要先给服务定性，先让事实说话。

## 实机 MCP 结果

### `mineflayer-mcp` 0.2.0

在 1.21.1 测试服上实际连接，9 个工具：

```text
observe move chat dig place attack use inventory status
```

CBAP 实测：

```text
move  工具返回 reached=true
      动作后立刻 observe 仍是旧坐标
      等 facts settle 后坐标一致
      -> verified（不是造假，是事实传播延迟）

dig   工具返回 dug=dirt + 目标坐标
      observe blocks 复核：目标方块已消失
      -> verified

chat  工具返回 ok
      observe chat 只能读到本地 outgoing buffer
      -> 不能证明服务端真的收到；应标 unverifiable
```

事实延迟很重要：`MCPDeviceDriver` 现在有 `facts_timeout_ms`，会轮询到事实稳定，而不是一次读到旧值就判 mismatch。

### 安全/能力缺口

```text
9 个工具里没有真正的 stop / estop
```

`chat` 不是急停。对一个真实 Mineflayer body，必须有独立的 stop 能力，否则 CBAP 只能把它标成：

```text
estop: unavailable
```

### `server-memory` 2.0.0

实机复测：

```text
create A                         -> ok
create relation A -> GHOST       -> rejected: Entity GHOST not found
delete A                         -> "Entities deleted successfully"
delete A again                   -> "Deleted 0 of 1 entities. Not found: A"
read_graph                       -> A 确实不存在
```

这次 **没有** 复现手机交接件里的悬空关系/假成功；2.0.0 会把失败说清楚。

### 未能实机审计

```text
server-filesystem   npm registry 超时，未安装
jsdom browser      只在手机端有，未搬过来
Chromium           未安装
```

## 结论

目前看到的不是“MCP 故意造假”，而是三类不同问题：

```text
1. 事实延迟：tool 已返回，状态还没传播（move）
2. 回执缺口：ok 只说明调用成功，不说明外部效果（chat/use/drop）
3. 能力缺口：没有 stop/estop（mineflayer-mcp）
```

CBAP 的 probe 已经把 1 和 2 分开；3 应该直接拒绝宣称“可远程安全控制”。

如果主人已经定位到具体漏洞，把 server、版本、复现命令/报文给我，我可以直接补一条回归，不靠猜。
