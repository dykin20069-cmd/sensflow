"""Persistent notification queue and Telegram delivery coordination."""

import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.gateways import OperatorNotifier
from sensflow.domain.enums import (
    NotificationDeliveryStatus,
    NotificationType,
)
from sensflow.infrastructure.database.base import utc_now
from sensflow.infrastructure.database.models import Notification
from sensflow.repositories import NotificationRepository

logger = logging.getLogger(__name__)
SessionFactory = async_sessionmaker[AsyncSession]


class NotificationService:
    """Persist notifications before delivering them to the configured operator."""

    def __init__(
        self,
        sessions: SessionFactory,
        notifier: OperatorNotifier,
        *,
        recipient: int | str = "operator",
    ) -> None:
        self._sessions = sessions
        self._notifier = notifier
        self._recipient = recipient

    async def queue(
        self,
        *,
        notification_type: NotificationType,
        title: str,
        message: str,
        client_order_id: UUID | None = None,
    ) -> None:
        async with self._sessions.begin() as session:
            await NotificationRepository(session).save(
                Notification(
                    client_order_id=client_order_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    delivery_status=NotificationDeliveryStatus.PENDING,
                )
            )

    async def queue_once(
        self,
        *,
        notification_type: NotificationType,
        title: str,
        message: str,
        throttle_seconds: float,
        client_order_id: UUID | None = None,
    ) -> bool:
        """Persist a notification only when the same key is outside its cooldown."""
        since = utc_now() - timedelta(seconds=throttle_seconds)
        async with self._sessions.begin() as session:
            repository = NotificationRepository(session)
            if await repository.exists_since(
                notification_type=notification_type,
                title=title,
                since=since,
            ):
                return False
            await repository.save(
                Notification(
                    client_order_id=client_order_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    delivery_status=NotificationDeliveryStatus.PENDING,
                )
            )
        return True

    async def deliver_pending(self, *, limit: int = 100) -> int:
        async with self._sessions() as session:
            pending = await NotificationRepository(session).list_by_status(
                NotificationDeliveryStatus.PENDING,
                limit=limit,
            )
            notification_ids = tuple(item.id for item in pending)
        delivered = 0
        for notification_id in notification_ids:
            async with self._sessions.begin() as session:
                repository = NotificationRepository(session)
                notification = await repository.get_for_update(notification_id)
                if (
                    notification is None
                    or notification.delivery_status is not NotificationDeliveryStatus.PENDING
                ):
                    continue
                try:
                    await self._notifier.send(notification.message)
                except Exception:
                    notification.delivery_status = NotificationDeliveryStatus.FAILED
                    logger.exception(
                        "notification_delivery_failed",
                        extra={"notification_id": str(notification.id)},
                    )
                else:
                    notification.delivery_status = NotificationDeliveryStatus.DELIVERED
                    notification.delivered_at = utc_now()
                    delivered += 1
                    if notification.notification_type is NotificationType.STOCK_AVAILABLE:
                        logger.info(
                            "stock_notification_sent",
                            extra={
                                "rate": notification.title.removeprefix("Stock appeared · "),
                                "recipient": str(self._recipient),
                            },
                        )
                await repository.save(notification)
        return delivered
