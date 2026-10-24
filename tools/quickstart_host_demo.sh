#!/usr/bin/env bash
# 10-minute path: run the Kernel + host allowlist device over a local UDS.
# No Minecraft, no LLM, no Docker, no root, no public network.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/.."

TMP="$(mktemp -d /tmp/cbap-10min.XXXXXX)"
TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
BRIDGE_PID=""
cleanup() {
    if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

mkdir -p "$TMP/root"
python3 tools/cbap_host_bridge.py \
    --root "$TMP/root" \
    --socket "$TMP/cbap.sock" \
    --audit "$TMP/audit.jsonl" \
    --no-tcp \
    --no-display \
    --token "$TOKEN" \
    >"$TMP/bridge.out" 2>"$TMP/bridge.err" &
BRIDGE_PID=$!

i=0
while [ "$i" -lt 50 ]; do
    i=$((i + 1))
    [ -S "$TMP/cbap.sock" ] && break
    if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
        echo "host bridge failed to start:" >&2
        cat "$TMP/bridge.err" >&2
        exit 1
    fi
    sleep 0.1
done
if [ ! -S "$TMP/cbap.sock" ]; then
    echo "timed out waiting for $TMP/cbap.sock" >&2
    exit 1
fi

echo "workspace: $TMP"
echo "host bridge: $TMP/cbap.sock"
echo "token file: $TMP/cbap.sock.token (0600; not printed)"
echo

TOKEN="$TOKEN" CBAP_SOCK="$TMP/cbap.sock" python3 - <<'PY'
import os
from kernel.legacy_runtime.client import CBAPClient

c = CBAPClient(os.environ["CBAP_SOCK"], agent_id="10-minute")
c.connect()
w = c.hello(token=os.environ["TOKEN"])
print("kernel:", w["kernel_id"])
print("devices:", [d["device_id"] for d in w["devices"]])
r = c.open("host://fs", mode="exclusive")
assert r["ok"], r
fd = r["payload"]["fd"]
assert c.lease(fd, ttl_ms=10000)["ok"]
_, _, res = c.write(fd, {
    "op": "write_file",
    "args": {"path": "hello.txt",
             "content": "hello from the 10-minute path\n"},
})
assert res["ok"], res
facts = res["facts"]
print("write:", facts["path"], facts["bytes"], "bytes")
print("sha256:", facts["sha256"])
print("stat:", c.stat(fd)["ok"])
c.release(fd)
c.close()
PY

echo
echo "file contents:"
cat "$TMP/root/hello.txt"
echo
echo "audit: $TMP/audit.jsonl"
echo "done: protocol + host allowlist path verified."
