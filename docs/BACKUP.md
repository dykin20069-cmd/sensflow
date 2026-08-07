# Backup and Restore

SensFlow uses PostgreSQL custom-format dumps. They are compressed by `pg_dump`, contain the schema and data, and are written to `backups/` by default.

## Create a backup

Ensure the PostgreSQL Compose service is running, then execute:

```sh
./scripts/backup.sh
```

The script loads `.env`, creates a UTC-timestamped `sensflow-YYYYMMDDTHHMMSSZ.dump`, and retains the newest ten dumps. Set `BACKUP_DIR` to place dumps outside the repository or on encrypted storage.

Copy production backups to a second, access-controlled storage location. A backup stored only on the application host is not sufficient disaster recovery.

## Restore a backup

```sh
./scripts/restore.sh /absolute/path/to/sensflow-YYYYMMDDTHHMMSSZ.dump
```

The script stops the application, displays the exact target database, and requires typing `RESTORE <database-name>`. Only then does it drop and recreate the configured database, restore the dump, and restart the application.

## Test restoration safely

Never test a restore against production.

1. Copy the production `.env` to an isolated test directory.
2. Change `POSTGRES_DB`, database credentials, Telegram token, and Compose project name.
3. Set `RBXCRATE_DRY_RUN=true`.
4. Start the isolated PostgreSQL service.
5. Restore the selected dump and run the acceptance checks against that isolated stack.
6. Destroy the isolated volume after verification.

Test restoration regularly; an untested dump is not a verified backup.
