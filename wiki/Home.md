# Cyberdyne Bridge · CBAP

> 这是 **Home 索引**，不是第二份主文档。  
> 协议、安全、发行版的唯一事实源在仓库里，Wiki 只负责导航。

## 先看什么

| 目标 | 入口 |
|---|---|
| 30 秒跑协议 | [README · 快速开始](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/README.md#快速开始) |
| 协议规范 | [spec/README.md](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/spec/README.md) |
| 安全边界 | [README · 安全边界](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/README.md#安全边界) |
| 安全控制与残余风险 | [docs/SECURITY-HARDENING.md](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/docs/SECURITY-HARDENING.md) |
| 参数手册 | [docs/CBAP-参数手册.md](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/docs/CBAP-参数手册.md) |
| 发行版 | [RELEASES.md](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/RELEASES.md) |
| CBAP OS / Host Bridge | [CBAP OS VM → host](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/docs/CBAP-OS-Host-Bridge.md) |
| Host device IDs | `host://fs` / `display` / `input/*` (input gated) |
| Device parity P0–P6 | [Device parity](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/blob/main/docs/DEVICE-PARITY.md) |
| GitHub Releases | [最新发行版](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/releases) |

## 当前状态

```text
CBAP conformance: 114/114
最新源码发行版: v1.7.1
协议版本: CBAP v1
主传输: Unix socket NDJSON
可选: TCP / TLS / mTLS
```

## 系统一眼

```text
Agent
  │ CBAP-U
  ▼
CBAP Kernel
  │ 租约 / fencing / 审计 / estop / approval
  │ CBAP-D
  ▼
Driver
  ▼
MCP / Minecraft / Device
```

## 安全一句话

> Agent 可以自主运行，但 Kernel 不相信 Agent 自带的安全声明。  
> 默认普通 read/write/lease 不需要人工逐步审批；高风险审批是 policy 显式配置的例外。

## 文档边界

```text
README.md                 项目入口 / 安全摘要 / 快速开始
spec/                     CBAP 协议
docs/                     设计、审计、参数手册、里程碑
RELEASES.md               源码发行版与兼容性
docs/releases/            每个版本的 release notes
```

Wiki 页面只维护导航；不复制安全规范正文，避免和仓库版本漂移。

## 相关 Agent 子仓

- [cyberdyne](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/tree/main/agents/cyberdyne)
- [mcp-mineflayer](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/tree/main/agents/mcp-mineflayer)
- [mindcraft](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/tree/main/agents/mindcraft)
- [voyager](https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/tree/main/agents/voyager)
