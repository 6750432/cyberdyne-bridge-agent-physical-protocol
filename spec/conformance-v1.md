# CBAP v1 一致性用例（20 条）

- **状态**：Draft
- **对应规范**：`spec/cbap-v1.md`
- **目标**：任何声称 “CBAP v1 compatible” 的 Kernel / Driver / Agent SDK，至少要通过对应等级的用例。
- **跑法**：`python3 tools/cbap_conformance.py --target fake`（v0 只支持假手；真手目标在 cmdResult id 闭环前不声明）

等级：

- **Core**：1–5、6–14、19（控制面最小闭环）
- **Full**：Core + 15–18、20（状态/租约/恢复/安全）
- **Driver**：Full + `describe/watchdog/health` 三条驱动专项（并入 20）

> 每条用例都必须断言 **错误码**，不能只断言“失败了”。

| # | 用例 | 前置 | 操作 | 期望 |
|---|---|---|---|---|
| 1 | 首包必须是 hello | 新连接 | 直接发 `request` | `E_PROTOCOL`，连接关闭；审计有记录 |
| 2 | 版本不匹配 | 新连接 | `hello.v = "2.0"` | `E_VERSION`；不进入会话 |
| 3 | 认证失败 | TCP | 错误 token | `E_AUTH`；不泄露设备列表 |
| 4 | 未知消息类型 | 已 hello | `type:"wat"` | `E_PROTOCOL`；连接保持 |
| 5 | 未知 op | 已 hello | `op:"nope"` | `E_NOTSUP`；连接保持 |
| 6 | 打开不存在的设备 | 已 hello | `open("mc://nope")` | `E_NOENT` |
| 7 | 只读 fd 写入 | `open(mode:"r")` | `write` | `E_PERM`；无副作用 |
| 8 | 独占冲突 | 两个 Agent | 都 `open(mode:"exclusive")` | 第二个 `E_BUSY`；第一个仍可写 |
| 9 | 无数据读 | 已 open | `read(timeout_ms:0)` | `E_AGAIN`，不是 `E_TIMEOUT` |
| 10 | 读超时 | 已 open | `read(timeout_ms:50)` 且无数据 | `E_TIMEOUT` |
| 11 | 写生命周期 | 已 open + lease | `write(move)` | 先 `ack accepted`，后 `result` 且 `id` 相同 |
| 12 | 幂等写 | 已 open + lease | 同一 `idempotency_key` 连发两次 | 设备侧副作用只发生一次；两次 `result` 一致 |
| 13 | 取消 | 已 open + lease | 对长任务发 `cancel` | 目标 `result` 为 `E_CANCELED`；不再产生新副作用 |
| 14 | 急停 | 已 open + lease | `estop` | 返回 `safe_state`；后续 `write` 被 `E_SAFETY`/`E_PERM` 拒绝；审计有 `estop` |
| 15 | 状态序号 | 已 hello | 收 10 帧 `state` | `seq` 严格递增；人为丢一帧后 Agent 能检测 gap |
| 16 | 探针未到货 | 已 open | 下发 `dig` 后立刻查完成 | 不得判完成；返回 `running` 或 `E_STALE` |
| 17 | 租约过期 | 已 open + lease(ttl=50ms) | 等 100ms 后 `write` | `E_BUSY`；不得偷偷续租 |
| 18 | 断线释放 | 已 open + lease | 直接断开连接 | Kernel 释放租约、停动作；重连后需重新 `open` |
| 19 | 超大帧 | 已 hello | 发 >64KiB 单行 | `E_FRAME`；连接保持；内存不增长 |
| 20 | 驱动安全 | 驱动已注册 | 停发心跳 / 调 `estop` | 驱动进 `safe_state`；Kernel 存活；`health` 报 `degraded` |

## 驱动专项（并入 20 的扩展断言）

| # | 用例 | 期望 |
|---|---|---|
| D1 | `describe()` 缺 `safety.estop` | Kernel 拒绝注册，`E_INVAL` |
| D2 | `estop()` 返回 `ok:true` 但设备仍在动 | 判失败；驱动不得声明 compatible |
| D3 | `watchdog_ms` 超时 | 驱动自动 `estop`，无需 Agent 参与 |
| D4 | `health()` 返回 `ok:false` | Kernel 标记 `degraded`，拒绝新租约 |
| D5 | 驱动崩溃 | Kernel 不崩；设备标记 `offline`；租约释放 |

## 断言“有牙”的要求

- 每条用例必须能在**故意改坏一行**时变红；否则不算有牙。
- 错误码断言必须精确到 `code`，不能只匹配 `ok:false`。
- 超时/租约/幂等用例必须用**假时钟**或短 TTL，不能靠 `sleep(30)`。
- 安全用例必须在**假驱动**上验证副作用，不能只看返回值。
- 用例本身不得依赖 `bridge.py` 的内部类名；只依赖 CBAP 线格式。

## 当前执行状态（2026-10-23）

- 20 条 Core/Full 用例 + D1/D4/D5 已可由 `tools/cbap_conformance.py` 执行；
- D2/D3 仍列在驱动专项，未声称通过；
- 执行器使用假手，不碰真实 Minecraft。
