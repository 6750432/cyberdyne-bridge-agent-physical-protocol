# Voyager CBAP peripheral

`mc://voyager/bot` wraps the Voyager Mineflayer HTTP bridge as a CBAP device.

```text
CBAP Kernel
  → McDriver (line-JSON)
  → drivers/voyager/adapter.mjs
  → Voyager bridge :3000
  → Mineflayer / Minecraft 1.19.2
```

## Supported

```text
read body
write forward   (one short forward pulse)
write exec      (explicit JS code)
write say       (chat)
estop / stop    (bridge /stop)
```

No LLM is involved in this driver. The caller supplies code/actions.

## Not supported

```text
VoyagerEnv / curriculum / skill library / critic
GPT-4 or any paid API
automatic code generation
```

## Bridge requirement

The bridge needs a `/state` endpoint; apply
`patches/voyager-state.patch` to `voyager/env/mineflayer/index.js`.
It also includes the optional `minecrafthawkeye` guard used by the spike.

## Test

```bash
# server + bridge + bot must be running
python3 tools/voyager_cbap.py
```
