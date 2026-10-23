# Mindcraft Mindy

Status: **active / external**

```text
upstream:  external/mindcraft
adapter:   drivers/mindcraft/adapter.mjs
device:    mc://mind/Mindy
transport: MindServer socket.io -> line JSON
control:   state / prompt / stop
```

This is not a low-level action driver. Mindcraft remains the autonomous
planner; CBAP observes state, delivers prompts, and can stop it.

The physical adapter remains in the main repository during the migration
window.
