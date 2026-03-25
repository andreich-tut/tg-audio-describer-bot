#!/bin/bash
set -e

COMPOSE="docker compose -f $(dirname "$0")/docker-compose.yml"
# Fallback to legacy docker-compose if plugin not available
if ! docker compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose -f $(dirname "$0")/docker-compose.yml"
fi

echo "Rebuilding and restarting..."
$COMPOSE build --pull
$COMPOSE up -d

echo "Cleaning up old images..."
docker image prune -f

echo "Done."
$COMPOSE ps
