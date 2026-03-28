#!/bin/bash
set -e

SCRIPT_DIR="$(dirname "$0")"
COMPOSE="docker compose -f $SCRIPT_DIR/../docker/docker-compose.yml"

mkdir -p ./data ./logs

echo "Building and starting services..."
$COMPOSE up -d --build

# Wait for container to be ready
echo "Waiting for container to start..."
sleep 3

# Get the bot container name
CONTAINER_NAME=$($COMPOSE ps -q bot 2>/dev/null | head -n1)
if [ -z "$CONTAINER_NAME" ]; then
  CONTAINER_NAME=$($COMPOSE ps -q 2>/dev/null | head -n1)
fi

# Run database migrations
echo "Running database migrations..."
if [ -n "$CONTAINER_NAME" ] && docker exec "$CONTAINER_NAME" python3 -m alembic upgrade head; then
  echo "✅ Migrations completed successfully"
else
  echo "⚠️  Skipping migrations (container not ready or not found)"
fi

echo "All services started."
$COMPOSE ps
