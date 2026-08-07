"""Timeline Event repository."""

from uuid import UUID

from sqlalchemy import select

from sensflow.infrastructure.database.models import TimelineEvent
from sensflow.repositories.base import Repository


class TimelineEventRepository(Repository[TimelineEvent]):
    """Append and retrieve Client Order timeline entries."""

    model = TimelineEvent

    async def list_for_client_order(
        self,
        client_order_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[TimelineEvent]:
        statement = (
            select(TimelineEvent)
            .where(TimelineEvent.client_order_id == client_order_id)
            .order_by(TimelineEvent.created_at, TimelineEvent.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)
