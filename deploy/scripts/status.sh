#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
docker compose --env-file .env.pilot -f docker-compose.pilot.yml ps
