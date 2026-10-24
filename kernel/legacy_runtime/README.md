# legacy_runtime · CBAP v1 网关（v0）

这是一个**不改主链**的第一层：

```
Agent --CBAP-U--> KernelServer --McDriver--> node/server.js（legacy hand）
```

- `KernelServer`：CBAP-U 服务，处理 `hello/open/read/write/ioctl/poll/lease/release/estop/stat/device_list`。
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

当前 82 条用例（网关/驱动/适配器/数据/20 条一致性 + D1/D4/D5）：

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
- MCP driver：真实 stdio MCP server 的 initialize/tools/list/tools/call；fake MCP 9 条通过

## v0 已知限制（照实写）

1. **多设备但单 Kernel**：v0 已支持一个 Kernel 挂多个驱动（legacy MC hand + dataflow Agent），但不做跨 Kernel/跨机器路由。
2. **每设备单 writer / 每设备 estop**：租约和 safe 状态按 `device_id` 隔离；一个设备 estop 不会封死其他设备。
3. **租约等待/释放**：`lease wait_ms>0` 进入 FIFO 等待队列；`release` 主动交接，不 estop。
4. **回执 FIFO**：legacy `cmdResult` 没有请求 ID，设备描述把 `max_inflight` 诚实写成 1；同一动词并发仍可能错配，等 legacy hand 加 `id` 后再消掉这条。
5. **cancel 是 best-effort**：CBAP 请求会回 `E_CANCELED`；MCP driver 通过终止/重启外部进程实现，legacy hand 已发出的动作仍可能继续跑完。
6. **estop 是锁存的**：`estop` 后网关进入 `safe`，`write` 回 `E_SAFETY`；v0 没有 `resume` 权限模型，恢复要 close/open 或重启网关。
7. **本地鉴权**：UDS 为 0600，SO_PEERCRED + token + operator token；同一 OS 用户仍可读本用户的 token。
8. **没有断线重连后的请求重放**：`McDriver` 会重连手，`MCPDriver` 会自动重启外部 server，但未完成的 CBAP 请求会 `E_IO`；需要重试的 Agent 自己用 `idempotency_key`。MCP 崩溃后租约释放，必须重新 `lease`。

## 下一步

- 给 legacy hand 的 `cmdResult` 加 `id`（或网关侧用单飞队列强制串行）；
- 把 `bridge.py` 的 `接线口` 换成 `CBAPClient`（真正“脑走 CBAP”）；
- 给 `mc-driver` 加 `device.json` 一致性测试与 `health` 看门狗；
- 给 `kernel` 加 `resume` 的 admin 权限模型。

## Security boundary (2026-10-24)

The Kernel now:

```text
binds the UDS with mode 0600
checks SO_PEERCRED against allowed_uids
generates <socket>.token and <socket>.operator (0600)
uses a capability policy; default agents cannot estop
requires the operator token for estop
enforces max sessions / inflight / write rate
adds fencing tokens and cancels pending writes on release
writes a hash-chained audit with optional HMAC and remote sink
latches safe mode on auth failure, estop burst, or audit failure
runs a state-age watchdog
```

Old clients that call `estop` as a normal agent must now use the operator
token or be granted `estop` by policy.

See [`docs/SECURITY-HARDENING.md`](../../docs/SECURITY-HARDENING.md).
