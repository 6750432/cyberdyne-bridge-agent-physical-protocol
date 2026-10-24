# CBAP Security Hardening

Status: **13-item hardening pass, 2026-10-24**

This document maps the 13 requested controls to the code, tests, and the
limits that remain. It is deliberately not a claim of formal security.

## 1. Local socket identity

Implemented:

```text
socket mode 0600 after bind
SO_PEERCRED uid/gid/pid check
default allowed uid = current uid
--allowed-uid can add explicit operators
per-agent uid and token_sha256 in policy
agent_token is checked in addition to the global token
```

Residual:

```text
same UID can always read the process memory/files; use separate UIDs,
containers, or a dedicated operator account for a real multi-user boundary.
```

## 2. Mandatory token

Implemented:

```text
Kernel generates a token if none is supplied
token file <socket>.token, mode 0600, O_NOFOLLOW
CBAPClient auto-loads it for local clients
raw clients must present it in hello
wrong tokens are audited
five auth failures in 60s latch the Kernel into safe mode
```

The token is not printed in the welcome message.

## 3. Per-agent capability policy

Implemented:

```text
CapabilityPolicy: devices + read/write/lease/estop
default agent: read/write/lease, no estop
operator token: separate <socket>.operator file, mode 0600
device allowlist supports fnmatch patterns
open/read/write/lease/estop/stat/device_list enforce policy
```

Residual:

```text
agent_id is still self-asserted; the policy is not a substitute for
per-agent credentials when agents share one OS user.
```

## 4. Operator-only estop

Implemented:

```text
estop requires the operator token
a normal viewer session gets E_PERM
per-device estop is still device-scoped
global estop is operator-scoped
estop is latched; operator resume requires reason + confirm=RESUME
```

The console reads the operator token file; a human does not need to paste the
Kernel agent token.

## 5. Console operator login

Implemented:

```text
operator token printed by the console process (or CBAP_CONSOLE_OPERATOR_TOKEN)
POST /api/login -> HttpOnly SameSite=Strict session cookie
API requires a valid session; no token in HTML
Host + Origin validation
CSP self-only, frame-ancestors none
login attempt rate limit
```

Residual:

```text
same OS user can read the console process environment/token file;
console is local-first by default; remote binding requires mTLS.
```

## 6. Fencing and in-flight cancellation

Implemented:

```text
lease carries a monotonically increasing fencing_token
stat exposes the lease token
write accepts an optional fencing_token and rejects stale values
release/close cancel pending writes for that device
canceled writes receive E_CANCELED
```

Residual:

```text
already-sent driver/device actions may still complete; cancellation is
best-effort unless the driver has a native stop primitive.
```

## 7. Tamper-evident audit

Implemented:

```text
SHA-256 hash chain: prev + hash on every row
monotonic seq on every row
signed checkpoint (<audit>.checkpoint) with seq/hash
checkpoint mismatch detects tail truncation
optional HMAC with CBAP_AUDIT_KEY
0600 audit files, O_NOFOLLOW
local mirror path
optional remote NDJSON POST sink
AuditChain.verify() detects edits/truncation of the chain
audit failure latches safe mode
```

Residual:

```text
remote delivery is best-effort (no ack/retry protocol); a remote receiver
must persist and verify the HMAC chain independently.
```

## 8. MCP subprocess and manifest hardening

Implemented:

```text
stdio only, command is an argv list (no shell)
child inherits only PATH/HOME/LANG/TMPDIR by default
transport.env is explicit
optional rlimits and start_new_session
manifest HMAC-SHA256 via CBAP_MANIFEST_KEY
CBAP_REQUIRE_SIGNED_MANIFEST=1 rejects unsigned manifests
```

Residual:

```text
this is process hygiene, not a container or seccomp sandbox.
Optional `transport.sandbox: {"type": "bwrap"|"nsjail"}` wraps the child
when that binary is installed; absence is a hard failure, not a fallback.
For hostile MCP servers still use a separate UID/container/VM.
```

## 9. Session, inflight, rate, and frame limits

Implemented:

```text
max_connections pre-auth (default 128)
2s hello handshake timeout
max_sessions (default 64)
max_inflight per session (default 4)
rate_hz per session (default 10 writes/s)
uid_rate_hz per local uid (default 50/s)
existing protocol.MAX_FRAME
MCP stdout line cap 8 MB, stderr line cap 4 KB
facts command output cap 1 MB
limits advertised in welcome
```

## 10. Independent facts

Implemented:

```text
manifest facts.independent flag
verification result carries independent: true/false
Kernel require_independent_facts option rejects unmarked results
```

Residual:

```text
a declaration is not cryptographic proof. A malicious MCP server can lie
about both action and facts. A real independent sensor/attestation channel
is still required.
```

## 11. Watchdog and estop evidence

Implemented:

```text
Kernel watchdog checks driver state age against safety.watchdog_ms
stale state triggers driver.estop and latches the device
MCP estop can declare expect/verify facts and is marked estop_verified
console shows driver_ok and safe_state
```

Residual:

```text
no physical kill line or hardware watchdog was added. Software estop is
still software. A real deployment needs an out-of-band safety circuit.
```

## 12. Tool and instruction pinning

Implemented:

```text
MCP driver computes SHA-256 over advertised tool definitions
instructions digest is computed from server/discover
manifest pin_tools.tools_sha256 / instructions_sha256 can pin them
mismatch refuses connection
```

Residual:

```text
the MCP protocol does not yet require this; it is a driver-level control.
```

## 13. Anomaly detection and auto-degrade

Implemented:

```text
auth-failure counter -> safe mode
estop-burst counter -> safe mode
audit write failure -> safe mode
security.degraded visible in stat
```

Residual:

```text
no ML/anomaly service; these are deterministic fail-closed rules.
```

## Verification

```text
CBAP conformance: 100/100
security tests:   14
MCP device tests: 14
console tests:    5
console TLS:      1
registry hotplug: 1
transport tests:  2
```

Run:

```bash
python3 tools/cbap_conformance.py --target fake
```

## Known unchangeable limits

```text
root/same-uid attacker can read tokens and ptrace processes
malicious hardware can lie about its own safe state
supply-chain compromise of Python/Node dependencies is outside CBAP
physical emergency stop cannot be implemented in software
```

These are not hidden. They are the boundary of this layer.

## Secret-provider backends

`kernel/legacy_runtime/secrets.py` supports:

```text
CBAP_SECRET_BACKEND=env       default, backwards compatible
CBAP_SECRET_BACKEND=file      CBAP_SECRET_FILE, JSON, must be 0600
CBAP_SECRET_BACKEND=keyring   optional keyring package
```

A configured backend that is unavailable fails closed. This is still not a
TPM; root/same-uid can read process memory. TPM/TPM2 or an HSM remains an
infrastructure-level control.

## M1 追加控制

```text
MCP transport.run_as_uid / run_as_gid      root-only setuid drop
MCP sandbox bwrap/nsjail                    fail-closed if requested
MCP auto pin <manifest>.pins.json          TOFU, then mandatory match
MCP estop expect/verify                    required for safety.estop
CBAP_AUDIT_REQUIRE_ACK=1                   remote ack seq/hash required
Audit <audit>.remote-ack                   0600 ack file
resume                                     operator reason + confirm=RESUME
```

M1 runbook: `docs/M1-Trust-Boundary.md`.

Remaining non-software items:

```text
root/same-uid attacker
malicious MCP server lying about facts
certified physical emergency stop
TPM/HSM
remote Kernel transport mTLS (Console mTLS exists)
independent penetration test
```
