"""Persistent notification delivery behavior."""

import asyncio
from contextlib import AbstractAsyncContextManager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sensflow.application.notifications import NotificationService
from sensflow.domain.enums import NotificationDeliveryStatus, NotificationType
from sensflow.infrastructure.database.models import Notification


class SessionContext(AbstractAsyncContextManager[object]):
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class Sessions:
    def __call__(self) -> SessionContext:
        return SessionContext()

    def begin(self) -> SessionContext:
        return SessionContext()


def test_pending_notification_is_delivered_and_marked_once() -> None:
    async def scenario() -> None:
        notification = Notification(
            id=uuid4(),
            notification_type=NotificationType.PURCHASE_COMPLETED,
            title="Purchase Completed",
            message="completed",
            delivery_status=NotificationDeliveryStatus.PENDING,
        )

        class Repository:
            async def list_by_status(self, *args: object, **kwargs: object) -> list[Notification]:
                return [notification]

            async def get_for_update(self, notification_id: object) -> Notification | None:
                return notification if notification_id == notification.id else None

            async def save(self, item: Notification) -> Notification:
                return item

        notifier = AsyncMock()
        service = NotificationService(Sessions(), notifier)  # type: ignore[arg-type]
        with patch(
            "sensflow.application.notifications.NotificationRepository",
            return_value=Repository(),
        ):
            delivered = await service.deliver_pending()

        assert delivered == 1
        notifier.send.assert_awaited_once_with("completed")
        assert notification.delivery_status is NotificationDeliveryStatus.DELIVERED
        assert notification.delivered_at is not None

    asyncio.run(scenario())
