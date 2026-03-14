#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${BASE_DIR}/.venv"

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${BASE_DIR}/requirements.txt"

echo "Stock agent venv ready: ${VENV_DIR}"
echo "Use: ${VENV_DIR}/bin/python ${BASE_DIR}/scripts/stock_agent.py --help"
