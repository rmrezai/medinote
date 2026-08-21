#!/bin/bash
set -u
cd "$(dirname "$0")"

APP_URL="http://127.0.0.1:5173"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"
COMPOSE_FILE="docker-compose.mac.yml"

echo "========================================"
echo "       MediNote Pilot 001 for Mac"
echo "========================================"
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is required but Docker was not found."
  echo "Opening the official Docker Desktop download page..."
  open "https://www.docker.com/products/docker-desktop/"
  echo
  read -r -p "After installing Docker Desktop, double-click Start MediNote.command again. Press Return to close. " _
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker Desktop..."
  open -a Docker >/dev/null 2>&1 || true
  echo "Waiting for Docker Desktop to become ready..."
  READY=0
  for i in $(seq 1 90); do
    if docker info >/dev/null 2>&1; then READY=1; break; fi
    sleep 2
  done
  if [ "$READY" -ne 1 ]; then
    echo "Docker Desktop did not become ready. Open Docker Desktop manually, wait until it is running, then try again."
    read -r -p "Press Return to close. " _
    exit 1
  fi
fi

echo "Starting MediNote..."
if ! docker compose -f "$COMPOSE_FILE" up -d --build; then
  echo
  echo "MediNote could not start. Showing recent service logs:"
  docker compose -f "$COMPOSE_FILE" logs --tail=80 || true
  read -r -p "Press Return to close. " _
  exit 1
fi

echo "Waiting for the MediNote API..."
READY=0
for i in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done

if [ "$READY" -ne 1 ]; then
  echo "MediNote started, but the API health check did not become ready."
  echo "Run 'MediNote Status.command' for details."
  read -r -p "Press Return to close. " _
  exit 1
fi

echo
echo "MediNote is running at: $APP_URL"
echo "Opening it in your default browser..."
open "$APP_URL"
echo
echo "You can close this Terminal window. MediNote will keep running."
echo "Double-click 'Stop MediNote.command' when you are finished."
sleep 3
