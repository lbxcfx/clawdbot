#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${HOME}/.openclaw/workspace-trading/stock-agent-local-prototype"

mkdir -p "${HOME}/.openclaw/workspace-trading"
rm -rf "${TARGET_DIR}"
cp -r "${BASE_DIR}" "${TARGET_DIR}"

echo "Installed stock-agent local prototype to ${TARGET_DIR}"
