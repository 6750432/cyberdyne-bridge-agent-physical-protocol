# ADR-001: 自研 Mineflayer Body + 外部 Agent Brain

**状态：** Accepted  
**日期：** 2026-10-24  
**决策者：** 项目维护者

---

## 上下文

CBAP 已经具备：

```text
Kernel / lease / policy / audit / estop / facts
McDriver -> legacy line JSON hand
Mindcraft / Voyager / MCP adapters
118 条 conformance
```

继续把 CBAP 协议层做大，收益递减；  
真正影响“AI 玩 MC 流不流畅”的是 **Body 的动作粒度、状态更新、寻路、cancel 和 SDK 调用姿势**。

## 决策

```text
1. 新建 body/，不直接重构旧 hand
2. 旧 agents/cyberdyne/hand 作为参考实现
3. 第一版 SDK 只做 Python
4. 第一个外部 Brain 用本地 Qwen
5. Minecraft 固定 1.21.1
6. CBAP OS / host bridge 与 MC 计划完全隔离
7. 外部 Mindcraft / Voyager / MCP 只做对照和互操作
```

## 理由

### 为什么新建 `body/`

```text
旧 hand 有历史包袱和大量插件
新 body 可以只保留 MC 1.21.1 需要的核心
API 可以先冻结，再逐步补能力
不会让 MC 改动污染 CBAP 主链
```

旧 hand 仍然有价值：

```text
动作面参考
插件行为参考
真实服务器踩坑记录
```

### 为什么自研 Body

```text
动作批处理、状态流、cancel 需要底层控制
外部 MCP 工具边界改不动
上游 GPL patch 不适合作为唯一依赖
CBAP 的 facts / lease 需要 Body 配合
```

### 为什么外部 Brain

```text
LLM planner / curriculum / memory 迭代太快
自研 planner 会把项目拖成第二个 Mindcraft
项目价值在“手 + 权限层”，不是“再写一个大脑”
```

### 为什么第一版 Python SDK

```text
测试和 Agent 侧工具主要是 Python
标准库即可实现 NDJSON UDS
先把接入体验跑通，再考虑 JS
```

### 为什么固定 1.21.1

```text
现有 hand / 数据 / 协议都围绕 1.21.1
路径和方块数据稳定
避免同时调 MC 版本和 Agent
```

## 后果

### 正面

```text
Body API 可控
SDK 可以隐藏 CBAP 细节
外部 Brain 可替换
CBAP 保持控制面
旧 hand 不背新债
```

### 负面

```text
短期要维护两套手
新 body 需要重新跑真实服务器
Python SDK 之后可能还要补 JS
```

## 被拒绝的方案

```text
A. 直接重构旧 hand
   风险：历史插件/配置耦合，首版难冻结 API
B. 直接用 mineflayer-mcp 作为唯一身体
   风险：GPL patch、工具边界、上游变更
C. 自研完整 Brain
   风险：范围爆炸，重复造 Mindcraft
D. 把 CBAP OS / host bridge 一起纳入 MC 计划
   风险：范围和叙事失控
```

## 验收

```text
body/ 有独立 README 和 API v0
Python SDK 能连 fake body
真实 Mineflayer hand 可在 1.21.1 本地服务器跑
旧 hand 不被删除，只标记 legacy/reference
CBAP 118 条测试不回归
```
