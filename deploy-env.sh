#!/bin/bash
# Copy .env file to VPS for deployment

set -e

VPS_HOST="${VPS_HOST:-dev}"
VPS_USER="${VPS_USER:-dev}"
VPS_PATH="${VPS_PATH:-/home/dev/tg-audio-describer-bot}"

echo "Copying .env to VPS..."
scp .env ${VPS_USER}@${VPS_HOST}:${VPS_PATH}/.env

echo "Done! .env copied to ${VPS_PATH}"
echo "Now run the deploy workflow or SSH to VPS and run ./update.sh"
