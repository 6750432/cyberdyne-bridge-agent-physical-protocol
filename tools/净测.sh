#!/bin/bash
# 净测 —— 先停脑/手，再归档 logs/记忆（避免旧 inode），起手→清包→起脑
# 纪律：只归档不删除 ✓ ｜ 不碰 cyberdyne.sock ✓ ｜ 用法：bash tools/净测.sh [--tp X Y Z]
set -u
cd "$(dirname "$0")/.." || exit 1
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/1000/bus}"
export MC_RCON_PASSWORD="${MC_RCON_PASSWORD:-cyberdyne}"
B="$HOME/cyberdyne-备份/净测-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$B"

echo "── 停脑、停手（先停再归档）"
systemctl --user stop mc-brain
systemctl --user stop mc-hand
sleep 2

echo "── 归档 logs/ 与 记忆/（不删，移到 $B）"
[ -d logs ] && mv logs "$B/logs"
[ -d 记忆 ] && mv 记忆 "$B/记忆"
mkdir -p logs 记忆

echo "── 起手（等 spawn）"
systemctl --user start mc-hand
sleep 8

echo "── 清背包"
python3 tools/rcon.py 'clear DeepSeek' 2>/dev/null | tail -1 | sed 's/^/   /'
if [ "${1:-}" = "--tp" ] && [ $# -ge 4 ]; then
    echo "── 传送到 $2 $3 $4"
    python3 tools/rcon.py "tp DeepSeek $2 $3 $4" 2>/dev/null | tail -1 | sed 's/^/   /'
fi

echo "── 起脑"
systemctl --user start mc-brain
sleep 5
echo "── 就绪：空包、空记忆、新日志（归档在 $B）"
