#!/bin/bash
set -e

IMAGE=tg-voice
CONTAINER=tg-voice

docker build -t "$IMAGE" .

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  docker stop "$CONTAINER"
  docker rm "$CONTAINER"
fi

docker run -d \
  --name "$CONTAINER" \
  --env-file .env \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -v warp-data:/var/lib/cloudflare-warp \
  --restart unless-stopped \
  "$IMAGE"

echo "Bot started. Logs: docker logs -f $CONTAINER"
