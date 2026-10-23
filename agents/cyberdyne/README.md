# Cyberdyne MC Agent

Status: **active / ours**

This is our original MC Agent:

```text
bridge.py          brain
node/server.js     hand
外挂/              hot-plug carriages
```

The brain/hand direct UDS path is **legacy** and does not go through CBAP.
The hand can also be wrapped by `McDriver` as the CBAP device
`mc://bot/DeepSeek`.

The physical files are still at the repository root during the migration
window. They will move under `agents/cyberdyne/` only after the driver plugin
boundary and compatibility shims are in place.
