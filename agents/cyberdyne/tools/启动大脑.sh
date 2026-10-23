#!/bin/bash
# 起"脑"（Python 反射层）。纯标准库，不连任何云端 API。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE"
while [ ! -d "$ROOT/kernel" ] && [ "$ROOT" != "/" ]; do
    ROOT="$(dirname "$ROOT")"
done
cd "$ROOT" || exit 1
exec nice -n 15 ionice -c3 python3 -u bridge.py "$@"
