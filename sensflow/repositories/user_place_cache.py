"""Repository for the remembered Roblox Place ID cache."""

from sqlalchemy import func, select

from sensflow.infrastructure.database.models import UserPlaceCache
from sensflow.repositories.base import Repository


class UserPlaceCacheRepository(Repository[UserPlaceCache]):
    """Persist and retrieve one remembered place per Roblox username."""

    model = UserPlaceCache

    async def get_by_username(self, username: str) -> UserPlaceCache | None:
        statement = select(UserPlaceCache).where(
            func.lower(UserPlaceCache.roblox_username) == username.casefold()
        )
        return await self.session.scalar(statement)

    async def get_by_username_for_update(self, username: str) -> UserPlaceCache | None:
        statement = (
            select(UserPlaceCache)
            .where(func.lower(UserPlaceCache.roblox_username) == username.casefold())
            .with_for_update()
        )
        return await self.session.scalar(statement)
