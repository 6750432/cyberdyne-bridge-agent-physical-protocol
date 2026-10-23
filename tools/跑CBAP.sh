#!/usr/bin/env bash
# 跑CBAP.sh —— CBAP v0 网关 + 驱动壳 + 接线口适配器
# 不连真 Minecraft；用 tests/cbap/fake_hand.py。
set -euo pipefail
cd "$(dirname "$0")/.." || exit 3

echo "══ CBAP v0 · 网关/驱动/适配器 ══"
python3 tools/cbap_conformance.py --target fake
