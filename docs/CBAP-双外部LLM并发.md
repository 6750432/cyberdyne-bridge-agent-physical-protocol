# 两个外部 LLM 同时驱动两个真实 CBAP 设备

日期：2026-10-23  
目标：从“外部 LLM 自主性”推进到“两个独立外部 LLM 规划器 + 两个真实异构设备”。

## 角色

```text
Planner α：Qwen3-4B-Instruct-2507，独立 CBAP session
Device  A：mcp://mc/MCPBody（真实 external MCP + Mineflayer）

Planner β：Qwen3-4B-Instruct-2507，独立 CBAP session
Device  B：mc://bot/DeepSeek（真实 legacy node/server.js hand）
```

每个 planner 只拿到自己设备对应的 `fd`，不能访问另一个设备。

## 任务

```text
α: 发送 "alpha online"，向东移动 1 格，然后 done
β: 发送 "beta online"，向东移动 1 格，然后 done
```

## 并发轨迹

两个 planner 用 barrier 同时开始，各自调用本地 LLM，再通过自己的 CBAP fd 执行。

### Planner α / MCP

```text
1 chat "alpha online"   → result r-5aae2f740b32461d
2 move dir=[1,0] ms=500 → result r-2e2de4bbca5244a1
3 done
```

### Planner β / legacy hand

```text
1 chat "beta online"    → result r-7635d86533864592
2 move dir=[1,0] ms=500 → result r-a7bfda67d842495a
3 done
```

## 隔离结果

```text
两个设备同时在 device_list 中
初始位置不同：
  α [45.306, 68, -41.548]
  β [473.5, 69, -130.5]

两个 chat 文本不同：
  "alpha online"
  "beta online"

result id 不串：
  r-5aae... / r-2e2d...
  r-7635... / r-a7bf...

两个 planner 最终都 chat_done=true, move_done=true
thread_errors = []
```

完整机器结果：

- [`dual-agent.json`](dual-agent.json)

## 重要边界

这次验证的是：

```text
两个独立外部 LLM 规划器
两个独立 CBAP session
两个真实异构设备
设备路由 / fd / 租约 / result id 隔离
```

**不是**：

```text
两个 planner 同时对同一个设备抢占
真正的 GPU 并行推理
Mindcraft/Voyager 两个自治 Agent
```

本地 `llama-server` 是单推理槽（`-np 1`），所以 LLM 推理本身会排队；
但 CBAP 侧是两个独立 planner/session，动作与结果没有串设备。

## 复现

```bash
systemctl --user start mc-hand.service
python3 tools/dual_agent_validation.py
systemctl --user stop mc-hand.service
```

测试后 legacy hand 已停止，`mc-hand.service` 仍 disabled。

## 下一步

```text
1. 让两个 planner 抢同一 device，验证 lease/E_BUSY/仲裁
2. 故障注入：kill MCP / estop / 租约过期 / cancel
3. 换 Mindcraft 作为第二个真实自治 Agent
```
