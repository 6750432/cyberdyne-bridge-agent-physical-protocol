# Cyberdyne MC Agent

Status: **legacy brain, migrated entrypoint / ours**

This is our original MC Agent:

```text
brain/bridge.py          brain
hand/node/server.js      hand
plugins/                 hot-plug carriages
```

The brain/hand direct UDS path is **legacy** and does not go through CBAP.
The hand can also be wrapped by `McDriver` as the CBAP device
`mc://bot/DeepSeek`.

M4 migration wrapper:

```text
agents/cyberdyne/brain/bridge_cbap.py
agents/cyberdyne/tools/启动大脑-cbap.sh
```

It keeps the legacy brain but replaces `接线口` with `CBAPHandAdapter`.
The original direct hand path remains frozen and is not the recommended runtime.

M4 removed the root compatibility shims. Use the physical paths or the
CBAP wrapper:

```text
agents/cyberdyne/brain/bridge_cbap.py
agents/cyberdyne/tools/启动大脑.sh
agents/cyberdyne/tools/启动手.sh
```

The old direct brain/hand path is frozen; it is not a second controller.

Local smoke: `python3 agents/cyberdyne/smoke.py`
Agent tools: `agents/cyberdyne/tools/`; root launch shims were removed in M4.
