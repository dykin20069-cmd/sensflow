"""System Log repository."""

from sqlalchemy import select

from sensflow.domain.enums import SystemLogLevel
from sensflow.infrastructure.database.models import SystemLog
from sensflow.repositories.base import Repository


class SystemLogRepository(Repository[SystemLog]):
    """Append and retrieve operational log rows."""

    model = SystemLog

    async def list_recent(
        self,
        *,
        level: SystemLogLevel | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[SystemLog]:
        statement = select(SystemLog)
        if level is not None:
            statement = statement.where(SystemLog.log_level == level)
        statement = (
            statement.order_by(SystemLog.created_at.desc(), SystemLog.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)
