# Voyager bridge

Status: **active / external, bridge only**

```text
upstream:  external/Voyager
adapter:   drivers/voyager/adapter.mjs
device:    mc://voyager/bot
transport: HTTP bridge -> line JSON
control:   state / exec / forward / say / stop
```

This is **not** Voyager's autonomous Python agent. It is the Mineflayer bridge
only. The Voyager planner, curriculum, skill library, and critic are not wired.

The state endpoint patch is kept at
`drivers/voyager/patches/voyager-state.patch`.
