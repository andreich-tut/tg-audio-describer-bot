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
  --privileged \
  -v warp-data:/var/lib/cloudflare-warp \
  --restart unless-stopped \
  "$IMAGE"

echo "Bot started. Logs: docker logs -f $CONTAINER"

# docker logs -f tg-voice     # live logs
# docker stop tg-voice        # stop bot
# docker restart tg-voice     # restart without rebuild
