#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname -- "$SCRIPT_DIR")

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER is required in .env or the environment}"
: "${POSTGRES_DB:?POSTGRES_DB is required in .env or the environment}"

BACKUP_DIR=${BACKUP_DIR:-"$PROJECT_DIR/backups"}
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILE="$BACKUP_DIR/sensflow-$TIMESTAMP.dump"
TEMP_FILE="$BACKUP_FILE.tmp"

mkdir -p "$BACKUP_DIR"
trap 'rm -f -- "$TEMP_FILE"' EXIT HUP INT TERM

docker compose --project-directory "$PROJECT_DIR" exec -T postgres \
    pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --format=custom --compress=9 --no-owner --no-privileges > "$TEMP_FILE"

mv -- "$TEMP_FILE" "$BACKUP_FILE"
trap - EXIT HUP INT TERM

find "$BACKUP_DIR" -type f -name 'sensflow-*.dump' -print \
    | sort -r \
    | awk 'NR > 10' \
    | while IFS= read -r old_backup; do
        rm -f -- "$old_backup"
    done

printf 'Backup created: %s\n' "$BACKUP_FILE"
