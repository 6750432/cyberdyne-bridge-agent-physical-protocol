#!/bin/bash
# Push the index-only wiki after GitHub creates the first page.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol"
WIKI_URL="git@github.com:${REPO}.wiki.git"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git clone "$WIKI_URL" wiki
cp "$ROOT/wiki/Home.md" "$ROOT/wiki/_Sidebar.md" wiki/
git -C wiki add Home.md _Sidebar.md
if git -C wiki diff --cached --quiet; then
  echo "wiki already up to date"
  exit 0
fi
git -C wiki -c user.name="cyberdyne-bridge" \
  -c user.email="cyberdyne-bridge@users.noreply.github.com" \
  commit -m "docs: seed index-only wiki"
git -C wiki push origin master
