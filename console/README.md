# CBAP Operator Console

Local-only web console for the CBAP Kernel.

It exists for one reason:

```text
人能看见，人能停。
```

It is a **host**, not part of the CBAP protocol. It talks to the Kernel over
the CBAP Unix socket and never opens a driver directly.

## What it shows

```text
device list / online state
current lease owner / expiry
pending writes
health
last facts
Kernel audit tail
```

## What it can do

```text
estop one device
estop all devices
```

There is intentionally **no resume endpoint**. The Kernel's estop is latched:
per-device estop requires a Kernel restart or an explicit admin resume path
(not implemented in v0). The UI labels the state `LATCHED SAFE`.

## Run

Start the Kernel first, then:

```bash
python3 console/server.py \
  --socket ./cbap.sock \
  --audit ./logs/cbap-audit.jsonl \
  --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

If the Kernel has an auth token:

```bash
python3 console/server.py --socket ./cbap.sock --token '<kernel-token>'
```

## Security posture

```text
bind:       127.0.0.1 only
Host:       validated against 127.0.0.1:<port> / localhost:<port>
Origin:     validated when present
API auth:   per-process X-CBAP-Token
CSP:        self only, frame-ancestors none
No CORS
No resume
No arbitrary command endpoint
```

The console token is embedded in the local HTML page for the same-origin UI.
It is not a substitute for Kernel authentication; use `--token` when the
Kernel requires one.

## Test

```bash
python3 -m unittest -v tests.cbap.test_console
```

## Limitations

```text
no multi-operator authentication
no TLS (localhost only)
no resume UI
no historical charts
no device-specific 3D visualization
```

The Kernel audit log is the authoritative record; the console is a view.
