# Disclaimer / 免责声明

**简体中文** | [English below](#english)

> 本文不是法律意见。若你计划商用、分发二进制、提供服务或用于受监管环境，
> 请咨询有资质的律师。

## 1. 实验性软件，按“原样”提供

Cyberdyne Bridge / CBAP 是研究性、实验性软件。  
在适用法律允许的最大范围内，作者和贡献者按 **“AS IS”** 提供本项目，
不提供任何明示或暗示的保证，包括但不限于：

```text
适销性
特定用途适用性
不侵权
无缺陷
不中断
数据不丢失
硬件不损坏
```

作者和贡献者不对因使用、无法使用、修改、分发或依赖本项目而产生的
任何直接、间接、附带、特殊、惩罚性或后果性损害承担责任。

## 2. 仅用于你有权控制的环境

你只能在你拥有或已获得明确授权的设备、账号、服务器和网络上使用本项目。

禁止：

```text
未经授权访问他人设备或账号
绕过访问控制、反作弊或安全机制
在公共 Minecraft 服务器上违反其规则
对他人实施骚扰、破坏、欺诈或攻击
将本项目用于任何违法活动
```

因违反游戏服务条款、服务器规则、账号封禁、网络服务条款或当地法律
产生的后果，由使用者自行承担。

## 3. Host / 桌面 / 输入控制风险

本项目包含宿主机测试桥和可选的桌面/鼠标/键盘设备接口。它们是
**本地测试能力**，不是生产级远程管理产品。

```text
host bridge 默认只应绑定 127.0.0.1
输入设备默认关闭
需要显式 --enable-input
X11 / portal 后端有不同隔离与同意模型
固定测试 token 不是生产密钥
```

绝对不要把 host bridge 暴露到公网，也不要在未经同意的设备上启用输入。
因配置错误、弱 token、网络暴露或误操作导致的损失由使用者承担。

## 4. AI / LLM 的不确定性

项目可以接入本地或外部 LLM。模型可能：

```text
产生幻觉
误解指令
重复动作
在异常状态下继续执行
给出看似合理但错误的计划
```

CBAP 的 lease、policy、fencing、audit、estop 和事实校验降低风险，
但**不构成安全认证**，也不能保证 AI 行为一定正确。

## 5. 第三方名称与项目

本项目不是以下机构的官方项目，也不代表其背书：

```text
Mojang Studios / Microsoft / 网易
DeepSeek
Qwen / 阿里云
Mindcraft
Voyager / MineDojo
mineflayer-mcp
PrismarineJS
```

Minecraft 是 Mojang Studios 的商标。  
第三方组件和补丁的许可见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 6. 无安全认证 / 无合规承诺

本项目没有经过：

```text
形式化验证
第三方安全认证
医疗/工业/汽车/航空等安全认证
隐私合规审计
出口管制审查
```

不要把它直接用于人身安全、医疗、工业控制、关键基础设施或高价值资产。

## 7. AI 协作披露

本项目有大量 AI 辅助生成/修改的代码、测试和文档。  
人类维护者负责架构、边界和最终验收，但这不构成对正确性或安全性的担保。

## 8. 责任限制

在适用法律允许的最大范围内，作者、贡献者和组织不对任何索赔、损害、
损失或责任承担责任，无论是合同、侵权、严格责任还是其他依据，也不论
是否已被告知可能发生此类损害。

## 9. 详细条款

本文件是总览；更细的条款见：

```text
LEGAL/TERMS.md                 使用条款
LEGAL/ACCEPTABLE-USE.md        可接受使用政策
LEGAL/PRIVACY.md               隐私
LEGAL/ABUSE.md                 滥用报告
LEGAL/INCIDENT-RESPONSE.md     事件响应
LEGAL/RISK-REGISTER.md         风险登记
LEGAL/COUNSEL-CHECKLIST.md     律师审阅清单
```

## 10. 不是法律意见

本文只做风险说明，不构成法律建议。  
如果你需要商用或对外提供服务，请自行完成许可证、隐私、出口、税务和
当地法律审查。

---

<a id="english"></a>

## English (summary)

Cyberdyne Bridge / CBAP is experimental research software provided **AS IS**,
without warranties of merchantability, fitness, non-infringement, or
uninterrupted operation. To the maximum extent permitted by law, the authors
and contributors are not liable for any direct, indirect, incidental, special,
consequential, or punitive damages arising from use of the project.

Use it only on devices, accounts, servers, and networks you own or are
explicitly authorized to control. Do not use it for unauthorized access,
anti-cheat evasion, public-server abuse, harassment, or illegal activity.
Host/desktop/input bridges are local test facilities, not production remote
administration. Input is disabled by default and must never be exposed to the
public internet.

LLM behavior is probabilistic and may be wrong. CBAP leases, policy, fencing,
audit, estop, and fact checks reduce risk but are not a security certification.
Minecraft is a trademark of Mojang Studios. This project is not affiliated with
or endorsed by Mojang, Microsoft, NetEase, DeepSeek, Qwen, Mindcraft, Voyager,
mineflayer-mcp, or PrismarineJS.

This is not legal advice.
