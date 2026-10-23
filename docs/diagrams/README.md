# CBAP structure diagram

Files:

- `cbap-structure.dot` — Graphviz source
- `cbap-structure.png` — rendered 180 dpi
- `cbap-structure.svg` — vector

Render:

```bash
dot -Tpng -Gdpi=180 cbap-structure.dot -o cbap-structure.png
dot -Tsvg cbap-structure.dot -o cbap-structure.svg
```

Reading:

```text
solid lines        action / control
cyan dashed        state / facts / result
gold dashed        unbuilt or partial
```

The dashed Alice path is source-only; the Forge build did not complete.
The Voyager node is the bridge, not Voyager's autonomous Python agent.
The Mindcraft node is the state/prompt/stop adapter, not a low-level action driver.

Control-plane benchmark (local UDS, fake device, one client):

```text
device_list p50 0.221 ms / p95 0.374 ms
read body   p50 0.236 ms / p95 0.522 ms
stat        p50 0.307 ms / p95 0.415 ms
process RSS ~29.7 MB including fake hand + driver + client
```

The bridge is not the end-to-end bottleneck; Minecraft actions and LLM
decisions dominate.
