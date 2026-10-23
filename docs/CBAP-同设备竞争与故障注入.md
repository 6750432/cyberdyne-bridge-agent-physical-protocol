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

等待 A TTL 过期（没有调用 A.lease 续租）
→ B lease
→ ok

B write chat
→ ok

A write（旧租约已失效）
→ E_BUSY: write requires a lease
```

结论：

```text
同一设备同一时刻只有一个 writer
竞争失败没有静默排队，返回 E_BUSY
租约过期后可以交接
旧 writer 不能继续写
```

当前仲裁策略是 **非阻塞争抢 + 调用方重试**，不是公平队列。

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
contention_and_fault.py: 13/13 checks passed
```

完整机器结果：

- [`contention-fault.json`](contention-fault.json)

## 边界

已验证：

```text
lease 排他
E_BUSY
TTL 交接
旧 writer 失效
pending 请求遇到 MCP crash → E_IO
health → unhealthy
```

未验证：

```text
公平队列 / 优先级
租约主动释放 API
cancel 与已经发出的 MCP 动作
MCP 自动重启/恢复
同设备两个外部 LLM planner 的完整对话仲裁
```

## 复现

```bash
python3 tools/contention_and_fault.py
```

脚本会启动一个真实 MCPBody 进程并在故障注入阶段杀掉它；结束后清理。
