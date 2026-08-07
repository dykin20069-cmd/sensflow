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


def test_stock_notification_cooldown_prevents_duplicate_queue_rows() -> None:
    async def scenario() -> None:
        stored: list[Notification] = []

        class Repository:
            async def exists_since(self, **kwargs: object) -> bool:
                return bool(stored)

            async def save(self, item: Notification) -> Notification:
                stored.append(item)
                return item

        service = NotificationService(Sessions(), AsyncMock())  # type: ignore[arg-type]
        with patch(
            "sensflow.application.notifications.NotificationRepository",
            return_value=Repository(),
        ):
            first = await service.queue_once(
                notification_type=NotificationType.STOCK_AVAILABLE,
                title="Suitable stock detected · 4.3",
                message="stock",
                throttle_seconds=60,
            )
            second = await service.queue_once(
                notification_type=NotificationType.STOCK_AVAILABLE,
                title="Suitable stock detected · 4.3",
                message="stock",
                throttle_seconds=60,
            )

        assert first is True
        assert second is False
        assert len(stored) == 1

    asyncio.run(scenario())
