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
current lease owner / expiry / fencing token
pending writes
health
last facts
Kernel audit tail
pending high-risk approvals
onboarded MCP manifests / registry enable/disable
probe / signature / pin status
in-memory history chart
```

## What it can do

```text
estop one device
estop all devices
release a lease (admin)
approve / deny a high-risk write (admin)
dual approval with a second operator token
release a lease (admin)
scan MCP tools, create an onboarding manifest
sign an onboarding manifest (CBAP_MANIFEST_KEY)
enable / disable an onboarding registry entry
probe an onboarded MCP device
history chart
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

The console prints an **operator token** at startup. Enter it in the login
form. The token is not embedded in the HTML page.

To pin it yourself:

```bash
export CBAP_CONSOLE_OPERATOR_TOKEN='<operator-token>'
python3 console/server.py --socket ./cbap.sock
```

If the Kernel has an explicit agent token:

```bash
python3 console/server.py --socket ./cbap.sock --token '<kernel-token>'
```

The operator token is separate from the Kernel agent token. The console reads
`<socket>.operator` (mode 0600), which the Kernel creates.

For dual approval:

```bash
export CBAP_SECOND_OPERATOR_TOKEN='<second-operator-token>'
python3 console/server.py --socket ./cbap.sock
```

A high-risk write with `approvals.required_approvals=2` needs one approval
from each operator session.

## Security posture

```text
bind:       127.0.0.1 only
Host:       validated against 127.0.0.1:<port> / localhost:<port>
Origin:     validated when present
API auth:   HttpOnly SameSite=Strict operator session cookie
Login:      POST /api/login with the printed operator token
CSP:        self only, frame-ancestors none
No CORS
No resume
MCP onboarding scan starts the operator-supplied argv (local, operator-only)
```

The page contains no token. Login attempts are rate-limited. The console is
still a local-only host; a hostile process running as the same OS user can
read the process environment or files. MCP onboarding is deliberately a
powerful operator action: it can start a local stdio server.

## Test

```bash
python3 -m unittest -v tests.cbap.test_console
```

## Limitations

```text
single operator token (no multi-user account system)
no TLS (localhost only)
no resume UI
no persistent history (chart is in-memory)
no Kernel hot-plug for registry toggles
no approval SLA / notifications
no device-specific 3D visualization
```

The Kernel audit log is the authoritative record; the console is a view.
