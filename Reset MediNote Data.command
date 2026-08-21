#!/bin/bash
set -u
cd "$(dirname "$0")"
echo "WARNING: This permanently deletes the LOCAL MediNote database used by this Mac launcher."
echo "Use only for synthetic/de-identified Pilot 001 testing."
read -r -p "Type DELETE to continue: " ANSWER
if [ "$ANSWER" != "DELETE" ]; then
  echo "Cancelled."
  sleep 2
  exit 0
fi
docker compose -f docker-compose.mac.yml down -v
echo "Local MediNote data deleted."
sleep 2
