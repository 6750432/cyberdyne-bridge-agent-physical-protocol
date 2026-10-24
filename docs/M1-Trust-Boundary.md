# M1 · Trust Boundary Closed

**状态**：software controls implemented；物理/基础设施项明确标注  
**日期**：2026-10-24  
**基线**：CBAP 98/98 tests

M1 的目标不是增加协议功能，而是让第三方 MCP 设备、审计和恢复路径的信任边界可配置、可验证、失败关闭。

---

## 1. MCP 子进程隔离

### 1.1 独立 UID/GID

```json
"transport": {
  "run_as_uid": 65534,
  "run_as_gid": 65534,
  "inherit_env": false,
  "env_allowlist": ["PATH", "HOME", "LANG"]
}
```

- 只有 root 能使用 `run_as_uid/run_as_gid`；非 root 请求会在驱动构造时 `E_SAFETY`。
- 子进程在 `preexec` 中执行 `setgid` / `setgroups` / `setuid`。
- 子进程默认不继承完整环境，Kernel token 不应出现在 env。
- 独立 UID 仍不是完整容器；生产建议再加 bwrap/nsjail 或 OCI。

### 1.2 bwrap / nsjail

```json
"transport": {
  "sandbox": {"type": "bwrap", "writable_cwd": false}
}
```

- 请求 sandbox 但二进制不存在 -> 拒绝启动。
- 这是 OS 隔离，不是内核/hypervisor 逃逸防护。

### 1.3 验收

```text
test_child_env_does_not_inherit_kernel_secret
test_run_as_uid_requires_root
test_sandbox_wrapper_is_opt_in_and_fails_closed
```

真实非 root 环境无法测试 setuid 生效；该项需要 root/容器 CI。

---

## 2. 远程审计锚点

### 2.1 配置

```bash
export CBAP_AUDIT_REMOTE_URL='https://audit.example/cbap'
export CBAP_AUDIT_REMOTE_TOKEN='...'
export CBAP_AUDIT_REQUIRE_ACK=1
```

远程 sink 必须对每批 NDJSON 返回：

```json
{"seq": 12, "hash": "<last-row-hash>"}
```

### 2.2 本地

```text
<audit>.remote-ack   0600
```

- worker 收到 ack 后原子写入；
- `require_remote_ack=1` 时，`AuditChain.verify()` 要求 ack 的 `seq/hash` 与本地链尾一致；
- ack 缺失/不一致 -> 验证失败；
- remote 不可达 -> 失败计数，不假装成功。

### 2.3 验收

```text
test_audit_remote_mirror_receives_signed_rows
test_audit_truncation_is_detected
```

真实生产还需要：

```text
remote 端持久化
remote 端独立信任域
网络重试/告警
```

---

## 3. Manifest / tool pin

### 3.1 签名

```bash
export CBAP_MANIFEST_KEY='...'
export CBAP_REQUIRE_SIGNED_MANIFEST=1
python3 tools/sign_mcp_manifest.py device.json --write
```

签名覆盖除 `signature` / `_manifest_path` 外的完整 manifest。

### 3.2 工具 pin

- 未提供 `pin_tools` 时，首次连接写 `<manifest>.pins.json`（TOFU），后续必须匹配；
- 提供 `pin_tools` 时，以 manifest 为准；
- tool 定义或 instructions 变化 -> 拒绝连接。

### 3.3 Estop 证据

```json
"estop": {
  "tool": "turn_off",
  "expect": {"on": false}
}
```

没有 `expect`/`verify` 的 `estop` 不再声明为 `safety.estop=true`，Kernel 会拒绝注册。

### 3.4 验收

```text
test_unsigned_manifest_can_be_rejected
test_tool_definition_pin_rejects_drift
test_estop_is_verified_by_facts
```

---

## 4. 恢复策略

M1 选择**显式不可恢复**：

```text
estop 锁存
resume 固定 E_PERM
恢复 = 重新 open / 重启 Kernel
控制台没有 resume 按钮
```

理由：

```text
没有双人审批、没有硬件确认前，
一个软件 resume 按钮会把急停变成可被误触的开关。
```

如果后续实现 resume，必须：

```text
operator token
+ reason
+ 二次确认
+ audit
+ 可选的第二人审批
+ 只恢复指定设备
```

---

## 5. M1 退出条件

```text
[x] MCP 子进程独立 UID/sandbox 代码路径
[x] 子进程 token 不可见（默认 env 策略）
[x] manifest 签名可强制（生产 env）
[x] tool pin 首次后强制
[x] estop 必须有 safe_state 证据
[x] remote audit ack 可选并可验证
[x] 删除审计尾部会被检出
[x] resume 明确不可用
[x] 98/98 tests 全绿

部署项（必须由环境打开）：
[ ] 生产使用独立 UID 或 sandbox
[ ] 生产设置 CBAP_REQUIRE_SIGNED_MANIFEST=1
[ ] 生产设置 CBAP_AUDIT_REQUIRE_ACK=1
```

软件项已完成；标记 `[ ]` 的是**部署时必须打开**的配置，不是默认全开。

---

## 6. 仍未关闭

```text
root / 同 uid 攻击
恶意 MCP server 伪造 facts
硬件安全回路
TPM/HSM
mTLS 远程 transport
正式渗透测试
```

M1 只关闭“软件可配置的信任边界”，不等于物理安全认证。
