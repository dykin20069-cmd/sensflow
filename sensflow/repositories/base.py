"""Shared mechanics for concrete SQLAlchemy repositories."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from sensflow.infrastructure.database.base import Base


class Repository[ModelT: Base]:
    """Provide the small set of persistence operations shared by all repositories."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: UUID) -> ModelT | None:
        """Load one row by its internal UUID."""
        return await self.session.get(self.model, entity_id)

    async def save(self, entity: ModelT) -> ModelT:
        """Add or flush one ORM entity without committing the transaction."""
        self.session.add(entity)
        await self.session.flush()
        return entity
