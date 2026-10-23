# Mindcraft CBAP peripheral

## What this is

This is a **state/prompt/stop** adapter for a real autonomous Mindcraft agent.
It is not a low-level action injector.

```text
Mindcraft / MindServer
   ↑ socket.io: state-update / send-message / stop-agent
adapter.mjs
   ↑ line-JSON
McDriver + CBAP Kernel
   ↑
CBAP client
```

## Files

```text
adapter.mjs        MindServer socket.io -> line-JSON
device.json        CBAP device mc://mind/Mindy
mapping.json       prompt + stop
patches/           headless lazy-load patches for external Mindcraft
```

## Run

Mindcraft must be running with a profile named `Mindy` and MindServer on 8080.
The local model can use the `lmstudio` API profile pointing at llama-server:

```json
{
  "name": "Mindy",
  "model": {"api": "lmstudio", "model": "qwen3", "url": "http://127.0.0.1:8099/v1"},
  "embedding": {"api": "lmstudio", "model": "qwen3", "url": "http://127.0.0.1:8099/v1"}
}
```

Start Mindcraft with `MINECRAFT_PORT=25565 MINDSERVER_PORT=8080` and
`SETTINGS_JSON` for `auto_open_ui=false`, `port=25565`, `render_bot_view=false`.

Start adapter:

```bash
node drivers/mindcraft/adapter.mjs \
  --port 8080 --agent Mindy \
  --socket /tmp/mindcraft-cbap.sock \
  --moduleRoot /home/bzys17mintstart/external/mindcraft/package.json
```

Probe:

```bash
python3 tools/mindcraft_cbap.py --target 22,67,-54
```

## Semantics

- `read body` returns Mindcraft's live position/health/hunger/activity.
- `write prompt` delivers a message to Mindcraft's autonomous planner.
  `ok:true` means **delivered**, not action complete.
- `write stop` / `estop` stops the agent process.
- Adapter exits after estop; restart adapter/Mindcraft to bring it back.

## Headless note

Mindcraft imports `prismarine-viewer` and `node-canvas-webgl` at module load.
For a headless install without native canvas/gl, apply
`patches/mindcraft-headless.patch` and install dependencies with
`npm install --ignore-scripts`. The patch only lazy-loads those UI/vision
modules; it does not change Mindcraft planning or actions.
