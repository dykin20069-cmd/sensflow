"""Complete V1 lifecycle against a real migrated PostgreSQL database."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sensflow.application.marketplace_workflows import MarketplaceWorkflows
from sensflow.application.rbxcreate_bridge import (
    MarketplaceCreateResult,
    MarketplaceStock,
    MarketplaceSyncResult,
)
from sensflow.domain.customer.service import RobloxIdentity, create_customer
from sensflow.domain.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    TimelineEventType,
)
from sensflow.domain.order.service import create_draft
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.infrastructure.database.models import SystemSettings
from sensflow.repositories import (
    ClientOrderRepository,
    CustomerRepository,
    MarketplaceOrderRepository,
    SystemSettingsRepository,
    TimelineEventRepository,
)

pytestmark = pytest.mark.integration


class LifecycleBridge:
    async def get_detailed_stock(self) -> tuple[MarketplaceStock, ...]:
        return (MarketplaceStock(Decimal("1.5"), 2, 5000, 10_000),)

    async def create_gamepass_order(self, **values: object) -> MarketplaceCreateResult:
        return MarketplaceCreateResult(
            external_order_id=str(values["order_id"]),
            status=MarketplaceOrderStatus.ACTIVE,
        )

    async def get_order_info(self, external_order_id: str) -> MarketplaceSyncResult:
        return MarketplaceSyncResult(
            external_order_id=external_order_id,
            status=MarketplaceOrderStatus.COMPLETED,
            purchased_quantity=None,
            remaining_quantity=None,
            vendor_id=None,
            price=Decimal("10"),
            error_reason=None,
            error_message=None,
        )


def test_complete_order_lifecycle_roundtrip(postgresql_url: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(postgresql_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        try:
            async with sessions.begin() as session:
                customer = await CustomerRepository(session).save(
                    create_customer(
                        RobloxIdentity(900_201, "LifecycleCustomer"),
                        800_201,
                        now,
                    )
                )
                order = await ClientOrderRepository(session).save(
                    create_draft(customer, 1000, customer.current_place_id, Decimal("2"))
                )
                await TimelineEventRepository(session).save(
                    create_timeline_event(
                        order,
                        TimelineEventType.ORDER_CREATED,
                        "Client Order created as Draft.",
                        now - timedelta(seconds=1),
                    )
                )
                await SystemSettingsRepository(session).save(
                    SystemSettings(
                        maximum_purchase_rate=Decimal("2"),
                        automatic_reorder_enabled=True,
                        automatic_reorder_interval_seconds=60,
                        auto_requeue_delay_seconds=Decimal("5"),
                        marketplace_monitoring_interval_seconds=60,
                        synchronization_interval_seconds=60,
                        marketplace_commission=Decimal("0.10"),
                        usd_exchange_rate=Decimal("90"),
                        telegram_notifications_enabled=True,
                        notification_categories=[],
                        application_timezone="UTC",
                    )
                )
                order_id = order.id

            workflows = MarketplaceWorkflows(
                sessions,
                LifecycleBridge(),  # type: ignore[arg-type]
                clock=lambda: now,
            )
            await workflows.start_purchase(order_id)

            async with sessions() as session:
                active = await MarketplaceOrderRepository(session).get_active_for_client_order(
                    order_id
                )
                assert active is not None
                marketplace_order_id = active.id

            await workflows.synchronize_marketplace_order(marketplace_order_id)

            async with sessions() as session:
                completed_order = await ClientOrderRepository(session).get_details(order_id)
                completed_attempt = await MarketplaceOrderRepository(session).get(
                    marketplace_order_id
                )

            assert completed_order is not None
            assert completed_attempt is not None
            assert completed_order.current_status is ClientOrderStatus.COMPLETED
            assert completed_attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED
            assert completed_order.marketplace_cost == Decimal("10.0000")
            assert completed_order.marketplace_commission == Decimal("1.0000")
            assert completed_order.final_cost_usd == Decimal("11.0000")
            assert completed_order.final_cost_local_currency == Decimal("990.0000")
            assert [event.event_type for event in completed_order.timeline_events] == [
                TimelineEventType.ORDER_CREATED,
                TimelineEventType.PAYMENT_CONFIRMED,
                TimelineEventType.PURCHASING_STARTED,
                TimelineEventType.MARKETPLACE_ORDER_CREATED,
                TimelineEventType.MARKETPLACE_ORDER_COMPLETED,
                TimelineEventType.ORDER_COMPLETED,
            ]
        finally:
            await engine.dispose()

    asyncio.run(scenario())
