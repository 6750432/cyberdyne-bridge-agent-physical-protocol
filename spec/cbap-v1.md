# CBAP v1 · Cyberdyne Bridge Agent Protocol

- **状态**：Draft（规范草案，未实现）
- **版本**：1.0.0
- **日期**：2026-10-23
- **范围**：Agent ↔ Kernel 的系统调用 ABI（CBAP-U），以及 Kernel ↔ Driver 的驱动 ABI（CBAP-D）
- **不包含**：Minecraft 动作语义、驱动实现、包管理器、具体调度算法

> 本文用 RFC 2119 的关键词：**MUST / MUST NOT / SHOULD / SHOULD NOT / MAY**。

---

## 1. 目标与非目标

### 1.1 目标

1. 让 Java / Node / Python / MCP Agent 用同一套调用访问不同身体（MC bot、机械臂、四足）。
2. 让内核与 Minecraft 解耦：`dig` / `craft` 属于驱动方言，不属于内核。
3. 让驱动可热插拔、可一致性测试、可版本化。
4. 让安全动作（`estop`）优先于普通动作，且不依赖 Agent 配合。
5. 让每次调用有 `id`、`deadline`、`errno`、审计记录。

### 1.2 非目标

- 不规定 MC 方块/配方/物品表；这些由 `mc-driver` 提供。
- 不规定机械臂的关节/力矩协议；这些由 `robot-driver` 提供。
- 不规定包管理器格式；见后续 `cbap-pkg` 草案。
- 不承诺硬实时；v1 是控制面协议，硬实时数据面另议（见 §12）。

---

## 2. 角色与分层

```
┌──────────────────────────────────────────────┐
│ Agent（用户态）                               │
│  Java / Node / Python / MCP / LLM            │
└───────────────┬──────────────────────────────┘
                │ CBAP-U（系统调用）
┌───────────────▼──────────────────────────────┐
│ Kernel                                       │
│  scheduler / safety / device manager / task  │
└───────────────┬──────────────────────────────┘
                │ CBAP-D（驱动 ABI）
┌───────────────▼──────────────────────────────┐
│ Driver                                       │
│  mc-driver / robot-arm / quadruped           │
└───────────────┬──────────────────────────────┘
                │ 设备协议
┌───────────────▼──────────────────────────────┐
│ Device（Minecraft / 机械臂 / 四足）           │
└──────────────────────────────────────────────┘
```

- **Agent**：只调用 CBAP-U；不直接碰设备。
- **Kernel**：调度、安全、设备管理、任务/记忆、审计；不认识设备方言。
- **Driver**：把 CBAP-D 翻译成设备协议；负责设备级安全状态。
- **Device**：真实身体。
- **Lease**：写租约；同一 actuator 同时只有一个 writer。

---

## 3. 传输与分帧

### 3.1 传输绑定

v1 **MUST** 支持：

- Unix domain socket（默认）；
- TCP `127.0.0.1` + token（可选，跨容器/Windows 时用）。

v1 **MAY** 支持：共享内存、串口、CAN、ROS 2/DDS（作为 v1.x 扩展）。

### 3.2 分帧

- v1 控制面 **MUST** 使用 UTF-8 NDJSON：一行一个 JSON object，`\n` 结尾。
- 单行 **MUST NOT** 超过 64 KiB；超过 → `E_FRAME`，丢弃该行。
- 空行 **MUST** 忽略。
- 解析失败 **MUST** 返回 `E_PROTOCOL`，且 **MUST NOT** 崩溃。
- 二进制/高频数据面 **MAY** 使用 CBOR / Protobuf / 共享内存；必须在 `hello` 中协商 `encoding`。

### 3.3 连接与重连

- Agent 连接后 **MUST** 先发 `hello`；否则 kernel **MUST** 返回 `E_PROTOCOL` 并关闭。
- Kernel **MUST** 在 `welcome` 中返回 `protocol`、`kernel_id`、`limits`、`devices`。
- 断线重连 **MUST** 使用新的 `session_id`；`state.seq` 由 Kernel 单调递增，Agent 用它判断丢帧。
- 重连后 **MUST NOT** 自动重放未确认的 `write`；需要重放时用 `idempotency_key`。

---

## 4. 消息信封

所有消息 **MUST** 是 JSON object，并包含：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `v` | string | 是 | 协议版本，v1 固定 `"1.0"` |
| `type` | string | 是 | 消息类型（见 §5） |
| `ts` | integer | 是 | Unix epoch 毫秒；仅用于日志/跨进程戳 |
| `id` | string | 条件 | 请求/响应/取消/错误必填；`state`/`event` 可省略 |
| `seq` | integer | 条件 | `state`/`event` 必填；单调递增 |
| `op` | string | 条件 | `request` 必填，系统调用名 |
| `args` | object | 条件 | `request` 必填 |
| `ok` | boolean | 条件 | `result` 必填 |
| `error` | object | 条件 | 失败时必填；见 §9 |
| `payload` | object | 否 | 结果/事件/状态载荷 |

- 未知字段 **MUST** 被忽略（向前兼容）。
- 未知 `type` **MUST** 返回 `E_PROTOCOL`。
- 未知 `op` **MUST** 返回 `E_NOTSUP`，**MUST NOT** 断开连接。

### 4.1 时间

- `ts`：Unix epoch 毫秒，用于日志与跨进程比较。
- `t_mono`：发送方单调钟毫秒，用于本机判据；**MUST NOT** 跨进程相减。
- `deadline_ms`：相对当前时刻的毫秒数；`0` 表示“尽快”，不是“无限”。

### 4.2 ID

- `id` **MUST** 在单个 session 内唯一；建议 UUIDv7 / ULID。
- 响应 **MUST** 回带请求的 `id`。
- `idempotency_key` **MAY** 用于 `write`；相同 key 的重试 **MUST** 至多产生一次副作用。

---

## 5. 消息类型

### 5.1 `hello`（Agent → Kernel）

```json
{
  "v": "1.0",
  "type": "hello",
  "id": "01J...",
  "ts": 1700000000000,
  "agent_id": "mindcraft-1",
  "role": "agent",
  "auth": {"token": "..."},
  "encoding": "json",
  "capabilities": ["read", "write", "lease"],
  "limits": {"max_inflight": 4}
}
```

- `agent_id` **MUST** 稳定且唯一；同一 agent 重连可复用。
- `auth.token` 在 TCP 下 **MUST**；UDS 下 **MAY**（用 peer credentials）。
- `capabilities` 是请求的权限，不是授予；kernel 在 `welcome` 中返回实际权限。

### 5.2 `welcome`（Kernel → Agent）

```json
{
  "v": "1.0",
  "type": "welcome",
  "id": "01J...",
  "ts": 1700000000000,
  "kernel_id": "cyberdyne-main",
  "protocol": "1.0",
  "session_id": "01J...",
  "encoding": "json",
  "capabilities": ["read", "write", "lease"],
  "limits": {"max_frame": 65536, "max_inflight": 4, "rate_hz": 20},
  "devices": [
    {"device_id": "mc://bot/DeepSeek", "type": "minecraft-java", "state": "ready"}
  ]
}
```

- 版本不匹配 **MUST** 返回 `E_VERSION` 并关闭。
- `devices` **MAY** 为空；Agent 可用 `device_list` 刷新。

### 5.3 `request`（Agent → Kernel）

```json
{
  "v": "1.0",
  "type": "request",
  "id": "r-42",
  "ts": 1700000000000,
  "op": "write",
  "args": {
    "fd": "fd-7",
    "frame": {"channel": "body", "op": "move", "args": {"dir": [1, 0], "ms": 500}}
  },
  "deadline_ms": 2000,
  "idempotency_key": "move:1"
}
```

### 5.4 `ack`（Kernel → Agent）

```json
{"v":"1.0","type":"ack","id":"r-42","ts":1700000000000,"state":"accepted"}
```

- `state` 取值：`accepted` / `running`。
- `ack` 只表示“受理”，**不代表完成**。
- 需要终态的调用 **MUST** 再发 `result`。

### 5.5 `progress`（Kernel → Agent）

```json
{"v":"1.0","type":"progress","id":"r-42","ts":1700000000100,"progress":0.4,"detail":{"step":"walking"}}
```

- `progress` 是 0..1 的浮点数；未知时可省略。
- 高频进度 **SHOULD** 合并/限流。

### 5.6 `result`（Kernel → Agent）

```json
{
  "v": "1.0",
  "type": "result",
  "id": "r-42",
  "ts": 1700000000500,
  "ok": true,
  "payload": {"fd": "fd-7"},
  "facts": {"block": "air"}
}
```

- `ok:true` **不代表任务完成**；完成由 `facts` + `verify` 判据决定（见 §8）。
- `facts` **SHOULD** 是可复核的事实（方块、物品增量、位置、力矩等）。
- 失败时 `ok:false` + `error`。

### 5.7 `event`（Kernel → Agent）

```json
{"v":"1.0","type":"event","seq":101,"ts":1700000000600,"kind":"chat","payload":{"from":"mintstar","text":"..."}}
```

- `kind` 由设备/内核定义：`chat` / `damage` / `arrived` / `blocked` / `lease_lost` / `device_offline` / `safety`。
- `event` 是异步的；Agent **MUST NOT** 假设事件顺序跨设备一致。

### 5.8 `state`（Kernel → Agent）

```json
{
  "v": "1.0",
  "type": "state",
  "seq": 102,
  "ts": 1700000000700,
  "t_mono": 123456,
  "device_id": "mc://bot/DeepSeek",
  "payload": {
    "body": {"pos": [0, 64, 0], "hp": 20, "food": 20},
    "inventory": {"oak_log": 3},
    "world": {"scan_seq": 7}
  }
}
```

- `seq` **MUST** 单调递增；Agent 用它检测丢帧。
- `payload` 是设备方言；schema 由 `device.json` 的 `schemas` 声明。
- 默认频率由 `limits.rate_hz` 控制；Agent **MAY** 用 `subscribe`（v1.x）调整。

### 5.9 `cancel`（Agent → Kernel）

```json
{"v":"1.0","type":"cancel","id":"c-1","ts":1700000000800,"target":"r-42","reason":"user_abort"}
```

- `cancel` 是幂等的；已完成的请求返回 `ok:true`，不报错。
- 取消别人发起的请求 **MUST** 需要 `admin` 权限，否则 `E_PERM`。

### 5.10 `error`

```json
{"v":"1.0","type":"error","id":"r-42","ts":1700000000900,"error":{"code":"E_TIMEOUT","message":"deadline exceeded","retryable":true}}
```

- 协议级错误（无对应 `id`）也 **MUST** 带 `id`（可为新 ID）和 `error`。

---

## 6. CBAP-U：Agent 系统调用

### 6.1 `open`

```json
{"op":"open","args":{"device_id":"mc://bot/DeepSeek","mode":"rw"}}
```

- `mode`：`r` / `rw` / `exclusive`。
- 返回 `{"fd":"fd-7","device_id":"..."}`。
- `exclusive` **MUST** 获得写租约；拿不到 → `E_BUSY`。
- 无权限 → `E_PERM`；设备不存在 → `E_NOENT`。

### 6.2 `close`

```json
{"op":"close","args":{"fd":"fd-7"}}
```

- **MUST** 释放租约、取消未完成请求、停动作（不是 `estop`）。
- 已关闭 fd → `E_NOENT`（幂等可返回 `ok:true`，但 **SHOULD** 带 `already_closed:true`）。

### 6.3 `read`

```json
{"op":"read","args":{"fd":"fd-7","channel":"body","timeout_ms":1000}}
```

- 返回 `{"frame":{...}}`；无新数据 → `E_AGAIN`。
- `timeout_ms` 到期 → `E_TIMEOUT`。
- 只读 fd 可读；写 fd 也可读（除非 `mode=r` 限制）。

### 6.4 `write`

```json
{"op":"write","args":{"fd":"fd-7","frame":{"channel":"body","op":"move","args":{"dir":[1,0],"ms":500}}},"deadline_ms":2000}
```

- 成功 → `ack accepted`，随后 `result`。
- 需要写租约；没有 → `E_BUSY` / `E_PERM`。
- `deadline_ms` 到期 → `E_TIMEOUT`；副作用是否发生由 `result.facts` 说明。
- 设备拒绝（安全/前置条件）→ `E_SAFETY` / `E_INVAL`。

### 6.5 `ioctl`

```json
{"op":"ioctl","args":{"fd":"fd-7","request":"scan","args":{"radius":12,"step":2}}}
```

- `request` 是设备特定操作；未知 → `E_NOTSUP`。
- 返回 `{"payload":{...}}` 或 `E_AGAIN`（长操作）。
- `ioctl` **MUST NOT** 绕过安全策略；危险请求仍可被 `E_SAFETY` 拒绝。

### 6.6 `poll`

```json
{"op":"poll","args":{"fds":["fd-7"],"events":["readable","event"],"timeout_ms":1000}}
```

- 返回 `{"events":[{"fd":"fd-7","kind":"readable"}]}`。
- 超时无事件 → `ok:true` + 空数组（不是错误）。

### 6.7 `lease`

```json
{"op":"lease","args":{"fd":"fd-7","mode":"write","ttl_ms":30000}}
```

- 返回 `{"lease_id":"l-1","expires_at":1700000030000}`。
- 同一 actuator 同时只能有一个写租约；冲突且未请求等待 → `E_BUSY`。
- 可选 `wait_ms`：冲突时进入 FIFO 等待队列；`release`、estop 或租约过期后交给队首；超时 → `E_TIMEOUT`。
- 租约过期 **MUST** 自动释放；未续租的 writer **MUST NOT** 继续写。

### 6.7.1 `release`

```json
{"op":"release","args":{"fd":"fd-7"}}
```

- 主动释放当前 fd 持有的租约，不关闭 fd、不触发 estop。
- 返回 `{"released":true}`；没有持有租约时 `released:false`。
- 释放后队首 waiter 可取得租约。

### 6.8 `estop`

```json
{"op":"estop","args":{"fd":"fd-7","reason":"operator"}}
```

- **MUST** 总是允许（安全优先），不受租约/权限限制；但 **MUST** 审计。
- 返回 `{"safe_state":"idle"}`。
- `estop` 后恢复写 **MUST** 需要 `admin` 权限或重新 `open`（由内核策略决定）。
- 设备驱动 **MUST** 在收到 `estop` 后进入安全状态；不能只回 `ok:true`。

### 6.9 `stat`

```json
{"op":"stat","args":{"fd":"fd-7"}}
```

- 返回设备描述符、健康、能力、限额、当前租约。
- Agent **SHOULD** 在 `open` 后先 `stat`，不要假设能力。

### 6.10 `device_list`

```json
{"op":"device_list","args":{}}
```

- 返回 `{"devices":[{"device_id":"...","type":"...","state":"ready"}]}`。
- 无权限的设备 **MUST NOT** 出现。

---

## 7. CBAP-D：驱动 ABI

驱动 **MUST** 实现以下方法（进程内库或独立进程均可；v1 推荐独立进程）：

| 方法 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `describe()` | — | `device.json` | 设备描述符；启动时注册 |
| `open(channel, mode)` | channel, mode | handle | 打开通道 |
| `read(handle, timeout)` | handle, timeout | frame | 读状态；可 `E_AGAIN` |
| `write(handle, frame, deadline)` | handle, frame, deadline | result | 下发动作 |
| `ioctl(handle, request, args)` | handle, request, args | payload | 设备特有操作 |
| `poll(handles, timeout)` | handles, timeout | events | 事件 |
| `estop()` | — | safe_state | 安全状态；必须幂等 |
| `health()` | — | `{ok, detail}` | 健康检查 |
| `watchdog(heartbeat_ms)` | heartbeat_ms | — | 心跳；超时进安全状态 |

要求：

- `describe()` **MUST** 返回符合 `device.schema.json` 的描述符。
- `estop()` **MUST** 幂等、**MUST** 不依赖 Agent 配合、**MUST** 在 `watchdog` 超时后自动触发（由驱动/硬件实现）。
- `write()` **MUST** 在安全边界外返回 `E_SAFETY`，不能“先动再说”。
- 驱动 **MUST** 把设备错误映射到 §9 的 errno；不能只返回自由文本。
- 驱动 **SHOULD** 在 `describe()` 中声明 `schemas`，让 Kernel/Agent 校验 payload。

### 7.1 驱动注册

v1 允许两种绑定：

1. **进程内**：驱动是 Kernel 加载的库；适合可信驱动、快速原型。
2. **独立进程**：驱动通过 CBAP-D socket 连接 Kernel；适合不可信/多语言驱动。

独立进程 handshake：

```json
{"v":"1.0","type":"driver_hello","id":"...","ts":...,"device":{...},"pid":1234}
{"v":"1.0","type":"driver_welcome","id":"...","ts":...,"kernel_id":"...","session_id":"..."}
```

之后 Kernel 发 `driver_request`，驱动回 `driver_result`；消息体复用 §4/§5 的 `id`/`op`/`args`/`error` 语义。

---

## 8. 能力、技能与完成判据

### 8.1 能力

`device.json` 的 `capabilities` **MUST** 从下表选取（可扩展，但扩展名 **MUST** 带命名空间）：

`locomotion` / `manipulation` / `vision` / `inventory` / `chat` / `crafting` / `container` / `combat` / `audio`

### 8.2 技能

Kernel 的规划器按技能选动作，不硬编码 `dig`：

```json
{
  "name": "break_block",
  "requires": ["manipulation", "vision"],
  "args_schema": {"p": "vec3"},
  "preconditions": [{"type": "block_exists", "p": "$args.p"}],
  "effects": [{"type": "block_gone", "p": "$args.p"}],
  "verify": {"type": "block", "p": "$args.p", "equals": "air"},
  "cost": {"time_ms": 1000, "energy": 0.1}
}
```

- `verify` **MUST** 是可复核的事实判据，不能是“命令发出去了”。
- 技能由驱动/模块提供；Kernel 只做注册、校验、调度。

### 8.3 完成判据

- `result.ok` 只代表“这次调用成功”，不代表任务完成。
- 任务完成 **MUST** 由 `verify` + `facts` 判断；没有 `verify` 的动作 **MUST** 被 Kernel 拒绝注册（fail-closed）。
- 探针未到货/状态过期 → **MUST NOT** 判完成；返回 `E_STALE` 或保持 `running`。

---

## 9. 错误码

| code | 含义 | 可重试 |
|---|---|---|
| `E_VERSION` | 协议版本不匹配 | 否 |
| `E_PROTOCOL` | 帧/字段/类型错误 | 否 |
| `E_AUTH` | 未认证 | 否 |
| `E_PERM` | 无权限 | 否 |
| `E_NOENT` | 设备/fd/请求不存在 | 否 |
| `E_BUSY` | 租约冲突/资源忙 | 是（退避） |
| `E_AGAIN` | 暂无数据/背压 | 是 |
| `E_TIMEOUT` | 截止时间到 | 是（视副作用） |
| `E_INVAL` | 参数非法 | 否 |
| `E_NOTSUP` | 不支持的操作/能力 | 否 |
| `E_IO` | 设备/传输错误 | 是 |
| `E_CANCELED` | 已取消 | 否 |
| `E_SAFETY` | 安全策略拒绝 | 否 |
| `E_STALE` | 状态过期/探针未到 | 是 |
| `E_FRAME` | 帧过大/格式错误 | 否 |
| `E_INTERNAL` | 内核内部错误 | 是 |

- `error` 对象 **MUST** 包含 `code`、`message`；**SHOULD** 包含 `retryable`、`detail`。
- 程序 **MUST** 按 `code` 分支，**MUST NOT** 解析 `message`。

---

## 10. 权限、租约与安全

### 10.1 权限

Agent 的权限至少包括：

- `read`：读状态/事件；
- `write`：写动作；
- `lease`：申请写租约；
- `estop`：急停（默认授予所有已认证 Agent）；
- `admin`：恢复、改策略、取消他人请求、加载驱动。

权限在 `welcome.capabilities` 中授予；未授予的调用 → `E_PERM`。

### 10.2 租约

- 写 actuator **MUST** 持有写租约。
- 读 **MAY** 共享；`exclusive` 打开会阻止其他写者。
- 租约 **MUST** 有 TTL；过期自动释放；续租用 `lease` 同 fd。
- Agent 崩溃/断线 → Kernel **MUST** 释放其租约并停动作。

### 10.3 安全

- `estop` **MUST** 优先于所有普通请求；Kernel **MUST** 先处理 `estop`。
- 安全状态由驱动定义（`safety.estop`），不能只回 `ok:true`。
- 硬件看门狗 **SHOULD** 独立于 Kernel；Kernel 崩溃时硬件仍能进安全状态。
- 所有 `estop`、权限变更、驱动加载 **MUST** 审计。

---

## 11. 版本与兼容

- `v` 使用 `MAJOR.MINOR`；v1 为 `"1.0"`。
- MAJOR 变化：不兼容；Kernel **MUST** 拒绝并返回 `E_VERSION`。
- MINOR 变化：只加字段/消息/错误码；旧 Agent **MUST** 忽略未知字段。
- 未知 `op` → `E_NOTSUP`；未知 `type` → `E_PROTOCOL`；两者都 **MUST NOT** 崩溃。
- 删除字段/改语义 **MUST** 升 MAJOR；并提供至少一个 MINOR 的弃用期。

---

## 12. 数据面与实时性（v1.x 方向）

v1 控制面是 JSON/NDJSON，适合 MC（1–20 Hz）和低频机器人指令；**不适合** 1 kHz 硬实时控制。

- 高频传感器/关节控制 **SHOULD** 走驱动内的实时线程/共享内存/ROS 2，不经过 JSON 控制面。
- Kernel 负责监督、授权、安全；实时环由驱动/RT 控制器负责。
- 若需要跨机，**SHOULD** 用 DDS/ROS 2 或共享内存 + 序列化，不要用 TCP+JSON 跑 1 kHz。

---

## 13. 一致性

实现 **MUST** 通过 `spec/conformance-v1.md` 的 20 条用例，才能声明“CBAP v1 compatible”。

一致性等级：

- **Core**：hello/welcome、open/close、read/write、error、state、estop；
- **Full**：Core + ioctl/poll/lease/stat/device_list/cancel；
- **Driver**：Full + CBAP-D 的 describe/watchdog/health。

---

## 14. 示例

见：

- `spec/examples/session.ndjson`：一次 Agent 会话；
- `spec/examples/mc-device.json`：MC 驱动描述符；
- `spec/examples/robot-arm-device.json`：机械臂描述符；
- `spec/examples/mapping-mc.json`：MC 动作映射。

---

## 15. 开放问题

1. `state` 是推送还是拉取？v1 默认推送；`subscribe` 放到 v1.1。
2. 多 Kernel /多身体路由：v1 单 Kernel；跨 Kernel 用 `device_id` 路由，协议待定。
3. 包管理器 `cbap-pkg`：包格式、签名、仓库索引待定。
4. 安全认证：v1 只定义软件契约，不替代硬件安全认证/FMEA。
5. 中文/英文命名：v1 的 `op`/`code`/字段名 **MUST** 用 ASCII；人类可读文本可本地化。
