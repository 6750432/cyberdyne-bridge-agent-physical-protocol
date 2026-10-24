# M2 · Protocol 1.1

**状态**：first slice implemented  
**日期**：2026-10-24  
**基线**：CBAP 96/96 tests  
**原则**：只实现有明确消费方的协议能力；不为了“草案完整”加字段。

---

## 1. 实现范围

### 1.1 Feature negotiation

```json
{"type":"hello","features":["poll_filter"]}
```

Kernel 返回实际授予：

```json
{"type":"welcome","features":["poll_filter"]}
```

- 未知 feature 忽略；
- 未授予 `poll_filter` 时，带过滤参数的 `poll` 返回 `E_NOTSUP`；
- 当前只定义 `poll_filter`。

### 1.2 `poll` 过滤

```json
{"op":"poll","args":{
  "timeout_ms":1000,
  "fds":["fd-1"],
  "events":["chat"]
}}
```

行为：

```text
fds     只返回这些 fd 的事件
events  只返回这些 kind
未知 fd -> E_NOENT
不匹配事件保留在队列
超时无事件 -> ok:true + []
```

事件现在带：

```json
{"kind":"chat","fd":"fd-1","fds":["fd-1"],"seq":4,"payload":{}}
```

### 1.3 可选 TCP

```python
KernelServer(..., tcp_host="127.0.0.1", tcp_port=8766)
```

```python
CBAPClient(tcp_host="127.0.0.1", tcp_port=8766)
```

- token 仍然必需；
- TCP 没有 `SO_PEERCRED`，不能依赖 uid 白名单；
- 不配 TLS 时 token 是明文，只适合本机/受控网络；
- 监听地址默认 `127.0.0.1`。

CLI：

```bash
python3 -m kernel.legacy_runtime \
  --tcp-host 127.0.0.1 --tcp-port 8766
```

### 1.4 TLS / mTLS

```python
KernelServer(
  ..., tcp_host="127.0.0.1", tcp_port=8766,
  tls_cert="server.crt", tls_key="server.key",
  tls_ca="client-ca.crt", tls_require_client_cert=True,
)
```

```python
ctx = ssl.create_default_context(cafile="server-ca.crt")
ctx.load_cert_chain("client.crt", "client.key")
CBAPClient(tcp_host="127.0.0.1", tcp_port=8766, tls_context=ctx)
```

- TLS 最低 1.2；
- `tls_require_client_cert=True` 必须有 `tls_ca`；
- 没有客户端证书 -> handshake/hello 失败；
- 仍然是 token + TLS 两层，不替代 token。

测试：

```text
test_tcp_token_round_trip
test_mtls_round_trip_and_missing_client_cert
```

---

## 2. 没有实现

### `progress`

没有真实驱动能提供可信进度。  
当前 `progress` 仍是 reserved，不发假进度。

需要时再定义：

```text
driver.on_progress
progress 0..1 + detail
按 request id 关联
限流
```

### CBOR

当前只支持 JSON。  
CBOR 需要真实高频数据面，否则只是增加攻击面和依赖。

### 独立 CBAP-D 进程

仍是 planned。  
当前 driver 是进程内对象；MCP 是子进程，但不是 CBAP-D 独立进程。

---

## 3. 安全边界

TCP 增加的是**网络攻击面**：

```text
token 泄露
重放
中间人（无 TLS）
客户端证书管理
监听地址误配
```

所以：

```text
默认不启用 TCP
默认只 bind 127.0.0.1
不配 TLS 不应用于跨机
mTLS 不等于硬件安全
```

---

## 4. 验收

```text
[x] feature negotiation tested
[x] poll filters tested
[x] unknown fd -> E_NOENT
[x] unnegotiated filter -> E_NOTSUP
[x] TCP token round trip
[x] TLS/mTLS round trip
[x] missing client cert rejected
[x] 96/96 tests
```

已完成软件项；部署项：

```text
[ ] 生产 TCP 必须配 TLS
[ ] 远程部署必须有客户端证书/网络 ACL
```

---

## 5. 不在 M2 内

```text
CBOR
progress
独立 CBAP-D 进程
物理安全
TPM/HSM
形式化验证
```
