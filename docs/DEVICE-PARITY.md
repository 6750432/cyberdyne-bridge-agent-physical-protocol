# CBAP Device Parity P0–P6

**目标**：让不同设备在 Kernel 眼里拥有同一套**身份、生命周期、租约、审计、策略、事实和急停**。

> 同权不同能：接口权利相同，能力不强行相同。

当前状态：**P0–P6 已落地**，主仓 **114/114**。

---

## P0 · Device Contract v1

所有设备注册时归一化为：

```json
{
  "contract": "cbap-device-v1",
  "device_id": "host://fs",
  "class": "filesystem",
  "version": "1.0",
  "actions": {
    "write_file": {"args": {"path": "relative-path"}, "danger": "normal"}
  },
  "capabilities": ["read", "write", "lease", "estop"],
  "trust": {"source": "host-filesystem", "independent": false,
            "attestation": "local-hash", "level": 1},
  "isolation": {"process": "host-bridge", "uid": 1000,
                "sandbox": "none", "network": "local"},
  "resources": {"max_inflight": 4, "rate_hz": 10,
                "max_bytes": 65536, "max_sessions": 4},
  "safety": {"estop": true, "watchdog_ms": 10000,
             "safe_state": "read-only"}
}
```

Kernel 注册时校验：

```text
device_id 唯一且带 scheme
class 合法
actions typed
capabilities 合法
trust / isolation / resources / safety 必须存在
safety.estop 和 watchdog_ms 必须存在
```

真实驱动声明 `legacy=false`。旧测试 fixture 可以被归一化，但：

```bash
--strict-contracts
```

会拒绝 legacy 描述。

代码：

```text
kernel/legacy_runtime/device_contract.py
kernel/legacy_runtime/server.py
drivers/mc/driver.py
drivers/mcp_device/driver.py
drivers/host_desktop/driver.py
drivers/host_desktop/devices.py
```

---

## P1 · 默认最小权限

生产默认：

```json
{
  "default": {"devices": [], "capabilities": ["read"]}
}
```

- 没有显式 grant，不能打开任何设备。
- `--policy` 可以按 agent 授权设备与能力。
- `host://input/*` 的敏感动作还可以要求审批。

示例：

```json
{
  "default": {
    "devices": ["host://fs", "host://display"],
    "capabilities": ["read", "write", "lease"]
  },
  "agents": {
    "cbap-os-vm": {
      "devices": ["host://fs", "host://display"],
      "capabilities": ["read", "write", "lease"]
    }
  },
  "approvals": {
    "devices": ["host://input/*"],
    "ops": ["click", "type", "key"],
    "required_approvals": 1
  }
}
```

测试 harness 使用：

```text
CBAP_TEST_MODE=1
```

它只影响测试进程；生产默认仍是 deny。

Host bridge 自己显式构造 policy，不再吃全局通配：

```text
host://desktop  host://fs  host://display
```

只有 `--enable-input` 才加入输入设备。

---

## P2 · 隔离与配额

### 每设备配额

Kernel 现在执行 contract 中的：

```text
max_inflight   同一设备同时 pending/approval 上限
rate_hz        每设备每秒 write 上限
max_bytes      单次 frame 上限
max_sessions   同一设备同时打开 fd 上限
```

超限返回：

```text
E_BUSY / E_INVAL
```

### 隔离声明

每个设备必须声明：

```text
process
uid
sandbox   none / process / uid / bwrap / nsjail / portal
network
```

已存在的实际隔离：

```text
MCP child     bwrap/nsjail/uid/rlimit（按 manifest）
MC hand      独立 node 进程
host bridge  独立宿主进程
portal input xdg-desktop-portal RemoteDesktop
```

输入设备如果使用未隔离的 X11 后端，可以被 Kernel 拒绝：

```bash
--require-isolated-input
```

此开关要求 `--input-backend portal` 或其他 isolated backend。

---

## P3 · 事实与信任标签

每个结果都会带：

```json
{
  "source": "host-filesystem",
  "independent": false,
  "attestation": "local-hash",
  "trust_level": 1,
  "observed_at": 179...,
  "trust": {"source": "host-filesystem", "independent": false, ...}
}
```

`require_independent_facts` 使用这些标签；host 文件/截图不会被冒充成独立硬件事实。

当前事实来源：

```text
mc://         Minecraft server facts       independent=true
mcp://        MCP facts / external probe   manifest-dependent
host://fs     local file stat/hash         independent=false
host://display local screenshot hash       independent=false
host://input   "sent" only, not "effective" independent=false
```

---

## P4 · 安全状态与急停证据

每个设备有：

```text
safe_state    off / idle / input-disabled / read-only / stopped / unknown
estop         必须实现
watchdog_ms   必须声明
```

`estop` 返回每设备证据：

```json
{
  "devices": [
    {"device_id": "host://fs", "driver_ok": true,
     "safe_state": "read-only", "declared_safe_state": "read-only"}
  ]
}
```

全局 estop、单设备 estop、watchdog 都走同一套审计。

注意：软件 `safe_state` 不等于物理断电；硬件断电仍需要设备/BMS/继电器证据。

---

## P5 · Native Wayland 输入

新增 consent-first 后端：

```text
xdg-desktop-portal RemoteDesktop
```

启动：

```bash
python3 tools/cbap_host_bridge.py \
  --root ~/Desktop/CBAP-Host-Test \
  --tcp-port 18765 \
  --enable-input \
  --input-backend portal \
  --require-isolated-input
```

特点：

```text
不使用 root
不使用 uinput
由 compositor 弹用户授权框
只支持显式 key chord（不是任意文本注入）
支持 pointer relative / button / axis
portal 不可用或用户取消 -> E_SAFETY
```

X11/XWayland 后端仍保留，但它是默认未隔离的兼容路径；不要把它说成 native Wayland。

---

## P6 · 每设备 conformance

主仓：

```bash
python3 tools/cbap_conformance.py --target fake
```

结果：

```text
114 tests OK
```

新增测试：

```text
tests/cbap/test_device_contract.py
tests/cbap/test_host_device_conformance.py
```

覆盖：

```text
contract shape / welcome
default-deny policy
max_bytes / max_sessions / rate
trust facts / independent requirement
per-device estop safe_state
strict contract / isolated input gate
host fs actions / escape rejection
display + input default deny
portal backend declaration/probe
```

现有 MC/MCP/Kernel 测试继续覆盖：

```text
lease / fencing / cancel / audit / approval / TLS / mTLS / resume
```

---

## 设备矩阵

| device | class | actions | trust | isolation | default |
|---|---|---|---|---|---|
| `mc://bot/DeepSeek` | actuator | move/dig/... | server, independent | hand process | allowed only by policy |
| `mcp://...` | actuator | manifest tools | manifest facts | sandbox/rlimit | allowed only by policy |
| `host://desktop` | filesystem | write/list/stat/ping | local, false | host process | policy grant |
| `host://fs` | filesystem | write/list/stat/ping | local, false | host process | policy grant |
| `host://display` | display | screenshot/stat | local hash, false | host process | policy grant |
| `host://input/mouse` | input | X11 or portal actions | sent-only, false | none/portal | disabled + approval |
| `host://input/keyboard` | input | X11 or portal key | sent-only, false | none/portal | disabled + approval |

---

## 仍然不是“完全平权”的地方

```text
host bridge 进程本身仍是宿主用户进程；没有对 fs/display 做 bwrap
X11 input 仍是未隔离兼容后端
portal 的实际 Start 需要用户点授权框；CI 只测 availability/default-deny
host://fs 仍是 allowlist，不是宿主根目录
没有 TPM/远程硬件证明
safe_state 不是物理断电证明
```

这些是剩余边界，不应伪装成已完成。

---

## 命令

```bash
# 全套 conformance
python3 tools/cbap_conformance.py --target fake

# host device safety
python3 tools/test_host_desktop.py
python3 tools/test_host_devices.py

# 严格 host bridge
python3 tools/cbap_host_bridge.py \
  --root ~/Desktop/CBAP-Host-Test \
  --tcp-port 18765 \
  --strict-contracts \
  --require-isolated-input \
  --enable-input \
  --input-backend portal
```
