#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${HOME}/.openclaw/workspace-trading/trading-agent-runtime"

mkdir -p "${HOME}/.openclaw/workspace-trading"
rm -rf "${TARGET_DIR}"
cp -r "${BASE_DIR}" "${TARGET_DIR}"

echo "已安装 trading-agent 运行资产到 ${TARGET_DIR}"
