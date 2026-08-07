# SensFlow

SensFlow is a private Telegram-first application for managing Version 1 Robux purchase workflows through RBXCrate. It tracks customers, paid and unpaid orders, external marketplace attempts, financial snapshots, timelines, recovery, and operator diagnostics.

## Architecture

SensFlow is a Python 3.13 modular monolith:

- aiogram provides the operator interface.
- Application services coordinate transactions and external calls.
- Domain services enforce order, marketplace, settings, and finance rules.
- SQLAlchemy asyncio repositories persist data in PostgreSQL 17.
- A typed httpx adapter communicates with RBXCrate.
- One in-process asyncio task performs synchronization and PreOrder checks.

There are no web servers, worker processes, message brokers, Redis, or microservices.

## Local startup

1. Copy `.env.example` to `.env` and replace every placeholder credential.
2. For safe testing, set `RBXCRATE_DRY_RUN=true`.
3. Start the stack:

   ```sh
   docker compose up -d --build
   ```

4. Check startup and migration output:

   ```sh
   docker compose logs -f application
   ```

The application waits for PostgreSQL health and applies Alembic migrations before starting Telegram polling.

## Tests

Run formatting, linting, and unit tests:

```sh
uv run ruff format --check sensflow tests
uv run ruff check sensflow tests
uv run pytest
```

PostgreSQL integration tests run when `TEST_DATABASE_URL` points to a PostgreSQL server on which the configured user may create temporary databases:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/postgres uv run pytest -m integration
```

See [Deployment](docs/DEPLOYMENT.md), [Operations](docs/OPERATIONS.md), [Backup and Restore](docs/BACKUP.md), and the [V1 Acceptance Checklist](docs/V1_ACCEPTANCE_CHECKLIST.md).
