# M3 · Operator Productization

**状态**：implemented
**日期**：2026-10-24
**基线**：CBAP 100/100 tests
**范围**：Console lease/审批；MCP onboarding/probe；注册表热插拔；双人审批；签名；持久化历史；SLA 通知；mTLS operator；resume

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
resume 走 M3 operator 确认流程
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
[x] required_approvals=2 / operator-1 + operator-2
[x] same approver rejected
[x] approval audit
[x] onboarding scan
[x] manifest create
[x] probe / health
[x] registry enable / disable
[x] onboarding signature button
[x] persistent history (JSONL + 300/device cache)
[x] Kernel registry hotplug (explicit reload)
[x] approval SLA + local notification feed
[x] optional webhook notification
[x] Console mTLS operator identity
[x] operator resume with reason + confirm
[x] UI + API
[x] 100/100 tests
```

部署注意：

```text
[ ] onboarding registry 目录权限 0700
[ ] 生产 manifest 签名
[ ] MCP 子进程独立 UID/sandbox
[ ] TCP TLS（如启用）
```

---

## 5. 注册表启用/禁用

控制台 onboarding 列表现在有：

```text
Enable / Disable
Sign / Re-sign
Probe
```

状态写在：

```text
devices/onboarded/registry.json   0600
```

禁用后：

```text
onboard_probe 拒绝
UI 标灰
Console 调用 Kernel registry_reload
Kernel 在无 fd/lease/pending/approval 时卸载 driver
```

Kernel 启动参数：

```bash
python3 -m kernel.legacy_runtime --mcp-registry devices/onboarded
```

**边界**：热插拔是**显式 reload**，不是文件系统 watcher。
如果设备仍有 fd/lease/pending/approval，Kernel 会保留并返回 `kept`，不会强杀。

## 6. Onboarding 签名 UI

控制台按钮：

```text
Sign manifest
```

调用：

```http
POST /api/onboard/sign {"name":"..."}
```

使用：

```text
CBAP_MANIFEST_KEY / secret backend
```

签名覆盖 manifest 去掉 `signature` / `_manifest_path` 的 canonical JSON。
没有配置 key 时按钮失败，不会生成假签名。

## 7. 历史图

Console 保存**持久化 JSONL + 内存缓存**：

```text
CBAP_CONSOLE_HISTORY 默认 logs/console-history.jsonl
每设备最多缓存 300 个样本
online / lease / pending / health
hp / food（如果 facts 提供）
```

API：

```http
GET /api/history?device_id=...&limit=180
```

UI 用本地 SVG 画线，不加载第三方图表库。
重启 Console 会从 JSONL 恢复最近样本。

## 8. Approval SLA / notifications

Policy：

```json
"approvals": {"sla_ms": 30000}
```

Approval 超过 SLA：

```text
本地 console notification feed 增加 approval_sla
可选 webhook POST
CBAP_CONSOLE_WEBHOOK_URL / CBAP_CONSOLE_WEBHOOK_TOKEN
```

Webhook 带：

```text
Authorization: Bearer <token>
X-CBAP-Signature: sha256=<hmac>
```

通知是 best-effort；本地 feed 仍保留，不宣称 at-least-once。

## 9. 远程 mTLS operator

Console 支持：

```bash
python3 console/server.py   --bind-host 0.0.0.0 --port 8765   --allowed-host cbap.example:8765   --tls-cert server.crt --tls-key server.key   --tls-ca client-ca.crt --tls-require-client-cert
```

- 远程 bind 必须有 TLS；
- mTLS 客户端证书 CN 成为 operator 身份后缀；
- 仍要求 operator login token；
- 双人审批可用两个不同 CN；
- Host/Origin 必须显式加入 `--allowed-host`。

## 10. Resume

```http
POST /api/resume
{"device_id":"...","reason":"physical cause cleared","all":false}
```

Kernel op：

```json
{"op":"resume","args":{
  "device_id":"...", "reason":"...", "confirm":"RESUME"
}}
```

- operator/admin only；
- reason >= 3；
- confirm 精确 `RESUME`；
- 有 lease/pending/approval -> `E_BUSY`；
- health 非 ok -> `E_SAFETY`；
- 只清 safe，不授予 lease；
- 全局 safe 必须 `all=true`；
- audit `resume`。

---

## 11. 仍未做

```text
多操作员角色管理
持久化审批通知（SLA feed 仍是内存）
远程 operator 证书吊销/OCSP
审批 SLA 的 at-least-once 送达
```

不把“有 approval”误写成“有硬件安全认证”。
