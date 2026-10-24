# CBAP v1 conformance

- **Status**: Implemented profile 1.0
- **Date**: 2026-10-24
- **Specification**: [`cbap-v1.md`](cbap-v1.md)
- **Implementation matrix**: [`implementation-matrix.md`](implementation-matrix.md)
- **Command**: `python3 tools/cbap_conformance.py --target fake`
- **Current suite**: **90 tests, 0 failures**

## Levels

```text
Core       hello/welcome, open/close, read/write, error, state, estop
Full       Core + ioctl/poll/lease/stat/device_list/cancel
Driver     Full + describe/health/watchdog
Security   token/operator/policy/audit/fencing/limits
MCP device tool receipt vs independent facts
Console    login/Host/Origin/estop/audit
```

## Core: 20 original cases

The original 20-case table remains the semantic baseline:

| # | Case | Expected |
|---|---|---|
| 1 | first packet must be hello | `E_PROTOCOL` |
| 2 | version mismatch | `E_VERSION` |
| 3 | auth failure | `E_AUTH` |
| 4 | unknown message type | `E_PROTOCOL` |
| 5 | unknown op | `E_NOTSUP` |
| 6 | unknown device | `E_NOENT` |
| 7 | read-only write | `E_PERM` |
| 8 | exclusive conflict | `E_BUSY` |
| 9 | no data | `E_AGAIN` |
| 10 | read timeout | `E_TIMEOUT` |
| 11 | write lifecycle | `ack` then `result` |
| 12 | idempotent write | one side effect |
| 13 | cancel | `E_CANCELED` |
| 14 | estop | `safe_state`, later write rejected |
| 15 | state seq | strictly increasing |
| 16 | stale probe | no false completion |
| 17 | lease expiry | `E_BUSY` |
| 18 | disconnect | lease released |
| 19 | oversize frame | `E_FRAME` |
| 20 | driver safety | safe state / health |

## Driver cases

```text
D1 describe missing safety.estop -> Kernel rejects registration
D4 health false -> refuse new lease
D5 driver crash -> device offline, lease released
D2/D3 driver-level physical proof remain hardware/implementation limits
```

## Additional suites

```text
tests/cbap/test_mcp_device.py   11  MCP facts/pin/estop/sandbox
tests/cbap/test_security.py     14  token/uid/policy/audit/fencing/limits
tests/cbap/test_console.py       3  login/Host+Origin/estop/audit
```

## Current status

```text
CBAP conformance: 90/90 passed
```

Not claimed as passed:

```text
physical emergency-stop certification
hardware root of trust / TPM
remote mTLS transport
independent CBAP-D process
poll(fds/events) filtering
progress notifications
```

Those are marked `planned`/`reserved` in the matrix, not in the 1.0
compatibility claim.
