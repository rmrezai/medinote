#!/bin/bash
set -u
cd "$(dirname "$0")"
echo "Stopping MediNote..."
docker compose -f docker-compose.mac.yml down
echo "MediNote stopped. Your local database volume was preserved."
sleep 2
