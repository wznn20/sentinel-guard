#!/usr/bin/env bash
set -euo pipefail

WHEEL_URL="${WHEEL_URL:-https://github.com/wznn20/sentinel-guard/releases/latest/download/kx_agent-latest-py3-none-any.whl}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> KX Agent bootstrap"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install --upgrade "$WHEEL_URL"

mkdir -p "$HOME/.kx"
if [ ! -f "$HOME/.kx/config.yaml" ]; then
  "$PYTHON_BIN" -m kx_agent.cli setup --default
fi

echo
echo "KX Agent installed."
echo "Run:"
echo "  kx status --json"
echo "  kx chat"
echo "  kx app"
