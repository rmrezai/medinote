#!/bin/sh
set -eu
[ "$#" -eq 1 ] || { echo "Usage: $0 <backup.sql.gz.enc>" >&2; exit 2; }
cd "$(dirname "$0")/../.."
BACKUP="$1"
[ -f "$BACKUP" ] || { echo "Backup not found: $BACKUP" >&2; exit 1; }
set -a
. ./.env.pilot
set +a
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass env:BACKUP_PASSPHRASE -in "$BACKUP" -out "$TMP"

gzip -dc "$TMP" | docker compose --env-file .env.pilot -f docker-compose.pilot.yml exec -T db \
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
echo "Restore completed."
