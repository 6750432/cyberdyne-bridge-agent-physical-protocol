# M4 · Legacy bridge decision

**Status**: phase 1 (freeze + migration wrapper)  
**Date**: 2026-10-24  
**Decision**: archive the direct hand path; migrate the reusable brain through CBAP

---

## 1. Why

`bridge.py` is the pre-CBAP 4.4k-line brain/hand path. It bypasses:

```text
leases / fencing
Kernel audit
operator estop
facts + verify
token and policy
```

Running it beside the Kernel creates two device controllers.

## 2. Decision

```text
direct hand execution     -> archive (frozen, no new features)
brain / planner / plugins -> migrate through CBAP where still needed
root compatibility shims -> keep until all callers move
physical source           -> do not delete in phase 1
```

This is the safer half of “migrate or archive”: the old path remains
recoverable, but it is no longer the recommended runtime.

## 3. Migration path

```text
agents/cyberdyne/brain/bridge_cbap.py
  imports legacy bridge.py
  replaces 接线口 with CBAPHandAdapter
  calls legacy 主()
```

Run:

```bash
export CBAP_SOCKET="$PWD/cbap.sock"
export CBAP_DEVICE="mc://bot/DeepSeek"
bash agents/cyberdyne/tools/启动大脑-cbap.sh
```

The original `bridge.py` is not modified or unpinned.

Adapter limitations remain fail-closed:

```text
watch_items
furnace_watch
mode / friend / 变了 / scan_clear
```

## 4. Phases

### Phase 1 (this commit)

```text
[x] freeze legacy direct path
[x] inventory and archive boundary
[x] CBAP brain wrapper
[x] adapter env/config support
[x] wrapper smoke test
[ ] remove root shims
[ ] migrate all plugins
[ ] delete/retire direct hand path
```

### Phase 2

```text
move root shims out of the main entrypoint
repoint launch scripts to bridge_cbap.py
migrate supported plugin actions
keep old source in archive/legacy-bridge
```

### Phase 3

```text
decide whether to delete the old direct hand code
or keep it as an unmaintained read-only archive
```

## 5. Acceptance for phase 1

```text
[x] bridge.py fingerprint unchanged (658c947ec7f33d37)
[x] bridge_cbap.py --help works
[x] wrapper sets legacy.接线口 to CBAPHandAdapter
[x] root shims still work for old callers
[x] CBAP 101/101 tests
```

## 6. Non-goals

```text
rewriting the 4.4k-line brain in one step
supporting every legacy plugin over CBAP immediately
running bridge.py and Kernel against the same hand
```

Old path remains legacy; it is not a second security boundary.
