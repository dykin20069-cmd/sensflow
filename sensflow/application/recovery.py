"""Startup recovery for interrupted Purchasing Client Orders."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.domain.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    TimelineEventType,
)
from sensflow.domain.order.service import return_to_preorder
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.infrastructure.database.base import utc_now
from sensflow.repositories import (
    ClientOrderRepository,
    MarketplaceOrderRepository,
    TimelineEventRepository,
)

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Summary of one startup or operator-triggered recovery pass."""

    checked: int
    repaired: int


class RecoveryService:
    """Reconcile every Client Order left in Purchasing after a process stop."""

    def __init__(
        self,
        sessions: SessionFactory,
        workflows: MarketplaceWorkflows,
    ) -> None:
        self._sessions = sessions
        self._workflows = workflows

    async def recover_incomplete_orders(self) -> RecoveryResult:
        """Synchronize active attempts and restore orphaned orders to PreOrder."""
        async with self._sessions() as session:
            purchasing = await ClientOrderRepository(session).list_by_status(
                ClientOrderStatus.PURCHASING,
                limit=10_000,
            )
            order_ids = tuple(order.id for order in purchasing)

        repaired = 0
        for order_id in order_ids:
            try:
                attempt_id = await self._recoverable_marketplace_order_id(order_id)
                if attempt_id is not None:
                    logger.info(
                        "recovery_order_checked",
                        extra={
                            "order_id": str(order_id),
                            "marketplace_order_id": str(attempt_id),
                            "recovery_action": "synchronize_attempt",
                        },
                    )
                    await self._workflows.synchronize_marketplace_order(attempt_id)
                else:
                    recovered_attempt_id = await self._restore_orphan(order_id)
                    if recovered_attempt_id is not None:
                        logger.info(
                            "recovery_order_checked",
                            extra={
                                "order_id": str(order_id),
                                "marketplace_order_id": str(recovered_attempt_id),
                                "recovery_action": "synchronize_racing_attempt",
                            },
                        )
                        await self._workflows.synchronize_marketplace_order(recovered_attempt_id)
                    else:
                        logger.info(
                            "recovery_order_checked",
                            extra={
                                "order_id": str(order_id),
                                "recovery_action": "returned_to_preorder",
                            },
                        )
                if await self._is_repaired(order_id):
                    repaired += 1
            except Exception:
                logger.exception(
                    "order_recovery_failed",
                    extra={"order_id": str(order_id), "recovery_action": "failed"},
                )
        return RecoveryResult(checked=len(order_ids), repaired=repaired)

    async def _is_repaired(self, order_id: UUID) -> bool:
        async with self._sessions() as session:
            order = await ClientOrderRepository(session).get(order_id)
            return order is not None and order.current_status is not ClientOrderStatus.PURCHASING

    async def _recoverable_marketplace_order_id(self, order_id: UUID) -> UUID | None:
        async with self._sessions() as session:
            repository = MarketplaceOrderRepository(session)
            active = await repository.get_active_for_client_order(order_id)
            if active is not None:
                return active.id
            attempts = await repository.list_for_client_order(order_id, limit=10_000)
            completed = next(
                (
                    attempt
                    for attempt in reversed(attempts)
                    if attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED
                ),
                None,
            )
            return None if completed is None else completed.id

    async def _restore_orphan(self, order_id: UUID) -> UUID | None:
        async with self._sessions.begin() as session:
            orders = ClientOrderRepository(session)
            order = await orders.get_for_update(order_id)
            if order is None or order.current_status is not ClientOrderStatus.PURCHASING:
                return None
            active = await MarketplaceOrderRepository(
                session
            ).get_active_for_client_order_for_update(order_id)
            if active is not None:
                return active.id
            attempts = await MarketplaceOrderRepository(session).list_for_client_order(
                order_id,
                limit=10_000,
            )
            completed = next(
                (
                    attempt
                    for attempt in reversed(attempts)
                    if attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED
                ),
                None,
            )
            if completed is not None:
                return completed.id
            now = utc_now()
            return_to_preorder(order)
            await orders.save(order)
            await TimelineEventRepository(session).save(
                create_timeline_event(
                    order,
                    TimelineEventType.PREORDER_CREATED,
                    "Startup recovery found no active Marketplace Order; returned to PreOrder.",
                    now + timedelta(microseconds=1),
                )
            )
            return None
