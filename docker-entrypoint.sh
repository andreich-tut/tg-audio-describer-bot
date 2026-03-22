#!/bin/sh
set -e

# Start Warp daemon
warp-svc &
sleep 3

# Register if not yet registered
if ! warp-cli registration show 2>/dev/null | grep -q "Device ID"; then
    echo "Registering Warp..."
    warp-cli registration new
fi

warp-cli mode warp
warp-cli connect

echo "Waiting for Warp to connect..."
until warp-cli status 2>/dev/null | grep -q "Connected"; do sleep 1; done
echo "Warp connected."

exec python bot.py
