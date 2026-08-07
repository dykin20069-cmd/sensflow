#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf 'Usage: %s /path/to/sensflow-backup.dump\n' "$0" >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname -- "$SCRIPT_DIR")
BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    printf 'Backup file does not exist: %s\n' "$BACKUP_FILE" >&2
    exit 2
fi

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER is required in .env or the environment}"
: "${POSTGRES_DB:?POSTGRES_DB is required in .env or the environment}"

case "$POSTGRES_DB" in
    postgres|template0|template1)
        printf 'Refusing to replace PostgreSQL system database: %s\n' "$POSTGRES_DB" >&2
        exit 2
        ;;
esac

printf 'WARNING: all existing data in database "%s" will be dropped.\n' "$POSTGRES_DB"
printf 'Type "RESTORE %s" to continue: ' "$POSTGRES_DB"
IFS= read -r confirmation
if [ "$confirmation" != "RESTORE $POSTGRES_DB" ]; then
    printf 'Restore cancelled.\n'
    exit 1
fi

docker compose --project-directory "$PROJECT_DIR" stop application
docker compose --project-directory "$PROJECT_DIR" exec -T postgres \
    dropdb --username "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB"
docker compose --project-directory "$PROJECT_DIR" exec -T postgres \
    createdb --username "$POSTGRES_USER" --owner "$POSTGRES_USER" "$POSTGRES_DB"
docker compose --project-directory "$PROJECT_DIR" exec -T postgres \
    pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --exit-on-error --no-owner --no-privileges < "$BACKUP_FILE"
docker compose --project-directory "$PROJECT_DIR" start application

printf 'Restore completed from: %s\n' "$BACKUP_FILE"
