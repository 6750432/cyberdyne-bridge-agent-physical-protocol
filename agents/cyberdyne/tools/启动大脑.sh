#!/bin/bash
# M4: default brain entrypoint is the CBAP wrapper.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE"
while [ ! -d "$ROOT/kernel" ] && [ "$ROOT" != "/" ]; do
    ROOT="$(dirname "$ROOT")"
done
cd "$ROOT" || exit 1
exec nice -n 15 ionice -c3 python3 -u agents/cyberdyne/brain/bridge_cbap.py "$@"
