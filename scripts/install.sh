#!/usr/bin/env bash
set -euo pipefail

echo "Sentinel branding is deprecated for this runtime."
echo "Forwarding to the KX installer..."
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/install_kx.sh"
