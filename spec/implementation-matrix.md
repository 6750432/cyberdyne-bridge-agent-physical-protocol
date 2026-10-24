# CBAP v1 implementation matrix

**Status**: 1.0 implemented profile  
**Date**: 2026-10-24  
**Rule**: a feature may be called “CBAP v1 compatible” only if it is marked
`implemented` here and has a test in `tools/cbap_conformance.py`.

## Status vocabulary

```text
implemented   present and covered by the test suite
reserved      wire shape exists, but no producer/consumer in 1.0
planned       accepted direction, not in 1.0
deprecated    accepted for compatibility, no new use
removed       not part of the current profile
```

## 1. Transport and envelope

| Feature | Status | 1.0 notes | Evidence |
|---|---|---|---|
| Unix socket NDJSON | implemented | `AF_UNIX`, 64 KiB frame | conformance |
| TCP + token | optional | `KernelServer(tcp_host,tcp_port)` | test_transport |
| TLS/mTLS | optional | cert/key/ca + client cert | test_transport |
| CBOR / Protobuf | planned | not implemented | — |
| `hello` / `welcome` | implemented | token + policy | test_conformance |
| `ping` / `pong` | implemented | implementation extension | test_gateway |
| `progress` | reserved | Kernel does not emit | — |
| `event.seq` | implemented | monotonic per Kernel | conformance/event |
| `cancel` | implemented | same session only | test_conformance |
| `error` / errno | implemented | 16 codes | test_conformance |

## 2. CBAP-U syscalls

| Syscall | Status | 1.0 notes |
|---|---|---|
| `open` / `close` | implemented | mode `r/rw/exclusive` |
| `read` | implemented | `E_AGAIN` / `E_TIMEOUT` |
| `write` | implemented | lease + optional fencing token |
| `ioctl` | implemented | scan/watch/watch_items/furnace_watch |
| `poll` | implemented | `timeout_ms` + negotiated `fds/events` |
| `lease` / `release` | implemented | TTL, FIFO `wait_ms`, fence |
| `estop` | implemented, tightened | operator token required |
| `stat` | implemented | health/lease/security/pending |
| `device_list` | implemented | policy-filtered |
| `resume` | planned | currently `E_PERM` |
| `cancel` other session | removed from 1.0 | current `E_PERM` |

## 3. Driver ABI

| Feature | Status | Notes |
|---|---|---|
| in-process driver | implemented | `describe/health/wait_state/send/estop` |
| independent CBAP-D process | planned | v1.1 |
| MC driver | implemented | 21 ops, full legacy hand surface |
| dataflow driver | implemented | external MC Agent |
| MCP device driver | implemented | stdio, facts, pin, estop |
| MCP sandbox `bwrap/nsjail` | optional | fail-closed when requested/unavailable |
| MCP independent UID/GID | optional | `transport.run_as_uid/gid`; requires root |
| manifest HMAC | optional | `CBAP_REQUIRE_SIGNED_MANIFEST=1` in production |
| tool/instruction pinning | implemented | manifest pin or TOFU sidecar |
| independent fact command | implemented | `facts.source=command` |

## 4. Security profile

| Feature | Status | Notes |
|---|---|---|
| socket 0600 + peer uid | implemented | `SO_PEERCRED` |
| token file | implemented | `<socket>.token`, 0600, O_NOFOLLOW |
| operator token | implemented | `<socket>.operator`, estop only |
| per-agent uid/token | implemented | policy `uids`, `token_sha256` |
| capability policy | implemented | device fnmatch + 4 caps |
| pre-auth connection cap | implemented | 128 default, 2s hello |
| max sessions/inflight/rate | implemented | defaults in manual |
| per-uid rate | implemented | 50/s default |
| audit hash chain | implemented | seq/prev/hash |
| audit checkpoint | implemented | detects tail truncation |
| audit HMAC/remote sink | optional | best-effort remote |
| remote audit ack | optional | `CBAP_AUDIT_REQUIRE_ACK=1`; ack seq/hash |
| watchdog | implemented | software; 1s scan |
| estop fact verification | implemented | manifest `expect` |
| hardware estop hook | implemented | software-triggered relay command |
| physical certified estop | not software | hardware/infrastructure |
| TPM/HSM | planned | infrastructure |
| mTLS transport | optional | cert/key/CA; TCP only |

## 5. Agent adapters

| Adapter | Status | Notes |
|---|---|---|
| Cyberdyne MC hand | implemented | `drivers/mc` |
| MCP Mineflayer | implemented | 9 ops |
| Mindcraft | implemented | state/prompt/stop |
| Voyager | implemented | forward/exec/say/stop |
| Alice Forge | archived | source only, not built |

## 6. M2 transport/poll

| Feature | Status | Notes |
|---|---|---|
| feature negotiation | implemented | `hello.features` / `welcome.features` |
| poll fd/event filters | implemented | requires `poll_filter` |
| TCP token | optional | no peer UID on TCP |
| TLS | optional | cert/key |
| mTLS | optional | CA + required client cert |
| progress | reserved | no producer |
| CBOR | planned | JSON only |
| TCP warning | — | plaintext token without TLS |

## 7. M1 controls

| Control | Status | Notes |
|---|---|---|
| child env token scrub | implemented | default env allowlist |
| independent UID | optional | root only |
| bwrap/nsjail | optional | fail closed |
| manifest signature enforcement | optional | production env |
| automatic tool pin | implemented | `.pins.json` TOFU |
| estop safe-state requirement | implemented | no expect -> not safety.estop |
| remote ack verification | optional | ack file |
| resume | removed | explicit E_PERM |

## 8. Test mapping

```text
tools/cbap_conformance.py     96 cases
tests/cbap/test_conformance.py 20 core + D1/D4/D5 + security-adjacent
tests/cbap/test_mcp_device.py  14
tests/cbap/test_security.py    14
tests/cbap/test_console.py      3
tests/cbap/test_transport.py    2
```

## 7. Change rule

```text
A normative MUST without a test is not part of 1.0.
A planned feature must not be advertised in welcome.
A security tightening updates the spec; it does not silently keep the
weaker draft behavior.
```
