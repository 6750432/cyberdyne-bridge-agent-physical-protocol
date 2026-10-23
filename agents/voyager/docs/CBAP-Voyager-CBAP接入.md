# Voyager bridge 接入 CBAP

日期：2026-10-23  
目标：把已经跑通的 Voyager 1.19.2 bridge 收成 CBAP 设备，**不使用任何付费 API / GPT-4**。

## 结果

```text
device: mc://voyager/bot
adapter: agents/voyager/adapter/adapter.mjs
kernel: McDriver + CBAP Kernel
```

实测：

```text
voyager_cbap.py: 8/8 checks passed
```

```text
OK  Voyager device visible
OK  read state       [11.5, 66, 23.5]
OK  lease
OK  forward under lease
OK  position changed [11.5, 66, 23.5] → [11.5, 66, 23.7]
OK  say under lease
OK  estop
OK  offline after estop
```

完整结果：

- [`voyager-cbap.json`](voyager-cbap.json)

## 结构

```text
CBAP Kernel
  → McDriver
  → line-JSON adapter
  → Voyager bridge HTTP :3000
  → Mineflayer
  → Minecraft 1.19.2
```

adapter 提供：

```text
state    从 bridge /state 拉取并转成 CBAP body
forward  一段短前进
say      聊天
exec     显式 JS 代码
stop     bridge /stop
```

## 这不是什么

这不是 Voyager 的自治 Python agent。

没有：

```text
VoyagerEnv
curriculum
skill library
critic
GPT-4
自动代码生成
```

它是一个 **可被 CBAP/本地 planner 驱动的 Voyager bridge 身体**。

如果要让 Voyager 自己的 Python agent 跑起来，还需要：

```text
1. Python 3.10 下 import VoyagerEnv（gym/psutil）
2. 把 VoyagerEnv 的 reset/step 包成 CBAP 设备
3. 让本地 4B Qwen 或本 Agent 做 planner
```

## 当前状态

测试完成后：

```text
Minecraft 1.19.2 server   stopped
Voyager bridge            stopped
Voyager CBAP adapter      stopped after estop
```

## 复现

```bash
# 1.19.2 server
cd external/voyager-mc
$JAVA -Xmx1G -jar server.jar nogui

# Voyager bridge
node voyager/env/mineflayer/index.js 3000

# start bot once
curl -X POST localhost:3000/start -H 'Content-Type: application/json' \
  -d '{"port":25565,"reset":"hard","inventory":{},"waitTicks":10}'

# adapter
node agents/voyager/adapter/adapter.mjs --bridge http://127.0.0.1:3000

# CBAP probe
.python310/bin/python3.10 agents/voyager/tools/voyager_cbap.py
```
