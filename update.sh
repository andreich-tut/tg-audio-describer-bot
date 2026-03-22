#!/bin/bash
set -e

echo "Rebuilding and restarting..."
"$(dirname "$0")/start.sh"

echo "Cleaning up old images..."
docker image prune -f

echo "Done."
