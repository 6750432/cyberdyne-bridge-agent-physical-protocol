# body/ — 自研 Mineflayer Body

**状态：** v0 skeleton（API 已冻结，真实 Mineflayer hand 尚未接入）  
**目标 MC：** 1.21.1  
**SDK：** `sdk/python/mc_body_client.py`  
**API：** [`../docs/MC-BODY-API.md`](../docs/MC-BODY-API.md)  
**ADR：** [`../docs/MC-BODY-ADR.md`](../docs/MC-BODY-ADR.md)

```text
body/
  README.md
  fake_body.py        protocol-compatible fake for SDK tests
  src/                 real Mineflayer hand (next)
  test/                node/body tests (next)
```

## 边界

```text
Body 不知道 CBAP
Body 不知道 LLM
Body 只做 Minecraft 身体
```

## 状态

```text
[x] API v0
[x] Python SDK
[x] fake body + SDK tests
[ ] 真实 Mineflayer hand
[ ] 1.21.1 本地服务器 baseline
[ ] goto / collect / craft
[ ] cancel / batch
[ ] benchmark
```

## 下一刀

```text
1. 安装 Node 20+
2. 新建 src/hand.js + src/server.js
3. 只接 mineflayer + 最小动作
4. 用本地 1.21.1 服务器跑 goto
5. 记录 ack/state/cancel 延迟
```
