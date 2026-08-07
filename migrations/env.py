"""Alembic migration environment."""

import asyncio
import os

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from sensflow.infrastructure.database.models import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """Return the configured async PostgreSQL URL."""
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def configure_context(**connection_options: object) -> None:
    """Configure Alembic consistently for online and offline modes."""
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        **connection_options,
    )


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    configure_context(
        url=database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    """Run migrations on a synchronous connection supplied by SQLAlchemy."""
    configure_context(connection=connection)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and execute migrations."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against PostgreSQL."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
