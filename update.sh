#!/bin/bash
set -e

IMAGE=tg-voice
CONTAINER=tg-voice

echo "Rebuilding image..."
docker build -t "$IMAGE" .

echo "Restarting container..."
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  docker stop "$CONTAINER"
  docker rm "$CONTAINER"
fi

docker run -d \
  --name "$CONTAINER" \
  --env-file .env \
  --privileged \
  -v warp-data:/var/lib/cloudflare-warp \
  --restart unless-stopped \
  "$IMAGE"

echo "Done. Logs: docker logs -f $CONTAINER"
