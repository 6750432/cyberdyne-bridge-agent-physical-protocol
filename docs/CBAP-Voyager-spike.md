# Voyager 最小 spike

日期：2026-10-23  
目标：只验证 **Python 3.10 → Voyager HTTP bridge → Minecraft 1.19.2 → 一个手写 JS 任务**。  
明确不碰 GPT-4、curriculum、skill library、critic。

## 组成

```text
Python 3.10.14（本地源码构建）
  → stdlib urllib.request
  → Voyager bridge HTTP  :3000
  → mineflayer (Node)
  → Minecraft 1.19.2 :25565
```

Minecraft：

```text
版本:       1.19.2 vanilla dedicated server
online-mode: false
world:      flat
bot:        bot / ops.json level 4
```

Voyager 侧：

```text
external/Voyager
.voyager/env/mineflayer/index.js
```

## 关键现实处理

### Python 3.10

系统只有 Python 3.14；从源码构建了：

```text
external/Voyager/.python310/bin/python3.10   # 3.10.14
```

这个 spike 只用标准库，所以没有继续修 pip/ensurepip 的 zlib 问题。  
`VoyagerEnv`/gym 这条依赖链没在这个 spike 里启用。

### Node bridge

Voyager 原始 `npm install` 依赖太旧且下载不稳定。  
spike 里用了已有 Mindcraft 的 `node_modules`：

```text
mineflayer 4.39.0
minecraft-data 3.117.0
mineflayer-pathfinder 2.4.5
...
```

并对 `minecrafthawkeye` 做了 optional 处理（没有它也能跑，只是不能用弓）：

```text
node_modules symlink → Mindcraft node_modules
```

这是 **spike 配置**，不是最终可复现的生产安装。

### 没有 Fabric

Voyager 文档推荐 Fabric + 客户端 pause mods，但 bridge/手工任务本身在
vanilla 1.19.2 上就能跑。这个 spike 没装 Fabric，也没跑客户端。

## 实际结果

```text
voyager_spike.py: 4/4 checks passed
```

输出：

```text
OK  bridge /start connected
    name=bot
    position={x:-7.5, y:-60, z:-5.5}
    health=20
    inventory={oak_log:3}
    elapsed=3.72s

OK  manual JS /step executed
    onChat=['voyager spike: manual task OK']
    elapsedTime=60

OK  manual chat observed
OK  bridge /stop
```

完整结果：

- [`voyager-spike.json`](voyager-spike.json)

## 这证明了什么

```text
Python 3.10 能驱动 Voyager bridge
Voyager bridge 能连上 1.19.2
/start 能重置并给物品
/step 能执行手写 JS
world observation / onChat 能回来
```

## 这没证明什么

```text
没有跑 VoyagerEnv
没有跑 Voyager agent
没有 GPT-4 / 本地 LLM 规划
没有 curriculum / skill library / critic
没有 Fabric 客户端 mods
没有 CBAP adapter
```

所以这是“桥和世界能通”的 spike，不是“Voyager 已经能自治”。

## 如果要继续

最短下一步：

```text
1. 让 VoyagerEnv 在 Python 3.10 下 import（gym/psutil）
2. 用 VoyagerEnv.reset/step 跑同一手写任务
3. 再把 VoyagerEnv 的 /start /step /stop 包成 CBAP 设备
```

真正的 GPT-4 全量学习仍然不建议现在开：

```text
成本高
旧依赖风险
没有 OpenAI key
```

## 复现

```bash
# 1.19.2 server
cd external/voyager-mc
$JAVA -Xmx1G -jar server.jar nogui

# Voyager bridge
node voyager/env/mineflayer/index.js 3000

# spike
.python310/bin/python3.10 /path/to/tools/voyager_spike.py
```

测试完成后 server/bridge 已停止。
