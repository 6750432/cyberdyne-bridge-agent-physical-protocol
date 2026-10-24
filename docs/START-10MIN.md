# 10 分钟跑通 CBAP

**实测范围：** 干净 clone → 118/118 conformance → host allowlist 文件写入  
**实测主机：** Linux / Python 3.13 / 无 Minecraft / 无 Node / 无 LLM / 无 root  
**实测耗时：** clone 7s + conformance 118s + host demo <2s  
**10 分钟预算：** 约 2.5 分钟执行，其余时间用来看架构和安全边界。

> 这条 10 分钟路径只验证 **协议 + Kernel + host allowlist**。  
> 完整的 CBAP OS / QEMU / ISO / 桌面虚拟机是另一条路径，通常 15–30 分钟。

---

## 0. 前置条件

```text
Linux 或 macOS
Python 3.10+
git
```

不需要：

```text
Minecraft 服务端
Node.js
LLM / API key
Docker
root
公网
```

## 1. 克隆（约 10 秒）

```bash
git clone --depth 1 \
  https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol.git
cd cyberdyne-bridge-agent-physical-protocol
```

## 2. 跑 118 条 conformance（约 2 分钟）

```bash
python3 tools/cbap_conformance.py --target fake
```

期望结尾：

```text
Ran 118 tests
OK
CBAP v1 conformance · target=fake · cases=118
```

这一步不需要 Minecraft，也不需要任何外部依赖。  
它覆盖 Kernel、租约、fencing、cancel、estop、policy、MCP、host device 等路径。

## 3. 跑 host allowlist demo（约 2 秒）

```bash
./tools/quickstart_host_demo.sh
```

它会：

```text
创建 /tmp/cbap-10min.*
生成随机 token（不打印）
启动本地 host bridge（只使用 Unix socket）
打开 host://fs
lease
写入 hello.txt
stat + sha256
读取文件内容
关闭并清理
```

期望输出：

```text
devices: ['host://desktop', 'host://fs', 'host://display']
write: /tmp/cbap-10min.*/root/hello.txt 30 bytes
sha256: ...
stat: True
hello from the 10-minute path
done: protocol + host allowlist path verified.
```

这一步验证的是：

```text
Agent -> CBAP-U -> Kernel -> host://fs -> 文件
```

不是 shell，不是任意路径，不是公网。

## 4. 用 5 分钟看边界（可选但建议）

```text
README.md                         项目定位
docs/DEVICE-PARITY.md             device contract / policy / quotas / trust / safe_state
docs/CBAP-OS-Host-Bridge.md       host bridge / 输入默认关闭 / token
LEGAL/ACCEPTABLE-USE.md           允许/禁止用途
SECURITY.md                       漏洞报告
```

## 5. 如果想看完整 CBAP OS（另一条路径）

这部分不包含在 10 分钟内：

```text
构建 / 启动 QEMU CBAP OS ISO
GRUB 版本选择
Control Center
宿主机 host bridge + token
```

入口：

```text
docs/CBAP-OS-Host-Bridge.md
https://github.com/6750432/dsh-os-build
```

## 常见失败

### `ModuleNotFoundError`

请确认在仓库根目录执行，而不是在 `tools/` 里：

```bash
cd cyberdyne-bridge-agent-physical-protocol
python3 tools/cbap_conformance.py --target fake
```

### `Address already in use`

10 分钟脚本默认使用 Unix socket + `--no-tcp`，不会占用 8765/18765。  
如果仍冲突，检查是否已有旧的 host bridge：

```bash
pgrep -af cbap_host_bridge
```

### 权限不足

10 分钟脚本不需要 root；不要在 `sudo` 下运行。

## 验收标准

```text
[ ] clean clone 成功
[ ] conformance 118/118
[ ] host://fs 写入成功
[ ] sha256 返回
[ ] stat 返回 true
[ ] 没有使用 TCP / 公网 / Minecraft / LLM / root
```

完成以上，就算跑通了 **CBAP 协议主路径**。
