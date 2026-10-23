# Cyberdyne MC Agent

Status: **active / ours**

This is our original MC Agent:

```text
brain/bridge.py          brain
hand/node/server.js      hand
plugins/                 hot-plug carriages
```

The brain/hand direct UDS path is **legacy** and does not go through CBAP.
The hand can also be wrapped by `McDriver` as the CBAP device
`mc://bot/DeepSeek`.

Compatibility shims remain at the repository root:

```text
bridge.py  -> agents/cyberdyne/brain/bridge.py
node       -> agents/cyberdyne/hand/node
外挂        -> agents/cyberdyne/plugins
config.json -> agents/cyberdyne/config.json
```

This keeps the existing service and launch scripts working.
