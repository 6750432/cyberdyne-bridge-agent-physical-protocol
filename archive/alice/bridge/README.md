# Alice minimal CBAP bridge

This is a **minimal add-on bridge** for Alice (Forge 1.20.1). It is not a
full CBAP driver; it exposes only server-authoritative state and one
deterministic task.

## Apply

Copy:

```text
drivers/alice/bridge/CbapBridge.java
```

to:

```text
<Alice>/src/main/java/com/dddgn/alice/bridge/CbapBridge.java
```

Build Alice normally:

```bash
./gradlew build
```

The class is registered by `@Mod.EventBusSubscriber`; no main-class edit is
required.

## Endpoints

Local-only, default `127.0.0.1:8745` (override `-Dalice.cbap.port=...`):

```text
GET  /health
GET  /state
POST /spawn   {"name":"Alice","pos":[x,y,z]}
POST /task    {"type":"walk_to","target":[x,y,z]}
POST /stop
```

`/state` returns `BotStateReport.json(bot)` — the same structured facts Alice
uses for its LLM decision layer, including task tree / last terminal / menu.

`/task` only supports `walk_to` in this minimal version; it calls
`BotManager.assignWalkTo`. No mining, containers, inventory writes, or LLM.

## Reconciliation

The caller must not trust HTTP acceptance as completion. Poll `/state` and
verify server facts:

```text
final bot.pos near target
task.current idle
task.lastTerminal terminal=SUCCESS (when available)
```

`tools/alice_bridge_probe.py` does this directly over HTTP, without GPT or any
paid API.

## Status

Source is ready for integration, but this environment has no JDK 17 / Forge
Gradle build set up yet, so the bridge has **not been compiled or run here**.
Do not claim it tested until the Forge build and a real server smoke test pass.

## Security

No auth; bind is loopback only. Do not expose this port.
