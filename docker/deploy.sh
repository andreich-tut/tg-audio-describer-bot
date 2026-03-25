#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying services ==="
bash "$SCRIPT_DIR/update.sh"
