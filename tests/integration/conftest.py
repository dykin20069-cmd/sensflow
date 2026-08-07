"""Temporary PostgreSQL database fixtures for opt-in integration tests."""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def _create_temporary_database(admin_url: str, database_name: str) -> None:
    engine = create_async_engine(admin_url)
    try:
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()


async def _drop_temporary_database(admin_url: str, database_name: str) -> None:
    engine = create_async_engine(admin_url)
    try:
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def postgresql_url() -> Iterator[str]:
    """Create a migrated temporary database or skip when PostgreSQL is unavailable."""
    configured_url = os.environ.get("TEST_DATABASE_URL")
    if not configured_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    parsed = make_url(configured_url)
    if parsed.drivername != "postgresql+asyncpg":
        pytest.skip("TEST_DATABASE_URL must use postgresql+asyncpg")

    database_name = f"sensflow_test_{uuid4().hex}"
    admin_url = parsed.set(database=parsed.database or "postgres").render_as_string(
        hide_password=False
    )
    test_url = parsed.set(database=database_name).render_as_string(hide_password=False)

    try:
        asyncio.run(_create_temporary_database(admin_url, database_name))
    except Exception:
        pytest.skip("PostgreSQL is unavailable or temporary database creation is not permitted")

    try:
        configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            command.upgrade(configuration, "head")
        yield test_url
    finally:
        asyncio.run(_drop_temporary_database(admin_url, database_name))
