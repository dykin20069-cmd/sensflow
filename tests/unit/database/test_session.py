"""Tests for async database construction."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sensflow.infrastructure.config import DatabaseSettings
from sensflow.infrastructure.database.session import (
    create_database_engine,
    create_session_factory,
    verify_database_connection,
)


def database_settings() -> DatabaseSettings:
    return DatabaseSettings(
        url=SecretStr("postgresql+asyncpg://user:password@localhost:5432/sensflow")
    )


def test_engine_and_session_factory_use_asyncpg() -> None:
    async def exercise() -> None:
        engine = create_database_engine(database_settings())
        session_factory = create_session_factory(engine)
        session = session_factory()

        assert isinstance(engine, AsyncEngine)
        assert engine.dialect.driver == "asyncpg"
        assert isinstance(session, AsyncSession)
        assert session.sync_session.expire_on_commit is False

        await session.close()
        await engine.dispose()

    asyncio.run(exercise())


def test_verify_database_connection_executes_probe() -> None:
    async def exercise() -> None:
        connection = AsyncMock()
        connection_context = MagicMock()
        connection_context.__aenter__ = AsyncMock(return_value=connection)
        connection_context.__aexit__ = AsyncMock(return_value=False)
        engine = MagicMock()
        engine.connect.return_value = connection_context

        await verify_database_connection(engine)

        connection.execute.assert_awaited_once()

    asyncio.run(exercise())
