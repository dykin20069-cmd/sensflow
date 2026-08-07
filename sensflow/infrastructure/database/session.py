"""SQLAlchemy async engine and session construction."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sensflow.infrastructure.config import DatabaseSettings


def create_database_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Create an asyncpg-backed SQLAlchemy engine."""
    return create_async_engine(
        settings.url.get_secret_value(),
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the application's async session factory."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def verify_database_connection(engine: AsyncEngine) -> None:
    """Verify that PostgreSQL accepts a simple query."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
