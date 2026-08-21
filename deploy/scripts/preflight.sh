#!/bin/sh
set -eu

ENV_FILE="${1:-.env.pilot}"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 1; }

if grep -q 'CHANGE_ME' "$ENV_FILE"; then
  echo "Refusing deployment: CHANGE_ME values remain in $ENV_FILE" >&2
  exit 1
fi

for cmd in docker openssl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing required command: $cmd" >&2; exit 1; }
done

docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required" >&2; exit 1; }

echo "Preflight passed."
