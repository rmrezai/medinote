#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
[ -f .env.pilot ] || { echo "Missing .env.pilot" >&2; exit 1; }
set -a
. ./.env.pilot
set +a
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

mkdir -p deploy/backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TMP="deploy/backups/medinote-${STAMP}.sql.gz"
OUT="${TMP}.enc"

docker compose --env-file .env.pilot -f docker-compose.pilot.yml exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl | gzip -9 > "$TMP"

openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass env:BACKUP_PASSPHRASE -in "$TMP" -out "$OUT"
rm -f "$TMP"
chmod 600 "$OUT"

find deploy/backups -type f -name 'medinote-*.sql.gz.enc' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
printf '%s\n' "$OUT"
