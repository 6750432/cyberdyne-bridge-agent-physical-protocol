# Legacy inventory

| Item | Path | Role |
|---|---|---|
| brain | `agents/cyberdyne/brain/bridge.py` | reflex/task/plugin brain |
| hand | `agents/cyberdyne/hand/node/server.js` | mineflayer hand |
| plugins | `agents/cyberdyne/plugins/` | hot-plug carriages |
| config | `agents/cyberdyne/config.json` | legacy settings |
| shim | `bridge.py` | root compatibility symlink |
| shim | `node` | root compatibility symlink |
| shim | `外挂` | root compatibility symlink |
| shim | `config.json` | root compatibility symlink |
| CBAP wrapper | `agents/cyberdyne/brain/bridge_cbap.py` | M4 migration path |
| adapter | `kernel/legacy_runtime/brain_adapter.py` | 接线口 -> CBAP-U |

The old direct path and the Kernel must not connect to the same hand at the
same time.
