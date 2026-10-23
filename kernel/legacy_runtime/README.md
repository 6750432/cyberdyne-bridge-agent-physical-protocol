# legacy_runtime · CBAP v1 网关（v0）

这是一个**不改主链**的第一层：

```
Agent --CBAP-U--> KernelServer --McDriver--> node/server.js（legacy hand）
```

- `KernelServer`：CBAP-U 服务，处理 `hello/open/read/write/ioctl/poll/lease/estop/stat/device_list`。
- `McDriver`：CBAP-D 形状的 MC 驱动包壳，直接说 `node/server.js` 的 line-JSON。
- `CBAPClient`：最小 Python 客户端，给测试/示例用。
- `brain_adapter.py`：`接线口` 形状的适配器（`连/收/发/断`），让未来的 `bridge.py` 可以一行换过来；现在没有接进主链。
- `tests/cbap/fake_hand.py`：假手，不连 Minecraft。

## 跑起来

```bash
# 只检查手在不在、读一份 health
python3 -m kernel.legacy_runtime --check

# 起网关（会监听 ./cbap.sock）
python3 -m kernel.legacy_runtime \
  --hand-socket ./cyberdyne.sock \
  --cbap-socket ./cbap.sock
```

> ⚠ **不要同时跑 `bridge.py` 和这个网关去连同一只手。**
> 两者都是 legacy hand 的客户端；legacy hand 没有 per-client 仲裁，会变成“两个大脑抢一只手”。
> 现在这个网关是给“新 Agent / 测试 / 迁移期”用的，不是替代 `bridge.py` 的常驻入口。

## 最小客户端示例

```python
from kernel.legacy_runtime import CBAPClient

c = CBAPClient("./cbap.sock", agent_id="demo")
c.connect()
c.hello()
r = c.open("mc://bot/DeepSeek", mode="exclusive")
fd = r["payload"]["fd"]
print(c.read(fd, channel="body"))
print(c.write(fd, {"channel": "body", "op": "move",
                   "args": {"dir": [1, 0], "ms": 300}}))
c.close()
```

## 测试

```bash
python3 tools/cbap_conformance.py --target fake
```

当前 53 条用例（网关/驱动/适配器/数据/20 条一致性 + D1/D4/D5）：

- hello/welcome、device_list
- open/read
- 无租约 write → `E_BUSY`
- lease + move → ack + result + 状态更新
- chat + poll
- estop 后 write → `E_SAFETY`
- unknown op → `E_NOTSUP`
- unknown device → `E_NOENT`
- `接线口` 形状 adapter：move/dig/say 全通
- adapter 的 `scan_environment` / `watch_blocks`（走 ioctl）全通
- adapter 对不支持的命令 fail-closed（回一条 `ok:false`）
- MCP driver：真实 stdio MCP server 的 initialize/tools/list/tools/call；fake MCP 4 条通过

## v0 已知限制（照实写）

1. **多设备但单 Kernel**：v0 已支持一个 Kernel 挂多个驱动（legacy MC hand + dataflow Agent），但不做跨 Kernel/跨机器路由。
2. **每设备单 writer**：租约按 `device_id` 隔离；同一设备同一时间只允许一个 writer，读可以共享。
3. **回执 FIFO**：legacy `cmdResult` 没有请求 ID，设备描述把 `max_inflight` 诚实写成 1；同一动词并发仍可能错配，等 legacy hand 加 `id` 后再消掉这条。
4. **cancel 不保证停手**：CBAP 请求会回 `E_CANCELED`，但已经发给 legacy hand 的动作可能继续跑完；真正的取消要等手侧支持。
5. **estop 是锁存的**：`estop` 后网关进入 `safe`，`write` 回 `E_SAFETY`；v0 没有 `resume` 权限模型，恢复要 close/open 或重启网关。
6. **没有鉴权**：UDS 默认无 token；TCP/token 字段已留，但 v0 只跑 UDS。
7. **没有断线重连后的请求重放**：`McDriver` 会重连手，但未完成的 CBAP 请求会 `E_IO`；需要重试的 Agent 自己用 `idempotency_key`。

## 下一步

- 给 legacy hand 的 `cmdResult` 加 `id`（或网关侧用单飞队列强制串行）；
- 把 `bridge.py` 的 `接线口` 换成 `CBAPClient`（真正“脑走 CBAP”）；
- 给 `mc-driver` 加 `device.json` 一致性测试与 `health` 看门狗；
- 给 `kernel` 加 `resume` 的 admin 权限模型。
