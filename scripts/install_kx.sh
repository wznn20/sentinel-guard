#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/wznn20/sentinel-guard.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.kx/kx-agent}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> KX Agent bootstrap"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" pull --ff-only origin main
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -e "$INSTALL_DIR"

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
