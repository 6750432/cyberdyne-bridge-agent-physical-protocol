# Mindcraft Mindy

Status: **active / external**

```text
upstream:  external/mindcraft
adapter:   agents/mindcraft/adapter/adapter.mjs
device:    mc://mind/Mindy
transport: MindServer socket.io -> line JSON
control:   state / prompt / stop
```

This is not a low-level action driver. Mindcraft remains the autonomous
planner; CBAP observes state, delivers prompts, and can stop it.

This adapter lives directly under `agents/mindcraft/adapter/`; there is no
`drivers/mindcraft` shim.

Local smoke: `python3 agents/mindcraft/smoke.py`
Probe: `agents/mindcraft/tools/mindcraft_cbap.py`.
