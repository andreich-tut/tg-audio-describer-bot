#!/bin/sh
set -e

WARP_TIMEOUT=30

# Start Warp daemon
warp-svc &
WARP_PID=$!
trap "kill $WARP_PID 2>/dev/null" EXIT

# Wait for warp-svc to be ready
echo "Waiting for warp-svc..."
elapsed=0
until warp-cli status 2>/dev/null; do
  sleep 1
  elapsed=$((elapsed + 1))
  if [ "$elapsed" -ge "$WARP_TIMEOUT" ]; then
    echo "ERROR: warp-svc failed to start after ${WARP_TIMEOUT}s"
    exit 1
  fi
done

# Register (no-op if already registered)
echo "Registering Warp..."
warp-cli --accept-tos registration new || true

echo "Setting Warp mode and connecting..."
warp-cli mode warp
warp-cli connect

echo "Waiting for Warp to connect..."
elapsed=0
until warp-cli status 2>/dev/null | grep -q "Connected"; do
  sleep 1
  elapsed=$((elapsed + 1))
  if [ "$elapsed" -ge "$WARP_TIMEOUT" ]; then
    echo "ERROR: Warp failed to connect after ${WARP_TIMEOUT}s"
    warp-cli status || true
    exit 1
  fi
done
echo "Warp connected."

exec python bot.py
