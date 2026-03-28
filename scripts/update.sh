#!/bin/bash
set -e

SCRIPT_DIR="$(dirname "$0")"
COMPOSE="docker compose -f $SCRIPT_DIR/../docker/docker-compose.yml"
# Fallback to legacy docker-compose if plugin not available
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose -f $SCRIPT_DIR/../docker/docker-compose.yml"
fi

# Get the bot container name from docker-compose
CONTAINER_NAME=$($COMPOSE ps -q bot 2>/dev/null | head -n1)
if [ -z "$CONTAINER_NAME" ]; then
  # Fallback: try to get full container ID by service name pattern
  CONTAINER_NAME=$($COMPOSE ps -q 2>/dev/null | head -n1)
fi
if [ -z "$CONTAINER_NAME" ]; then
  echo "❌ No running container found!"
  exit 1
fi

echo "Rebuilding and restarting..."
$COMPOSE build --pull
$COMPOSE up -d

# Wait for container to be ready
echo "Waiting for container to start..."
sleep 3

# Run database migrations
echo "Running database migrations..."
if docker exec "$CONTAINER_NAME" python3 -m alembic upgrade head; then
  echo "✅ Migrations completed successfully"
else
  echo "❌ Migration failed! Check logs with: docker logs $CONTAINER_NAME"
  exit 1
fi

echo "Cleaning up old images..."
docker image prune -f

echo "Done."
$COMPOSE ps
