# Deployment

## Prerequisites

- Docker Engine with Docker Compose v2
- A Telegram bot token and the numeric Telegram operator ID
- RBXCrate API credentials
- Persistent disk space for the PostgreSQL volume and off-host backups

## Prepare the environment

Copy `.env.example` to `.env`. Replace every placeholder, use a strong PostgreSQL password, and review all financial and interval values. The application fails before startup if critical credentials are missing or if intervals and purchase-rate bounds are invalid.

Set `RBXCRATE_DRY_RUN=true` for deployment verification. Change it to `false` only after the dry-run acceptance checklist passes and the live account balance is approved.

Do not commit `.env`. Restrict it to the deployment account:

```sh
chmod 600 .env
```

## Start or update

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f application
```

PostgreSQL must become healthy before the application starts. The application container runs `alembic upgrade head` before Telegram polling, so a migration failure prevents an unsafe partial startup.

To update:

1. Create and verify a backup.
2. Pull or copy the reviewed release.
3. Review `.env.example` for new settings.
4. Run `docker compose up -d --build`.
5. Inspect logs and the Telegram System Status screen.

## Logs

```sh
docker compose logs --tail=200 application
docker compose logs -f application
docker compose logs --tail=200 postgres
```

Application logs are one JSON object per line. Credentials, URLs containing passwords, Telegram tokens, and raw RBXCrate payloads must never appear.

## Migrations

Migrations run automatically during container startup. For an explicit check:

```sh
docker compose run --rm application /app/.venv/bin/alembic current
docker compose run --rm application /app/.venv/bin/alembic upgrade head
```

Do not downgrade a production database without a reviewed recovery plan and verified backup.
