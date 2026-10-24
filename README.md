<div align="center">

# Cyberdyne Bridge

### 赛博戴恩之桥 · CBAP v1

**把异构 Minecraft Agent，变成同一个协议下的外设。**

[![CBAP](https://img.shields.io/badge/CBAP-v1-0f766e?style=flat-square)](spec/README.md)
[![Conformance](https://img.shields.io/badge/conformance-66%2F66-14b8a6?style=flat-square)](tools/cbap_conformance.py)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](kernel/)
[![Transport](https://img.shields.io/badge/CBAP--U-Unix%20socket-334155?style=flat-square)](spec/README.md)
[![No paid API](https://img.shields.io/badge/LLM-local%20friendly-6b7280?style=flat-square)](#)
[![License](https://img.shields.io/badge/license-MIT-111827?style=flat-square)](LICENSE)

[架构图](#架构) · [快速开始](#快速开始) · [四个子仓](#四个-agent-子仓) · [协议保证](#协议桥保证什么) · [文档](#文档)

</div>

> **Minecraft Agent 不缺能挖矿的脚本。**
>
> 缺的是一个**能换身体、能验收、能急停**的协议。

Cyberdyne Bridge 是 **CBAP v1** 的参考实现：Agent 申请设备、执行动作，最后用**服务端事实**验收，而不是相信一句 `result.ok`。

Minecraft 只是沙盒。真正想验证的是：

```text
信息不完整、动作有代价、环境会变的世界里，
Agent 到底需要什么样的接口与判据。
```

---

## 仓库简介

**主仓是协议，不是某个具体 Bot。**

```text
Agent
  │  CBAP-U：Unix socket / 一行一条 JSON
  ▼
CBAP Kernel
  │  租约 · FIFO · 安全 · 急停 · 取消 · 审计
  │  CBAP-D：每个 Agent 自己的 adapter
  ▼
MCP / Mindcraft / Voyager / Cyberdyne
  │
  ▼
Minecraft 服务端（事实源）
```

一句话：

> **Agent 可以换，身体可以换，验收判据不能换。**

这也是为什么主仓只保留 CBAP、Kernel、租约、安全、审计和 conformance；具体 Agent 放进独立子仓，不写死进内核。

## 30 秒看懂

```bash
# 不需要 Minecraft、不需要 LLM、不需要付费 API
python3 tools/cbap_conformance.py --target fake
```

当前：

```text
66/66 tests passed
```

四个 Agent 子仓各自有独立 smoke：

```bash
for d in agents/cyberdyne agents/mcp-mineflayer agents/mindcraft agents/voyager; do
  python3 "$d/smoke.py" || exit 1
done
```

## 它解决什么

| 常见做法 | 问题 | CBAP 的做法 |
|---|---|---|
| 让 LLM 直接调 Minecraft API | 幻觉、越权、失败后不知道停 | Agent 只能通过协议申请设备、提交动作 |
| 命令返回 200 就算完成 | 「发出去了」不等于「真做到了」 | 用位置、背包、方块、任务终态验收 |
| 多个 Agent 抢同一个 Bot | 操作互相踩、状态互相污染 | 每设备租约 + FIFO 等待 + 每设备急停 |
| 每接一个 Agent 就改主链 | 内核越来越胖，最后不可维护 | Agent 只实现 adapter，主仓只依赖 driver 接口 |
| 出问题只能翻聊天记录 | 没有审计、无法复盘 | JSONL 审计 + 明确的错误码 / 取消语义 |

## 架构

![CBAP 中文架构图](docs/diagrams/cbap-structure-zh.png)

图例：

```text
实线     = 动作 / 控制
青虚线   = 状态 / 事实 / 结果
金实线   = 自己的旧直连
金虚线   = 未构建 / 部分
```

完整说明见 [`docs/REPO_LAYOUT.md`](docs/REPO_LAYOUT.md) 和 [`spec/README.md`](spec/README.md)。

## 协议桥保证什么

| 保证 | 含义 |
|---|---|
| **每设备租约** | 同一设备同一时刻只有一个 writer；等待 FIFO，不靠抢 |
| **显式释放** | `release` / `estop` / `cancel` 是不同语义，不能混用 |
| **服务端事实** | 完成判据来自服务端位置、背包、方块、任务终态 |
| **fail-closed** | 拿不准就拒绝，并且留下原因，不静默吞掉 |
| **幂等与在途** | 断线重连不乱重放；危险状态可以急停 |
| **审计** | 每次动作有账可查，失败也有证据 |
| **Agent 隔离** | 具体 Agent 不进入 Kernel，adapter 可替换 |

## 四个 Agent 子仓

主仓不把 Agent 写死。四个活跃子仓各自拥有 adapter、`device.json` / `mapping.json`、工具和 smoke：

| 子仓 | 归属 | 设备 | 控制面 |
|---|---|---|---|
| [`agents/cyberdyne`](agents/cyberdyne/) | 我们自己的 MC Agent | `mc://bot/DeepSeek` | 旧脑 / 手直连；手可被 `McDriver` 包成 CBAP 设备 |
| [`agents/mcp-mineflayer`](agents/mcp-mineflayer/) | 外部 | `mcp://mc/MCPBody` | MCP stdio JSON-RPC |
| [`agents/mindcraft`](agents/mindcraft/) | 外部 | `mc://mind/Mindy` | state / prompt / stop |
| [`agents/voyager`](agents/voyager/) | 外部 | `mc://voyager/bot` | state / exec / forward / say / stop |

Alice 未构建，放在 [`archive/alice`](archive/alice/)，不算活跃子仓。

每个子仓的契约：

```text
agent.json
adapter / driver
device.json + mapping.json
upstream patch
smoke test
```

## 快速开始

### 只跑协议，不碰 Minecraft

```bash
python3 tools/cbap_conformance.py --target fake
```

你会看到：

```text
CBAP v1 conformance · target=fake · cases=65
Ran 61 tests

OK
```

### 跑四个子仓的本地 smoke

```bash
for d in agents/cyberdyne agents/mcp-mineflayer agents/mindcraft agents/voyager; do
  python3 "$d/smoke.py" || exit 1
done
```

### 接真实 Minecraft

分别看：

- [`agents/mcp-mineflayer/README.md`](agents/mcp-mineflayer/README.md)
- [`agents/mindcraft/README.md`](agents/mindcraft/README.md)
- [`agents/voyager/README.md`](agents/voyager/README.md)
- [`agents/cyberdyne/README.md`](agents/cyberdyne/README.md)

## 仓库结构

```text
kernel/       CBAP Kernel：会话 / 租约 / 安全 / 急停 / 审计
spec/         CBAP 协议与设备契约
tests/        conformance
tools/        通用工装（conformance / 并发 / 故障 / 恢复）
docs/         协议文档、迁移说明、中文架构图
agents/       四个活跃 Agent 子仓
archive/      Alice 归档
```

## 当前状态

```text
CBAP conformance       66/66
活跃 Agent 子仓        4
Alice                  源码归档，未构建
控制面 p50             0.2–0.3 ms
旧套件                 有搬迁前就存在的红项
```

旧套件 `tools/跑全部.sh` 的红项（bridge 指纹和几条旧逻辑）没有被伪装成绿色；它们是 legacy 子链的状态，不是 CBAP conformance 的结果。详见 [`docs/REPO_LAYOUT.md`](docs/REPO_LAYOUT.md) 的 Verification。

## 文档

```text
docs/diagrams/cbap-structure-zh.png    中文架构图
docs/REPO_LAYOUT.md                    主仓 / 子仓 / shim / 迁移
spec/README.md                         CBAP 协议
spec/conformance-v1.md                 conformance 契约
docs/CBAP-内核化设计-2026-10-23.md     Kernel 设计
docs/CBAP-同设备竞争与故障注入.md      竞争与故障
docs/CBAP-cancel与MCP恢复.md           cancel / MCP 恢复
drivers/mcp_device/README.md            通用 MCP 设备驱动 / facts 校验
tools/mcp_device_probe.py               单个 MCP 设备的事实探针
docs/MCP-device-audit-2026-10-24.md     MCP 回执 vs 事实审计
agents/*/docs/                         各 Agent 自己的接入文档
```

## 旧子链

旧版 Cyberdyne 脑 / 手、车厢、老祖思维、日记和 M1–M7b 里程碑已经从主 README 移到：

- [`agents/cyberdyne/docs/LEGACY.md`](agents/cyberdyne/docs/LEGACY.md)

这是 Cyberdyne MC Agent 的子链档案，不是 CBAP 主链。

## GitHub About（复制用）

> **CBAP v1：Agent ↔ 物理世界的参考协议桥。主仓只放协议、Kernel、租约、安全、审计；Cyberdyne / MCP / Mindcraft / Voyager 是四个 Agent 子仓。Minecraft 只是沙盒。**

可直接复制到 GitHub 仓库 About 的短描述，另见 [`REPO_DESCRIPTION.md`](REPO_DESCRIPTION.md)。

## 许可

MIT，见 [`LICENSE`](LICENSE)。Minecraft 是 Mojang Studios 的商标，本项目与 Mojang 无关。

---

## ⚠️ 免责声明 / Disclaimer

请在使用本项目前，务必仔细阅读以下全部条款。任何对本项目的 Clone、下载、编译、运行、修改或分发行为，均视为您已阅读、理解并同意本免责声明的全部内容。

### 🚫 1. 严禁滥用与公共服务器红线

- **仅限本地环境**：本项目（Cyberdyne-Bridge）仅限用于本地单机、局域网私服、AI Agent 架构研究。绝对禁止将本项目的任何代码、脚本或衍生程序用于任何未经官方授权的公共服务器（如 Hypixel、2B2T 等）。
- **封号风险自负**：由于本项目使用了无头客户端（mineflayer）并在底层实现了 0ms 反射弧和连击逻辑，在公共服务器运行时，极大几率会触发反作弊系统（如 Watchdog、NCP、Matrix）导致账号或 IP 被封禁。因违反服务器规则导致的一切后果，由使用者自行承担。
- **破坏游戏体验零容忍**：严禁利用本项目在多人游戏中恶意破坏他人游戏体验（如无理由屠杀、恶意破坏建筑等）。

### 🛡️ 2. AI 自主行为与物理环境风险

- **大模型幻觉**：本项目接入了云端或本地的 LLM（大语言模型）进行任务规划。尽管本地已实现 Fail-Closed（默认拒绝）的安全白名单和双向翻译器校验，但仍不能完全排除由于大模型幻觉、网络延迟或物理引擎 Bug 导致的意外行为（如误挖方块、误放物品、卡死、掉入岩浆等）。
- **资源与成本**：使用本项目调用云端 API 会产生 Token 费用。作者不承担任何因 API 泄漏、盗刷、费率变更或云端服务商条款变动导致的财务损失。
- **硬件红线**：项目内置了热保护与资源看护脚本，但使用者需自行评估本地硬件的承载能力。因不当配置导致的高温、死机、硬件损坏或存档丢失，作者概不负责。

### 🐧 3. 运行环境限制

- **Linux Only**：本项目深度依赖 `nice`、`ionice`、`xinput`、Unix Domain Socket 等 Linux 专属机制及标准库。目前仅支持 Linux（推荐 Linux Mint / Ubuntu），且未提供图形界面（无头模式）。
- **Windows 兼容性**：作者坚决不处理任何 Windows 环境下的兼容性问题或 Issues。如果你只有 Windows，请自行尝试 WSL2 或使用虚拟机。

### ⚖️ 4. 版权与第三方许可

- **非官方项目**：本项目为个人开源研究项目，与 Mojang Studios、Microsoft 或网易（中国版 MC）没有任何直接或间接的关联。Minecraft 是 Mojang Studios 的商标。
- **开源依赖**：项目依赖 mineflayer 等优秀的开源 Node.js 库，这些库遵循其各自的开源许可协议。
- **AI 协作声明**：本项目约 80% 的代码、全部测试用例、验收报告及安全断言，由 AI 助手（大肥鱼，基于 DeepSeek V4）自主编写。人类（作者）仅负责架构设计、安全红线制定及最终验收。本项目不提供任何形式的明示或暗示担保（AS IS）。

### 💸 5. 无担保声明

本项目按"原样（AS IS）"提供，不包含任何明示或暗示的保证，包括但不限于对适销性、特定用途适用性及非侵权的保证。在任何情况下，作者均不对任何索赔、损害或其他责任负责，无论是在合同诉讼、侵权行为还是其他方面，均不承担因本软件、本软件的使用或其他交易而产生或与之相关的责任。
