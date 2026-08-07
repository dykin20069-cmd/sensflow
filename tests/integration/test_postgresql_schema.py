"""Verification of the migrated PostgreSQL schema and protection triggers."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sensflow.domain.enums import ClientOrderStatus
from sensflow.infrastructure.database.models import (
    Base,
    ClientOrder,
    Customer,
    CustomerUsernameHistory,
)

pytestmark = pytest.mark.integration

EXPECTED_ENUMS = {
    "client_order_status",
    "marketplace_order_status",
    "notification_delivery_status",
    "notification_type",
    "statistics_period",
    "system_log_level",
    "timeline_event_type",
}
EXPECTED_PROTECTION_TRIGGERS = {
    "trg_customer_username_history_append_only",
    "trg_customer_place_id_history_append_only",
    "trg_timeline_events_append_only",
    "trg_system_logs_append_only",
    "trg_customers_no_delete",
    "trg_marketplace_orders_no_delete",
    "trg_client_orders_completed_immutable",
}


def test_all_tables_enums_and_protection_triggers_exist(postgresql_url: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(postgresql_url)
        try:
            async with engine.connect() as connection:
                tables = await connection.run_sync(
                    lambda sync_connection: set(inspect(sync_connection).get_table_names())
                )
                enums = await connection.run_sync(
                    lambda sync_connection: {
                        item["name"] for item in inspect(sync_connection).get_enums()
                    }
                )
                trigger_rows = await connection.execute(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE NOT tgisinternal AND tgname LIKE 'trg_%'"
                    )
                )
                triggers = set(trigger_rows.scalars())
        finally:
            await engine.dispose()

        assert set(Base.metadata.tables) <= tables
        assert "alembic_version" in tables
        assert enums >= EXPECTED_ENUMS
        assert triggers >= EXPECTED_PROTECTION_TRIGGERS

    asyncio.run(scenario())


def test_append_only_and_completed_immutability_triggers_reject_updates(
    postgresql_url: str,
) -> None:
    async def scenario() -> None:
        engine = create_async_engine(postgresql_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        try:
            async with sessions.begin() as session:
                customer = Customer(
                    roblox_user_id=900_001,
                    current_username="TriggerCustomer",
                    current_place_id=800_001,
                    last_activity=now,
                )
                session.add(customer)
                await session.flush()
                history = CustomerUsernameHistory(
                    customer_id=customer.id,
                    username="OldTriggerName",
                )
                session.add(history)
                completed = ClientOrder(
                    customer_id=customer.id,
                    requested_robux=1000,
                    customer_receives=700,
                    current_status=ClientOrderStatus.COMPLETED,
                    current_place_id=customer.current_place_id,
                    marketplace_rate_limit=Decimal("2"),
                    marketplace_cost=Decimal("10"),
                    marketplace_commission=Decimal("1"),
                    final_cost_usd=Decimal("11"),
                    final_cost_local_currency=Decimal("990"),
                    usd_exchange_rate=Decimal("90"),
                    completed_at=now,
                )
                session.add(completed)
                await session.flush()
                history_id = history.id
                order_id = completed.id

            with pytest.raises(DBAPIError):
                async with sessions.begin() as session:
                    stored_history = await session.get(CustomerUsernameHistory, history_id)
                    assert stored_history is not None
                    stored_history.username = "MutatedName"

            with pytest.raises(DBAPIError):
                async with sessions.begin() as session:
                    stored_order = await session.get(ClientOrder, order_id)
                    assert stored_order is not None
                    stored_order.requested_robux = 2000
        finally:
            await engine.dispose()

    asyncio.run(scenario())
