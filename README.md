# Cyberdyne-Bridge · 赛博戴恩之桥

> **CBAP v1**：Agent ↔ 物理世界的参考协议桥。
> 主仓只负责协议、Kernel、租约、安全和审计；具体 Agent 放到独立子仓。
> Minecraft 只是低成本、可观测、可复现的物理沙盒。

[![CBAP 中文架构图](docs/diagrams/cbap-structure-zh.png)](docs/diagrams/cbap-structure-zh.png)

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

---

## 这是什么

一句话：

> **Agent 通过 CBAP 申请一个设备，执行动作，再用服务端事实校验结果。**

不是「让 LLM 直接操作 Minecraft」，而是把下面这些东西固定成协议：

```text
Agent
  │  CBAP-U：Unix socket，一行一条 JSON
  ▼
CBAP Kernel
  │  每设备租约 / FIFO 等待 / 安全模式 / 急停 / 审计
  │  CBAP-D：不同 Agent 的 adapter
  ▼
MCP / Mindcraft / Voyager / 我们自己的 MC Agent
  │
  ▼
Minecraft 服务端（事实源）
```

完成判据永远是：

```text
服务端事实 + 校验
```

不是：

```text
result.ok
「命令发出去了」
「adapter 说成功了」
```

## 四个活跃 Agent 子仓

主仓不把任何具体 Agent 写死进 Kernel。四个活跃子仓各自拥有 adapter、device/mapping、工具和 smoke：

| 子仓 | 归属 | 设备 | 控制面 |
|---|---|---|---|
| [`agents/cyberdyne`](agents/cyberdyne/) | 我们自己的 MC Agent | `mc://bot/DeepSeek` | 旧脑/手直连；手可被 `McDriver` 包成 CBAP 设备 |
| [`agents/mcp-mineflayer`](agents/mcp-mineflayer/) | 外部 | `mcp://mc/MCPBody` | MCP stdio JSON-RPC |
| [`agents/mindcraft`](agents/mindcraft/) | 外部 | `mc://mind/Mindy` | state / prompt / stop |
| [`agents/voyager`](agents/voyager/) | 外部 | `mc://voyager/bot` | state / exec / forward / say / stop |

Alice 未构建，放在 [`archive/alice`](archive/alice/)，不算活跃子仓。

每个子仓都有 `agent.json` 契约和独立 smoke：

```bash
python3 agents/cyberdyne/smoke.py
python3 agents/mcp-mineflayer/smoke.py
python3 agents/mindcraft/smoke.py
python3 agents/voyager/smoke.py
```

## 主仓结构

```text
kernel/       CBAP Kernel：会话 / 租约 / 安全 / 急停 / 审计
spec/         CBAP 协议与设备契约
tests/        conformance
tools/        通用工装（CBAP conformance / 并发 / 故障 / 恢复）
docs/         协议文档、迁移说明、架构图
agents/       四个活跃 Agent 子仓
archive/      Alice 归档
```

更完整的目录边界、兼容 shim 和迁移阶段见 [`docs/REPO_LAYOUT.md`](docs/REPO_LAYOUT.md)。

## 协议要点

| 做法 | 为什么 |
|---|---|
| **完成看服务端事实** | 背包、坐标、方块、任务终态才算数 |
| **每设备租约** | 同一设备同一时刻只有一个 writer；FIFO 等待 |
| **release / estop / cancel** | 正常释放、急停、取消是不同语义 |
| **幂等与在途请求** | 断线重连后不乱重放 |
| **fail-closed** | 拿不准就拒绝，并且出声 |
| **审计** | 每次动作有账可查 |
| **adapter 隔离** | Agent 实现不进 Kernel，主仓只依赖 driver 接口 |

协议细节：

- [`spec/README.md`](spec/README.md)
- [`spec/conformance-v1.md`](spec/conformance-v1.md)
- [`kernel/legacy_runtime/README.md`](kernel/legacy_runtime/README.md)

## 快速开始

只跑协议与控制面，不需要 Minecraft / LLM：

```bash
python3 tools/cbap_conformance.py --target fake
```

当前结果：

```text
61/61 tests passed
```

控制面本地实测：

```text
device_list  p50 0.221 ms / p95 0.374 ms
read body    p50 0.236 ms / p95 0.522 ms
```

跑四个 Agent 子仓的本地 smoke：

```bash
for d in agents/cyberdyne agents/mcp-mineflayer agents/mindcraft agents/voyager; do
  python3 "$d/smoke.py" || exit 1
done
```

真正接 Minecraft / MCP / Mindcraft / Voyager 时，先看对应子仓 README 和 `docs/`。

## 文档

```text
docs/diagrams/cbap-structure-zh.png    中文架构图
docs/REPO_LAYOUT.md                    主仓 / 子仓 / shim / 迁移
docs/CBAP-内核化设计-2026-10-23.md     Kernel 设计
docs/CBAP-同设备竞争与故障注入.md      竞争与故障
docs/CBAP-cancel与MCP恢复.md           cancel / MCP 恢复
agents/*/docs/                         各 Agent 自己的接入文档
```

## 旧子链

旧版 Cyberdyne 脑 / 手、车厢、老祖思维、日记和 M1–M7b 里程碑已经从主 README 移到：

- [`agents/cyberdyne/docs/LEGACY.md`](agents/cyberdyne/docs/LEGACY.md)

这是 Cyberdyne MC Agent 的子链档案，不是 CBAP 主链。

旧套件 `tools/跑全部.sh` 仍有搬迁前就存在的红项（bridge 指纹和几条旧逻辑）；不要把旧套件的红项和 CBAP 的 `61/61` 混在一起。详见 `docs/REPO_LAYOUT.md` 的 Verification。

## 关于皮肤

`assets/DeepSeek-skin.png` —— 小家伙的样子。皮肤是社区风格的自由素材。

## 许可

MIT，见 [`LICENSE`](LICENSE)。Minecraft 是 Mojang Studios 的商标，本项目与 Mojang 无关。
