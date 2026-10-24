# Releases / 发行版

CBAP 目前是**源码发行版**，没有预编译服务端/客户端二进制。  
每个 release 都是可审计的 Git 快照；源码归档由 GitHub 自动生成。

| 版本 | 主题 | Git 快照 | 关键内容 |
|---|---|---|---|
| **v1.5.0** | CBAP OS & Host Bridge | `v1.5.0` | CBAP OS UI、GRUB 多版本、host://desktop allowlist、VM→host CBAP 实测、101/101 |
| **v1.4.0** | Legacy Boundary | `c6022e2` | M4、root shim 移除、CBAP brain wrapper、101/101 tests |
| **v1.3.0** | Operator Infrastructure | `0b7cbe7` | Kernel hotplug、持久化历史、SLA、Console mTLS、resume、100/100 |
| **v1.2.0** | Operator Productization | `5728973` | lease/approval、MCP onboarding、registry、dual approval、98/98 |
| **v1.1.0** | Protocol 1.1 | `05d18d8` | poll filter、TCP/TLS、mTLS、96/96 |
| **v1.0.0** | Security Baseline | `3053656` | CBAP Kernel、13 项加固、console、MCP device driver |

## 版本边界

```text
v1.0.0  控制面 + 安全底线
v1.1.0  特性协商 / poll filter / TCP + TLS
v1.2.0  operator console / 审批 / MCP onboarding
v1.3.0  热插拔 / 历史 / SLA / mTLS / resume
v1.4.0  legacy 入口归档 / 默认 CBAP wrapper
v1.5.0  CBAP OS / 版本菜单 / host bridge / allowlist 实测
```

“CBAP v1” 是协议版本；`v1.x` 是仓库源码发行版。  
不要把 `v1.4.0` 误读成 CBAP 协议 1.4。

## 下载

GitHub Release 页面提供：

```text
Source code (zip)
Source code (tar.gz)
```

v1.5.0 / v1.4.0 同时附带：

```text
docs/CBAP-参数手册.pdf
```

## 兼容性

```text
CBAP wire: 1.0
Python: 3.10+
Transport: Unix socket；可选 TCP/TLS/mTLS
MCP: stdio JSON-RPC
```

## 证据

每个版本的主测试命令：

```bash
python3 tools/cbap_conformance.py --target fake
```

当前主分支：

```text
101/101
```

历史版本的测试数量以该 tag 下的 README / conformance 记录为准。
