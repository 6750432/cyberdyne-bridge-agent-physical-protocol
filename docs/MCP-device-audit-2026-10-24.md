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
