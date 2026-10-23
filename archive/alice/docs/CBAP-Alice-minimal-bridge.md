# Alice 最小 bridge

日期：2026-10-23  
目标：不做完整 Alice adapter，只提供一个能读服务器事实、提交一个 `walk_to` 的最小 bridge。

## 边界

```text
一个 bot
GET  /state
POST /task  {type:"walk_to", target:[x,y,z]}
POST /stop
```

不做：

```text
mine / collect / container / inventory writes
LLM
CBAP driver
```

## 设计

```text
CBAP / probe
  → HTTP 127.0.0.1:8745
  → Alice CbapBridge
  → Minecraft server thread
  → BotManager.assignWalkTo / BotStateReport / stopTask
```

`/state` 复用 Alice 自己的 `DecisionSnapshot` 事实，不是从日志猜。

## 最小闭环

```text
spawn（或已有 bot）
  → GET /state（服务器 pos）
  → POST /task walk_to
  → 轮询 GET /state（服务器 pos）
  → 距离 <= 1.5
  → POST /stop
  → GET /state 最终对账
```

## 代码

- `archive/alice/bridge/CbapBridge.java`
- `archive/alice/tools/alice_bridge_probe.py`
- `archive/alice/bridge/README.md`

## 状态

代码已写入，但当前环境没有 JDK17/Forge Gradle 构建环境，**未编译、未跑真实 Forge 服务端**。  
因此下一步是：

```text
1. 配 JDK17 + ForgeGradle
2. 编译 Alice
3. 启 Forge 1.20.1 服务端
4. 跑 probe
```

编译通过前，不能宣称 bridge 已验证。
