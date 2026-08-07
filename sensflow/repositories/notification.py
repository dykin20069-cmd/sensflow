"""Notification repository."""

from uuid import UUID

from sqlalchemy import select

from sensflow.domain.enums import NotificationDeliveryStatus
from sensflow.infrastructure.database.models import Notification
from sensflow.repositories.base import Repository


class NotificationRepository(Repository[Notification]):
    """Persist and query notification delivery records."""

    model = Notification

    async def get_for_update(self, notification_id: UUID) -> Notification | None:
        statement = select(Notification).where(Notification.id == notification_id).with_for_update()
        return await self.session.scalar(statement)

    async def list_by_status(
        self,
        status: NotificationDeliveryStatus,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(Notification.delivery_status == status)
            .order_by(Notification.created_at.desc(), Notification.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def list_for_client_order(
        self,
        client_order_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(Notification.client_order_id == client_order_id)
            .order_by(Notification.created_at.desc(), Notification.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)
