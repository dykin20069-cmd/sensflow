"""Real PostgreSQL roundtrip through every core order repository."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sensflow.domain.customer.service import RobloxIdentity, create_customer
from sensflow.domain.enums import TimelineEventType
from sensflow.domain.marketplace.service import MarketplaceOrderResult, create_marketplace_order
from sensflow.domain.order.service import create_draft, start_purchasing
from sensflow.domain.order.timeline import create_timeline_event
from sensflow.infrastructure.database.models import (
    CustomerPlaceIDHistory,
    CustomerUsernameHistory,
    UserPlaceCache,
)
from sensflow.repositories import (
    ClientOrderRepository,
    CustomerPlaceIDHistoryRepository,
    CustomerRepository,
    CustomerUsernameHistoryRepository,
    MarketplaceOrderRepository,
    TimelineEventRepository,
    UserPlaceCacheRepository,
)

pytestmark = pytest.mark.integration


def test_repository_graph_roundtrip(postgresql_url: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(postgresql_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        try:
            async with sessions.begin() as session:
                customers = CustomerRepository(session)
                customer = await customers.save(
                    create_customer(
                        RobloxIdentity(900_101, "RepositoryCustomer"),
                        800_101,
                        now,
                    )
                )
                username_history = await CustomerUsernameHistoryRepository(session).save(
                    CustomerUsernameHistory(
                        customer_id=customer.id,
                        username="PreviousRepositoryName",
                    )
                )
                place_history = await CustomerPlaceIDHistoryRepository(session).save(
                    CustomerPlaceIDHistory(customer_id=customer.id, place_id=800_100)
                )
                orders = ClientOrderRepository(session)
                order = await orders.save(
                    create_draft(customer, 1000, customer.current_place_id, Decimal("2"))
                )
                start_purchasing(order)
                await orders.save(order)
                marketplace_order = await MarketplaceOrderRepository(session).save(
                    create_marketplace_order(
                        order,
                        MarketplaceOrderResult(
                            external_order_id="repository-roundtrip",
                            purchase_rate=Decimal("1.5"),
                            requested_robux=1000,
                        ),
                        active_order_exists=False,
                    )
                )
                timeline_event = await TimelineEventRepository(session).save(
                    create_timeline_event(
                        order,
                        TimelineEventType.MARKETPLACE_ORDER_CREATED,
                        "Repository roundtrip event.",
                        now + timedelta(microseconds=1),
                    )
                )
                remembered = await UserPlaceCacheRepository(session).save(
                    UserPlaceCache(
                        roblox_username=customer.current_username,
                        place_id=customer.current_place_id,
                        place_name="Repository Place",
                        last_used_at=now,
                    )
                )
                customer_id = customer.id
                order_id = order.id

            async with sessions() as session:
                customer_details = await CustomerRepository(session).get_details(customer_id)
                order_details = await ClientOrderRepository(session).get_details(order_id)
                usernames = await CustomerUsernameHistoryRepository(session).list_for_customer(
                    customer_id
                )
                places = await CustomerPlaceIDHistoryRepository(session).list_for_customer(
                    customer_id
                )
                attempts = await MarketplaceOrderRepository(session).list_for_client_order(order_id)
                timeline = await TimelineEventRepository(session).list_for_client_order(order_id)
                remembered_lookup = await UserPlaceCacheRepository(session).get_by_username(
                    "repositorycustomer"
                )

            assert customer_details is not None
            assert order_details is not None
            assert usernames[0].id == username_history.id
            assert places[0].id == place_history.id
            assert attempts[0].id == marketplace_order.id
            assert timeline[0].id == timeline_event.id
            assert remembered_lookup is not None
            assert remembered_lookup.id == remembered.id
            assert customer_details.client_orders[0].id == order_id
            assert order_details.marketplace_orders[0].rbxcreate_order_id == (
                "repository-roundtrip"
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())
