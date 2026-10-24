# Security Policy / 安全策略

## Supported versions

安全修复优先覆盖：

```text
main 分支
最新 GitHub Release
```

旧版本不承诺持续安全更新。

## Reporting a vulnerability

**请不要在公开 Issue 中贴可利用细节、token、私钥、个人信息或完整攻击链。**

优先使用 GitHub 的私密漏洞报告：

```text
https://github.com/cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol/security/advisories/new
```

如果该入口不可用，请开一个**不含敏感细节**的 Issue，说明“需要私密渠道”，
维护者会提供后续联系方式。

请尽量包含：

```text
受影响版本 / commit
最小复现
影响范围
是否需要本地访问
是否涉及 host bridge / input / fs
你希望公开的时间线
```

## Scope

重点范围：

```text
CBAP Kernel 认证、租约、fencing、cancel、estop
policy / approval / audit / token
host bridge 网络绑定与 token
host://fs 路径逃逸 / symlink
host://display 截图路径
host://input 默认拒绝与 opt-in
MCP sandbox / manifest pin
TLS / mTLS 配置
```

不在范围：

```text
Minecraft 游戏本体 / 服务端漏洞
第三方上游项目本身（请报告给上游）
用户自行错误配置（例如把 host bridge 暴露公网）
社会工程 / 物理访问
```

## Safe harbor

我们支持出于善意的安全研究。请：

```text
只测试你拥有或获授权的环境
不要访问、修改或泄露他人数据
不要造成服务中断
给维护者合理修复时间
```

## 不要提交的内容

```text
真实 token / 私钥 / 云密钥
个人身份证 / 手机号 / 邮箱
他人设备截图
未脱敏日志
```

## Disclosure

维护者会在确认后尽量协调公开时间线。  
本项目是个人/社区项目，不承诺商业 SLA。

见 [`DISCLAIMER.md`](DISCLAIMER.md)。
