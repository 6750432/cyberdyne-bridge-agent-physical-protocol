# CBAP Operator Console

Local-first web console for the CBAP Kernel; optional remote mTLS.

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
persistent history chart
approval SLA notifications
```

## What it can do

```text
estop one device
estop all devices
resume one device / all devices (operator, reason + confirm)
release a lease (admin)
approve / deny a high-risk write (admin)
dual approval with a second operator token
scan MCP tools, create an onboarding manifest
sign an onboarding manifest (CBAP_MANIFEST_KEY)
enable / disable an onboarding registry entry
reload the Kernel registry
probe an onboarded MCP device
persistent history chart
SLA notification feed / optional webhook
```

Estop is latched. Resume is operator-only and requires:

```text
reason
confirm=RESUME
lease/pending/approval cleared
driver health ok
```

The UI labels the stopped state `LATCHED SAFE`.

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
bind:       default 127.0.0.1; remote bind requires TLS
Host:       explicit allowlist (`--allowed-host`)
Origin:     validated when present; https allowed under TLS
API auth:   HttpOnly SameSite=Strict operator session cookie
Login:      POST /api/login with the printed operator token
CSP:        self only, frame-ancestors none
No CORS
Resume: operator-only, reason + confirm=RESUME
MCP onboarding scan starts the operator-supplied argv (operator-only)
Optional mTLS: client certificate CN becomes the operator identity suffix
```

The page contains no token. Login attempts are rate-limited. The console is
local-first by default; remote binding requires TLS. A hostile process
running as the same OS user can read the process environment or files.
MCP onboarding is deliberately a powerful operator action: it can start a
local stdio server.

## Test

```bash
python3 -m unittest -v tests.cbap.test_console
```

## Limitations

```text
two fixed operator tokens (no full account system)
remote TLS requires operator-managed certs
history is JSONL-persisted; chart keeps last 300/device
Kernel registry reload is explicit, not a filesystem watcher
SLA notifications are in-memory + best-effort webhook
no device-specific 3D visualization
```

The Kernel audit log is the authoritative record; the console is a view.

## Remote mTLS

```bash
python3 console/server.py \
  --bind-host 0.0.0.0 --port 8765 \
  --allowed-host cbap.example:8765 \
  --tls-cert server.crt --tls-key server.key \
  --tls-ca client-ca.crt --tls-require-client-cert
```

The operator still logs in with an operator token. The client certificate CN
is appended to the operator identity (for example `operator-1@remote-ops`) and
is what dual approval counts as a distinct approver.
