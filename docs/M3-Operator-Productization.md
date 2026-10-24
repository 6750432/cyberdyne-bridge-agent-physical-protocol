# M3 · Operator Productization

**状态**：first slice implemented  
**日期**：2026-10-24  
**基线**：CBAP 98/98 tests  
**范围**：Console lease/审批；MCP onboarding/probe

---

## 1. Console lease

### 查看

`/api/status` 每台设备返回：

```json
{
  "lease": {
    "lease_id": "l-3",
    "fencing_token": 2,
    "agent_id": "mindcraft-1",
    "expires_at": 1790000000000
  },
  "pending": 1
}
```

UI 显示：

```text
lease owner
fencing token
pending count
Release lease
```

### Operator 释放 lease

```http
POST /api/lease/release
{"device_id": "mc://bot/DeepSeek"}
```

Kernel op：

```json
{"op":"admin_release","args":{"device_id":"..."}}
```

需要 `admin` capability；Kernel：

```text
清掉 lease
唤醒 lease waiters
取消该设备 pending
取消该设备 approvals
写 audit: admin_release
```

不调用 estop；需要停机时单独按 estop。

---

## 2. High-risk approval

### Policy

```json
{
  "approvals": {
    "devices": ["mc://bot/DeepSeek"],
    "ops": ["dig", "place", "give", "exec"],
    "ttl_ms": 60000
  }
}
```

只有 `ops` 非空才启用审批；不配置则保持原行为。

### 流程

```text
Agent write
  -> Kernel 检查 policy.approvals
  -> 命中：ack accepted；创建 approval；不立刻执行
  -> Console /api/approvals 看到 pending
  -> Operator Approve / Deny
  -> Approve：Kernel 重新校验 lease，再执行；agent 收到 result
  -> Deny：agent 收到 E_PERM
  -> Expire：agent 收到 E_TIMEOUT
```

审批 API：

```text
GET  /api/approvals
POST /api/approvals/approve {"approval_id":"ap-..."}
POST /api/approvals/deny    {"approval_id":"ap-..."}
```

Kernel ops：

```text
approval_list     admin
approval_approve  admin
approval_deny     admin
admin_release     admin
```

### 审计

```text
approval_request
approval_approve
approval_deny
approval_expired
approval_cancel
admin_release
```

### 安全规则

```text
普通 Agent 没有 admin
operator token 授予 admin
estop 不需要审批
resume 仍然 E_PERM
approval 不绕过 lease / fence / safe mode
approval 过期不执行
```

---

## 3. MCP onboarding

### 扫描

```http
POST /api/onboard/scan
{
  "command": ["python3", "server.py"],
  "cwd": "/path/to/server"
}
```

返回：

```json
{
  "ok": true,
  "server": {"name": "mcp-server", "version": "..."},
  "tools": [{"name":"turn_on","description":"...","inputSchema":{}}]
}
```

### 创建 manifest

```http
POST /api/onboard/create
{
  "device_id": "mcp://lab/light-01",
  "command": ["python3", "server.py"],
  "tools": [
    {"cbap_op": "turn_on", "tool": "turn_on"},
    {"cbap_op": "turn_off", "tool": "turn_off"}
  ],
  "facts": {"source": "tool", "tool": "get_state"},
  "estop": {"tool": "turn_off", "expect": {"on": false}}
}
```

写入：

```text
devices/onboarded/<safe-device-id>.json   0600
```

写 manifest 不启动 server；启动/探测在 probe 阶段。

### Probe

```http
GET  /api/onboard/list
POST /api/onboard/probe {"name":"<safe-device-id>"}
```

返回：

```text
health
describe
facts / estop
advertised tools
signed / pinned
verification
```

显式 `op` 才会执行工具；默认只读 health。

---

## 4. 验收

```text
[x] lease / fencing / pending 可见
[x] operator release lease
[x] approval policy
[x] approve / deny / expire
[x] approval audit
[x] onboarding scan
[x] manifest create
[x] probe / health
[x] UI + API
[x] 98/98 tests
```

部署注意：

```text
[ ] onboarding registry 目录权限 0700
[ ] 生产 manifest 签名
[ ] MCP 子进程独立 UID/sandbox
[ ] TCP TLS（如启用）
```

---

## 5. 仍未做

```text
双人审批
审批 SLA / 通知
设备注册表启用/禁用
多操作员角色
resume
```

不把“有 approval”误写成“有硬件安全认证”。
