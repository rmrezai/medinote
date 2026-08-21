#!/bin/bash
set -u
cd "$(dirname "$0")"
echo "MediNote service status"
echo "-----------------------"
docker compose -f docker-compose.mac.yml ps
echo
echo "Recent logs"
echo "-----------"
docker compose -f docker-compose.mac.yml logs --tail=60
read -r -p "Press Return to close. " _
