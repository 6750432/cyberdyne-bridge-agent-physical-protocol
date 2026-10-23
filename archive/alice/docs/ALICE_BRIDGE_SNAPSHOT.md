# Alice 最小 CBAP bridge · 档案

日期：2026-10-23  
状态：**源码完成，构建未完成，真实闭环未验证**。  
决定：停止继续构建，留档；Alice 本体计划重构。

## 为什么停

这版不是在 CBAP 协议上卡住，而是被 Forge 1.20.1 的构建链拖住了：

```text
JDK17 下载/安装
ForgeGradle 插件和 Minecraft/Forge 依赖下载
Gradle 8.8 下载
构建中途网络超时/长时间无进展
```

最小 bridge 本身只有：

```text
GET  /state
POST /task  walk_to
POST /stop
```

继续为了一个即将重构的 Forge mod 把 ForgeGradle 环境磨通，不值得。

## 已保留内容

源码：

```text
drivers/alice/bridge/CbapBridge.java
drivers/alice/README.md
tools/alice_bridge_probe.py
docs/CBAP-Alice-minimal-bridge.md
```

提交：

```text
37d6c8c  CBAP: add minimal Alice bridge source
```

## 设计

```text
probe / CBAP
  → HTTP 127.0.0.1:8745
  → CbapBridge
  → Minecraft server thread
  → BotStateReport / BotManager.assignWalkTo / stopTask
```

最小闭环：

```text
state 读服务器 pos
→ task walk_to
→ 轮询 state 对账
→ 到达目标
→ stop
```

不做：

```text
mine / collect / container / inventory write
LLM
完整 CBAP driver
```

## 未完成

```text
JDK17 + ForgeGradle 编译通过
Forge 1.20.1 服务端启动
bridge 真实 HTTP smoke test
WalkTo 真实闭环
```

**不要把这个档案说成已验证 bridge。**

## 恢复条件

如果 Alice 重构后仍需要 CBAP：

```text
1. 在新的 Alice 版本上重新确认 BotManager.assignWalkTo / BotStateReport
2. 重新应用 CbapBridge.java
3. 构建并跑 tools/alice_bridge_probe.py
4. 再决定是否扩成正式 driver
```

## 其他

外部 Alice 工作副本中为了构建做过 Gradle 镜像修改，这些修改没有进入本仓库，也不作为补丁保留；留档以本仓库的 bridge 源码为准。
