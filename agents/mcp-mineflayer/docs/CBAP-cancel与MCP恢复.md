# Cancel 与 MCP 自动恢复

日期：2026-10-23  
目标：补上“故障后能不能继续干活”的最后一环。

## 1. Cancel 一个真实 MCP 动作

MCP 没有 cancel 原语，所以采用 **终止外部 MCP 进程** 作为 best-effort cancel：

```text
CBAP write long move
→ ack accepted
→ cancel target
→ pending result E_CANCELED
→ MCP 进程终止
→ MCPDriver 自动重启
```

结果：

```text
cancel acknowledged
canceled write result is E_CANCELED
MCP auto-restarted after cancel
write works after cancel/restart
```

注意：

```text
cancel 不保证已经发出的 Minecraft 动作没有产生任何副作用
它保证 Kernel 侧请求终态为 E_CANCELED，并且后续可以继续
```

## 2. MCP 进程崩溃 + 自动重启

```text
CBAP write long move
→ ack accepted
→ kill MCP process
→ pending result E_IO: hand disconnected: MCP process ended
→ MCPDriver 自动重启
→ health ok
→ 重新 lease
→ write works
```

崩溃时 Kernel 会释放该设备租约，所以恢复后必须：

```text
重新 lease
```

这是有意的：旧 writer 不能自动继承崩溃后的写权限。

## 3. 实际结果

```text
cancel_recovery.py: 13/13 checks passed
restarts: 2
```

覆盖：

```text
cancel ack
E_CANCELED
cancel 后自动重启
cancel 后新写成功
MCP crash
pending E_IO
crash 后自动重启
crash 后租约释放
crash 后 re-lease + 新写成功
```

完整结果：

- [`cancel-recovery.json`](cancel-recovery.json)

## 更新

`MCPDriver` 新增：

```text
auto_restart=True
restart_delay=0.8
cancel()
_restart_client()
```

`KernelServer` 的 `cancel` 会调用驱动的 `cancel()`（如果驱动支持）。

## 边界

已验证：

```text
cancel 的 CBAP 终态
cancel 后恢复
crash 后恢复
crash 后租约释放/重新获取
```

未验证：

```text
不重启进程的真正动作取消
MCP 恢复后的 pending 自动重放（当前明确不重放）
多设备同时 crash 的恢复竞争
```

## 复现

```bash
python3 tools/cancel_recovery.py
```
