#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
./deploy/scripts/preflight.sh .env.pilot
docker compose --env-file .env.pilot -f docker-compose.pilot.yml pull
docker compose --env-file .env.pilot -f docker-compose.pilot.yml build --pull
docker compose --env-file .env.pilot -f docker-compose.pilot.yml up -d
docker compose --env-file .env.pilot -f docker-compose.pilot.yml ps
