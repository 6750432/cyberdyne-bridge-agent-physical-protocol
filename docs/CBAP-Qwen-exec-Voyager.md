# Qwen 4B 生成 JS 并通过 Voyager exec 执行

日期：2026-10-23  
目标：让本地 Qwen3-4B **自己生成一小段 JS**，通过 CBAP 的 `exec` 动作交给 Voyager bridge 执行。  
不使用 GPT-4、不使用任何付费 API。

## 结果

```text
voyager_qwen_exec.py: ok=true
attempts: 1
```

Qwen 生成并执行的代码：

```javascript
bot.setControlState('jump', true);
bot.setControlState('jump', false);
bot.chat('qwen exec works');
```

CBAP exec 返回：

```json
{"onChat": ["qwen exec works"]}
```

Minecraft 服务端日志：

```text
[Not Secure] <bot> qwen exec works
```

完整结果：

- [`voyager-qwen-exec.json`](voyager-qwen-exec.json)

## 链路

```text
Qwen3-4B :8099
  → tools/voyager_qwen_exec.py
  → CBAP exec
  → McDriver
  → drivers/voyager/adapter.mjs
  → Voyager bridge /step
  → Mineflayer
  → Minecraft 1.19.2
```

## 过程中的真实限制

第一版让 Qwen 用：

```javascript
await bot.waitForTicks(10);
```

在 bridge 里触发了：

```text
Timeout waiting for 10 ticks
```

所以这个 spike 改成 **不依赖 waitForTicks** 的小段 JS，并要求 Qwen 只做：

```text
jump state toggle + chat
```

这也说明 4B 生成的代码需要 supervisor 做校验，不能盲执行。

## 这证明了什么

```text
本地 4B 能生成小段 JS
CBAP exec 能把代码送到 Voyager bridge
bridge 能执行
onChat observation 能回到 CBAP
没有 GPT-4 / 付费 API
```

## 边界

```text
jump 只是 setControlState(true/false)，没有验证真正离地
exec 是任意 JS，当前仅适合本地可信环境
不是 VoyagerEnv / curriculum / skill library
不是 4B 能写复杂 Voyager skill
```

## 当前状态

测试后：

```text
Qwen model        stopped
Minecraft 1.19.2  stopped
Voyager bridge    stopped
CBAP adapter      stopped
ports 3000/25565/8099 closed
memory            ~4.5 GiB used / ~10 GiB available
```

## 复现

```bash
# start boundary-model, MC 1.19.2, bridge, bot, adapter
# then:
.python310/bin/python3.10 tools/voyager_qwen_exec.py
```
