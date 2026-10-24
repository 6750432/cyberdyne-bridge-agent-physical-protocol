# MC Body API v0

**状态：** Draft  
**传输：** Unix Domain Socket + NDJSON  
**MC 版本：** 1.21.1  
**SDK：** Python 3.10+（第一版）  
**控制面：** 不在 Body 内；CBAP 由 McDriver 包装

---

## 1. 设计目标

```text
持久连接
状态推送
任务级动作
ack + result
cancel
batch
可测量
不依赖 LLM
不依赖 CBAP
```

Body 不知道 CBAP，也不知道 LLM。  
它只做“Minecraft 身体”。

---

## 2. 传输

```text
Unix socket
每行一个 JSON
UTF-8
单行 <= 64 KiB
请求/响应带 id
```

Socket 权限：

```text
0600
只允许本用户
默认不监听 TCP
```

---

## 3. 消息

### 3.1 Client -> Body

#### hello

```json
{"v":"mc-body/1","type":"hello","id":"h-1","client":"qwen-agent"}
```

#### command

```json
{
  "v":"mc-body/1",
  "type":"command",
  "id":"r-1",
  "cmd":"goto",
  "args":{"x":10,"y":64,"z":-3,"range":1.5},
  "deadline_ms":15000
}
```

#### cancel

```json
{"v":"mc-body/1","type":"cancel","id":"c-1","target":"r-1"}
```

#### health

```json
{"v":"mc-body/1","type":"health","id":"h-2"}
```

#### shutdown

```json
{"v":"mc-body/1","type":"shutdown","id":"s-1"}
```

### 3.2 Body -> Client

#### welcome

```json
{
  "v":"mc-body/1",
  "type":"welcome",
  "id":"h-1",
  "body_id":"mc-body-1",
  "mc_version":"1.21.1",
  "capabilities":["goto","collect","craft","equip","dig","place","say","stop","batch"]
}
```

#### ack

```json
{"v":"mc-body/1","type":"ack","id":"r-1","state":"accepted","t":179...}
```

#### state

```json
{
  "v":"mc-body/1",
  "type":"state",
  "seq":42,
  "t":179...,
  "body":{
    "pos":[10.5,64,-3.5],
    "yaw":0.0,
    "pitch":0.0,
    "hp":20,
    "food":20,
    "on_ground":true,
    "held":"stone_pickaxe",
    "inventory":{"oak_log":3,"cobblestone":8},
    "nearby_blocks":[{"name":"stone","pos":[11,63,-3]}],
    "players":[]
  }
}
```

#### result

```json
{
  "v":"mc-body/1",
  "type":"result",
  "id":"r-1",
  "ok":true,
  "facts":{
    "reached":true,
    "position":[10.5,64,-3.5],
    "state_seq":42,
    "duration_ms":820
  },
  "error":null
}
```

失败：

```json
{
  "v":"mc-body/1",
  "type":"result",
  "id":"r-1",
  "ok":false,
  "facts":null,
  "error":{"code":"E_PATH","message":"no path","retryable":true}
}
```

#### event

```json
{"v":"mc-body/1","type":"event","kind":"chat","t":179...,"data":{"username":"x","message":"hi"}}
```

#### health

```json
{"v":"mc-body/1","type":"health","id":"h-2","ok":true,"mc_connected":true,"uptime_ms":1234}
```

---

## 4. 命令

### primitive

| cmd | args | facts |
|---|---|---|
| `goto` | x,y,z,range? | reached, position, state_seq, duration_ms |
| `dig` | x,y,z | block, dropped?, state_seq |
| `place` | x,y,z,item? | placed, block, state_seq |
| `equip` | item | held |
| `look` | yaw,pitch | yaw,pitch |
| `say` | text | sent |
| `stop` | — | stopped |

### task

| cmd | args | facts |
|---|---|---|
| `collect` | block,count,radius? | collected, inventory |
| `craft` | item,count | crafted, inventory |
| `smelt` | item,count,fuel? | output, inventory |
| `deposit` | container,item,count | stored, inventory |
| `batch` | steps[] | completed, failed_at |

### 语义

```text
一个连接同一时刻最多一个 active task 在跑
primitive 可以短任务
task 内部由 Body 本地循环
cancel 只取消当前 task
stop 是安全停止：停止移动/挖/攻击，释放按键
```

---

## 5. 状态

最低字段：

```text
pos / yaw / pitch
hp / food / on_ground
held
inventory
nearby_blocks
players
```

推送：

```text
默认 5–10 Hz
状态变化可立即推
seq 单调递增
```

---

## 6. 错误码

```text
E_INVAL       参数错误
E_NOTSUP      不支持的命令
E_BUSY        已有 active task
E_TIMEOUT     deadline
E_CANCELED    被 cancel
E_NOENT       目标方块/容器/物品不存在
E_PATH        寻路失败
E_SAFETY      安全拒绝（例如公共服务器策略/危险动作）
E_IO          连接/服务器错误
E_INTERNAL    未分类
```

---

## 7. Latency / 指标

Body 在 result 中返回：

```text
duration_ms
state_seq
queue_ms
```

SDK 记录：

```text
ack_ms
result_ms
state_age_ms
cancel_ms
```

目标：

```text
ack p50 < 50ms
ack p95 < 150ms
state age p95 < 250ms
cancel < 500ms
```

---

## 8. 安全

```text
默认 UDS only
socket 0600
不执行 shell
不接受任意路径
不接公共服务器
不把 MC 账号/服务器地址写进仓库
stop 必须释放所有控制键
```

---

## 9. 版本

```text
v: mc-body/1
向后兼容：只加字段，不改语义
破坏性变更：升 mc-body/2
```

---

## 10. 与 CBAP 的关系

```text
Body 不知道 CBAP
McDriver 把 Body command 映射成 CBAP write
CBAP lease / estop / audit / facts 在 Kernel 层
SDK 可以直连 Body（开发/benchmark）
生产 Agent 建议走 CBAP
```

## 11. 示例：SDK

```python
from sdk.python.mc_body_client import MCBodyClient

body = MCBodyClient("/tmp/mc-body.sock")
body.connect()
body.goto(10, 64, -3)
body.collect("oak_log", 3)
body.craft("stone_pickaxe", 1)
body.stop()
body.close()
```
