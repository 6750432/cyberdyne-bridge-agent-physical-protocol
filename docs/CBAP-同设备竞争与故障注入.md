# 同设备竞争与 MCP 崩溃注入

日期：2026-10-23  
目标：

1. 两个独立 CBAP session 抢同一个真实 MCP 设备，验证 lease/E_BUSY/交接；
2. 在一个写请求进行中杀掉 MCP 进程，验证 pending 请求和健康状态。

## 一、同设备竞争

设备：

```text
mcp://mc/MCPBody
```

两个 CBAP session：

```text
A: contender-A / fd-1
B: contender-B / fd-2
```

实际结果：

```text
A lease ttl=1500ms
→ ok

B lease
→ E_BUSY: device is leased by another writer

A write chat
→ ok

B write（无租约）
→ E_BUSY: write requires a lease

B lease wait_ms=5000
→ 进入 FIFO 等待队列

A release（主动释放，不关闭 fd）
→ B 被唤醒并取得租约

B write chat
→ ok

A write（已不是 owner）
→ E_BUSY: write requires a lease
```

结论：

```text
同一设备同一时刻只有一个 writer
立即抢失败返回 E_BUSY
显式 wait_ms 会进入 FIFO 等待队列
主动 release 会把手里的租约交给队首 waiter
旧 writer 不能继续写
```

仲裁策略：

```text
immediate lease   → 非阻塞，E_BUSY
lease wait_ms>0   → FIFO 排队，release/过期后交给队首
release           → 主动释放，不 estop、不关闭 fd
```

wait_ms 超时返回 `E_TIMEOUT`。

## 二、MCP 进程崩溃注入

在 B 持有租约时：

```text
B 发起 long move 到 (200,68,-200)
→ ack accepted
→ 立刻 kill MCP 进程
→ pending write
→ E_IO: MCP process ended
→ driver.health.ok = false
→ connected = false
```

这说明：

```text
已受理但未完成的写不会假成功
Kernel 会把设备断开映射成 E_IO
健康检查会转为 unhealthy
```

## 结果

```text
contention_and_fault.py: 14/14 checks passed
```

完整机器结果：

- [`contention-fault.json`](contention-fault.json)

## 边界

已验证：

```text
lease 排他
E_BUSY
wait_ms FIFO 排队
主动 release 交接
旧 writer 失效
pending 请求遇到 MCP crash → E_IO
health → unhealthy
```

未验证：

```text
优先级 / 抢占
cancel 与已经发出的 MCP 动作
MCP 自动重启/恢复
同设备两个外部 LLM planner 的完整对话仲裁
```

## 复现

```bash
python3 tools/contention_and_fault.py
```

脚本会启动一个真实 MCPBody 进程并在故障注入阶段杀掉它；结束后清理。
