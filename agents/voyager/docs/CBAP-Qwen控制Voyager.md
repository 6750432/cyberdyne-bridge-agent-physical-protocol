# 本地 Qwen 4B 通过 CBAP 控制 Voyager

日期：2026-10-23  
目标：用本地 **Qwen3-4B-Instruct-2507** 通过 CBAP 控制 `mc://voyager/bot`，不使用 GPT-4，不产生 API 费用。

## 链路

```text
Qwen3-4B (127.0.0.1:8099)
  → agents/voyager/tools/voyager_qwen_planner.py
  → CBAP fd / Kernel
  → McDriver
  → agents/voyager/adapter/adapter.mjs
  → Voyager bridge :3000
  → Mineflayer / Minecraft 1.19.2
```

## 任务

```text
forward 至少一次
发送 "qwen controlled voyager"
done
```

## Qwen 的实际决策

```text
turn 1  forward  → ok
turn 2  forward  → ok
turn 3  say "qwen controlled voyager" → ok
turn 4  done   → ok
```

位置：

```text
before [9.5, 64, 22.5]
after  [9.5, 64, 22.7]
```

Minecraft 服务端聊天日志：

```text
<bot> qwen controlled voyager
```

## 结果

```text
voyager_qwen_planner.py: ok=true
Qwen steps: 4
forward: 2
say: 1
done: 1 (goal gate passed)
```

完整机器结果：

- [`voyager-qwen.json`](voyager-qwen.json)

## 这证明了什么

```text
本地 4B 能通过 CBAP 读取 Voyager 状态
能选择 CBAP 支持的 action
能真实执行 forward / say
能在两个目标完成后选择 done
没有调用 GPT-4 或任何付费 API
```

## 边界

这不是 Voyager 的自治 Python agent：

```text
没有 VoyagerEnv
没有 curriculum
没有 skill library
没有 critic
没有自动代码生成
```

Qwen 只做**高层动作选择**；`forward` 的底层 JS 是 adapter 里固定的实现。  
任务也很小，不能据此判断 4B 能完成复杂 Voyager 任务。

## 当前状态

测试结束后：

```text
Qwen model       stopped
Minecraft 1.19.2 stopped
Voyager bridge   stopped
CBAP adapter     stopped after estop
ports 3000/25565/8099 closed
memory           ~4.4 GiB used / ~11 GiB available
```

## 复现

```bash
# start boundary-model, MC 1.19.2, bridge, bot, adapter
# then:
.python310/bin/python3.10 agents/voyager/tools/voyager_qwen_planner.py
```
