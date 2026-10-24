# Third-Party Notices / 第三方许可声明

Cyberdyne Bridge 的原创 Kernel、协议、驱动和测试代码采用 **MIT**（见根目录
[`LICENSE`](LICENSE)）。下列第三方组件、补丁、运行时依赖和名称不属于该 MIT
授权，按各自条款使用。

**这不是法律意见。** 如果你要发行组合产品，请让法律顾问复核。

---

## 1. 代码 / 补丁

| 组件 | 上游 | 许可 | 本仓位置 | 说明 |
|---|---|---|---|---|
| Mindcraft headless patch | [mindcraft-bots/mindcraft](https://github.com/mindcraft-bots/mindcraft) | MIT | `agents/mindcraft/adapter/patches/mindcraft-headless.patch` | 仅懒加载补丁；Mindcraft 仍是外部规划器 |
| Voyager state / spike patches | [MineDojo/Voyager](https://github.com/MineDojo/Voyager) | MIT | `agents/voyager/adapter/patches/*.patch` | 只接 Mineflayer bridge；不是 Voyager 自治 Python agent |
| mineflayer-mcp place patch | [swaynos/mineflayer-mcp](https://github.com/swaynos/mineflayer-mcp) | **GPL-3.0** | `agents/mcp-mineflayer/driver/patches/mineflayer-mcp-place.patch` | **不是 MIT**；只作为独立 GPL 外部组件的补丁分发 |

### GPL-3.0 边界

`mineflayer-mcp-place.patch` 是针对 GPL-3.0 上游源码的补丁。  
CBAP 的 MCP driver 通过 **stdio JSON-RPC 独立进程**调用该 server，不把
GPL 代码 import 进 Kernel。补丁文件本身按 GPL-3.0 分发，见：

```text
agents/mcp-mineflayer/driver/patches/LICENSE
third_party/licenses/mineflayer-mcp-GPL-3.0.txt
```

不要把该补丁应用到闭源 fork 后仍宣称整个产物是 MIT。

---

## 2. 运行时依赖（未 vendored）

这些包通过 npm / pip 安装，仓库不复制其源码；发布二进制时请一并保留其
license。版本以 `package.json` / lockfile / 实际安装为准。

| 包 | 许可 | 用途 |
|---|---|---|
| [mineflayer](https://github.com/PrismarineJS/mineflayer) | MIT | Minecraft 无头客户端 |
| [mineflayer-pathfinder](https://github.com/PrismarineJS/mineflayer-pathfinder) | MIT | 可选寻路 |
| [mineflayer-collectblock](https://github.com/PrismarineJS/mineflayer-collectblock) | MIT | 收集方块 |
| [prismarine-physics](https://github.com/PrismarineJS/prismarine-physics) | MIT | 物理数据/规则 |
| Minecraft data / prismarine-* 传递依赖 | 各自 MIT 等 | mineflayer 依赖树 |
| Python 标准库 | PSF-2.0 | Kernel / 工具 |
| MCP SDK（如安装） | 以上游为准 | 外部 MCP 生态 |

对应 license 文本在：

```text
third_party/licenses/
```

---

## 3. 外部进程 / 服务

| 名称 | 许可 / 条款 | 关系 |
|---|---|---|
| [mineflayer-mcp](https://github.com/swaynos/mineflayer-mcp) | GPL-3.0 | 独立 stdio 进程；不是本仓 MIT 代码 |
| [Mindcraft](https://github.com/mindcraft-bots/mindcraft) | MIT | 外部 Agent；本仓只有 adapter/patch |
| [Voyager](https://github.com/MineDojo/Voyager) | MIT | 外部 Agent bridge；规划器未接入 |
| Minecraft Java / Mojang / Microsoft | 专有 | 未分发游戏本体或服务端；仅互操作 |
| DeepSeek / Qwen 等模型 | 各自模型条款 | 未分发模型权重；仅名称/兼容性提及 |
| xdg-desktop-portal / Wayland / X11 | 各自开源许可 | 本机输入/截图后端；非本仓代码 |

### 媒体 / 截图

```text
assets/DeepSeek-skin.png
site/assets/deepseek-skin.png
```

这是社区风格的 Minecraft 皮肤素材，不是 Mojang 官方素材；再分发前请自行
确认素材来源与授权。

仓库中的 CBAP 架构图、CBAP OS 截图和终端截图由本项目制作；截图中的
Minecraft 画面/名称仅用于说明互操作，不构成对游戏素材的再许可。

---

## 4. 名称与商标

详见 [`TRADEMARKS.md`](TRADEMARKS.md)。

```text
Minecraft 是 Mojang Studios / Microsoft 的商标。
本项目不是 Mojang、Microsoft、网易、DeepSeek、Qwen、
Mindcraft、Voyager 或 mineflayer-mcp 的官方项目，
也不代表它们背书。
```

---

## 5. 原创代码许可

根目录 `LICENSE` 的 MIT 文本适用于 CBAP 原创代码。  
第三方补丁/依赖/名称不因被本仓引用而改许可。

如果你分发本仓的修改版：

```text
保留根 LICENSE
保留 THIRD_PARTY_NOTICES.md
保留 third_party/licenses/
保留每个补丁旁的 license（如适用）
不要移除上游版权头
```

---

## 6. 免责声明

见 [`DISCLAIMER.md`](DISCLAIMER.md) 和 [`SECURITY.md`](SECURITY.md)。
