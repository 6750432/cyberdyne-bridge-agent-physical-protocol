# Goal gate 与真实异构并发隔离

日期：2026-10-23  
目的：验证两件事：

1. 外部 LLM 在 goal gate 下**恰好停在 3 个 oak_log**；
2. 一个 Kernel 同时挂 **真实 MCP Agent** 和 **真实 legacy hand**，状态/租约/结果/estop 互不串。

## 一、Goal gate：恰好 3 个

前一版外部模型达到 3 个 oak_log 后继续挖到 6 个。  
supervisor 加入硬门禁：

```text
oak_log >= 3 且 action 不是 chat/done
→ 拒绝执行，反馈 GOAL_GATE
→ 要求外部 planner chat 然后 done
```

为了重跑，先把 6 个 oak_log 合成 24 个 oak_planks（真实消耗），
使库存从 0 开始。

外部 Qwen3-4B 的第二次轨迹：

```text
1  equip wooden_pickaxe
2  move  (44,70,-42)
3  dig   (44,70,-42) → oak_log
4  move  (44,71,-42)
5  dig   (44,71,-42) → oak_log
6  move  (44,72,-42)
7  dig   (44,72,-42) → oak_log
8  chat  "Collected 3 oak_logs..."
9  done
```

结果：

```text
oak_log × 3
oak_planks × 24
wooden_pickaxe × 1
stone_pickaxe × 1
```

没有继续挖第 4 个。goal gate 生效。

![Goal gate exact three](screenshots/cbap-mcp-goalgate.png)

## 二、真实异构并发隔离

### 设备

```text
A: mcp://mc/MCPBody
   真实 external MCP stdio agent
   mineflayer-mcp + Minecraft

B: mc://bot/DeepSeek
   真实 legacy node/server.js hand
   line-JSON / 不同 transport / 不同方言
```

一个 `KernelServer(drivers=[MCPDriver, McDriver])` 同时挂载。

### 实测输出

```text
OK   two real devices visible
     ['mc://bot/DeepSeek', 'mcp://mc/MCPBody']

OK   distinct real states
     MCP:    [45.306, 68, -41.548]
     legacy: [473.5, 69, -130.5]

OK   lease MCP
OK   legacy write blocked while MCP leased
     E_BUSY: write requires a lease

OK   lease legacy
OK   MCP side write
     {'ok': True, 'sent': 'concurrency: MCP side'}

OK   legacy side write
     {'text': 'concurrency: legacy side'}

OK   result ids are distinct
     MCP:    r-4b91a73bbdba4af9
     legacy: r-07eeaa8d6ddb45dd

OK   legacy estop
     {'safe_state': 'idle', 'driver_ok': True}

OK   legacy safe after estop
     E_SAFETY: device is in safe mode after estop

OK   MCP unaffected by legacy estop
     {'ok': True, 'sent': 'concurrency: MCP still alive'}
```

完整机器可读结果：

- [`cbap-concurrency.json`](cbap-concurrency.json)

### 修复的隔离问题

之前 `estop` 是 **全局 safe**：

```text
一个设备 estop → 所有设备 write 都被 E_SAFETY 拒绝
```

已改为 per-device：

```text
_safe_devices.add(f.device_id)
写检查：self._safe or f.device_id in self._safe_devices
```

单设备 conformance 用例仍然通过；多设备新增回归用例：

```text
test_estop_is_per_device
```

### 重要边界

这里的“第二个异构 Agent”是 **真实 legacy hand/transport**，不是 Mindcraft LLM。
它验证的是：

```text
Kernel 的 device routing / state isolation / lease isolation /
result id isolation / estop isolation
```

它没有验证“两个自主 LLM 同时规划”的冲突与仲裁；那是下一层。

## 验证结果

```text
55/55 tests passed
real_concurrency.py: 17/17 checks passed
```

运行：

```bash
python3 tools/cbap_conformance.py --target fake
systemctl --user start mc-hand.service
python3 tools/real_concurrency.py
systemctl --user stop mc-hand.service
```

测试完成后 legacy hand 已停止，`mc-hand.service` 仍保持 disabled。
