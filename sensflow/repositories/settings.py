"""System Settings repository."""

from sqlalchemy import select

from sensflow.infrastructure.database.models import SystemSettings
from sensflow.repositories.base import Repository


class SystemSettingsRepository(Repository[SystemSettings]):
    """Persist and retrieve the singleton System Settings row."""

    model = SystemSettings

    async def get_current(self) -> SystemSettings | None:
        statement = select(SystemSettings).limit(1)
        return await self.session.scalar(statement)

    async def get_current_for_update(self) -> SystemSettings | None:
        statement = select(SystemSettings).limit(1).with_for_update()
        return await self.session.scalar(statement)
