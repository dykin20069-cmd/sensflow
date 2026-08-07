"""Unit tests for thin SQLAlchemy repository behavior."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from sensflow.infrastructure.database.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    NotificationDeliveryStatus,
    StatisticsPeriod,
    SystemLogLevel,
)
from sensflow.infrastructure.database.models import (
    ClientOrder,
    Customer,
    CustomerPlaceIDHistory,
    CustomerUsernameHistory,
    MarketplaceOrder,
    Notification,
    Statistics,
    SystemLog,
    SystemSettings,
    TimelineEvent,
)
from sensflow.repositories import (
    ClientOrderRepository,
    CustomerPlaceIDHistoryRepository,
    CustomerRepository,
    CustomerUsernameHistoryRepository,
    MarketplaceOrderRepository,
    NotificationRepository,
    StatisticsRepository,
    SystemLogRepository,
    SystemSettingsRepository,
    TimelineEventRepository,
)


def session_mock() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.get = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock(return_value=[])
    session.execute = AsyncMock(return_value=[])
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    return session


def sql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_every_database_table_has_one_concrete_repository() -> None:
    repository_models = {
        repository.model
        for repository in (
            CustomerRepository,
            CustomerUsernameHistoryRepository,
            CustomerPlaceIDHistoryRepository,
            ClientOrderRepository,
            MarketplaceOrderRepository,
            TimelineEventRepository,
            NotificationRepository,
            StatisticsRepository,
            SystemSettingsRepository,
            SystemLogRepository,
        )
    }

    assert repository_models == {
        Customer,
        CustomerUsernameHistory,
        CustomerPlaceIDHistory,
        ClientOrder,
        MarketplaceOrder,
        TimelineEvent,
        Notification,
        Statistics,
        SystemSettings,
        SystemLog,
    }


def test_shared_repository_gets_and_saves_without_committing() -> None:
    async def exercise() -> None:
        session = session_mock()
        customer_id = uuid4()
        customer = MagicMock(spec=Customer)
        session.get.return_value = customer
        repository = CustomerRepository(session)

        assert await repository.get(customer_id) is customer
        assert await repository.save(customer) is customer

        session.get.assert_awaited_once_with(Customer, customer_id)
        session.add.assert_called_once_with(customer)
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()

    asyncio.run(exercise())


def test_customer_repositories_build_lookup_search_and_history_queries() -> None:
    async def exercise() -> None:
        session = session_mock()
        customer_id = uuid4()

        customer_repository = CustomerRepository(session)
        await customer_repository.get_by_roblox_user_id(42)
        assert "customers.roblox_user_id = 42" in sql(session.scalar.await_args.args[0])

        await customer_repository.get_by_username("Builderman")
        assert "customers.current_username = 'Builderman'" in sql(session.scalar.await_args.args[0])

        await customer_repository.search("build", archived=False, offset=10, limit=5)
        search_sql = sql(session.scalars.await_args.args[0])
        assert "customers.current_username ILIKE '%%build%%'" in search_sql
        assert "customers.archived IS false" in search_sql
        assert "LIMIT 5 OFFSET 10" in search_sql

        username_history = CustomerUsernameHistoryRepository(session)
        await username_history.list_for_customer(customer_id)
        assert "customer_username_history.customer_id" in sql(session.scalars.await_args.args[0])

        place_history = CustomerPlaceIDHistoryRepository(session)
        await place_history.list_for_customer(customer_id)
        assert "customer_place_id_history.customer_id" in sql(session.scalars.await_args.args[0])

    asyncio.run(exercise())


def test_client_order_repository_exposes_queries_and_deletion_without_rules() -> None:
    async def exercise() -> None:
        session = session_mock()
        repository = ClientOrderRepository(session)
        order_id = uuid4()
        order = MagicMock(spec=ClientOrder)

        await repository.get_for_update(order_id)
        assert "FOR UPDATE" in sql(session.scalar.await_args.args[0])

        await repository.list_by_status(ClientOrderStatus.DRAFT, offset=10, limit=10)
        list_sql = sql(session.scalars.await_args.args[0])
        assert "client_orders.current_status = 'draft'" in list_sql
        assert "LIMIT 10 OFFSET 10" in list_sql

        await repository.search("Builder")
        search_sql = sql(session.scalars.await_args.args[0])
        assert "JOIN customers" in search_sql
        assert "customers.current_username ILIKE '%%Builder%%'" in search_sql

        await repository.delete(order)
        session.delete.assert_awaited_once_with(order)
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()

    asyncio.run(exercise())


def test_marketplace_order_repository_exposes_active_external_and_history_queries() -> None:
    async def exercise() -> None:
        session = session_mock()
        repository = MarketplaceOrderRepository(session)
        client_order_id = uuid4()

        await repository.get_by_external_id("rbx-1")
        assert "marketplace_orders.rbxcreate_order_id = 'rbx-1'" in sql(
            session.scalar.await_args.args[0]
        )

        await repository.get_active_for_client_order(client_order_id)
        active_sql = sql(session.scalar.await_args.args[0])
        assert "marketplace_orders.marketplace_status = 'active'" in active_sql

        await repository.list_for_client_order(client_order_id)
        history_sql = sql(session.scalars.await_args.args[0])
        assert "ORDER BY marketplace_orders.created_at" in history_sql

        await repository.list_by_status(MarketplaceOrderStatus.CANCELLED)
        assert "marketplace_orders.marketplace_status = 'cancelled'" in sql(
            session.scalars.await_args.args[0]
        )

        session.scalar.return_value = 3
        assert await repository.count_by_status(MarketplaceOrderStatus.ACTIVE) == 3
        assert "count(*)" in sql(session.scalar.await_args.args[0]).lower()

        await repository.list_completed_for_unfinished_client_orders()
        unfinished_sql = sql(session.scalars.await_args.args[0])
        assert "JOIN client_orders" in unfinished_sql
        assert "marketplace_orders.marketplace_status = 'completed'" in unfinished_sql
        assert "client_orders.current_status = 'purchasing'" in unfinished_sql

    asyncio.run(exercise())


def test_supporting_repositories_expose_only_persistence_queries() -> None:
    async def exercise() -> None:
        session = session_mock()
        client_order_id = uuid4()

        await TimelineEventRepository(session).list_for_client_order(client_order_id)
        assert "ORDER BY timeline_events.created_at" in sql(session.scalars.await_args.args[0])

        await NotificationRepository(session).list_by_status(NotificationDeliveryStatus.PENDING)
        assert "notifications.delivery_status = 'pending'" in sql(
            session.scalars.await_args.args[0]
        )

        statistics = StatisticsRepository(session)
        await statistics.get_for_period(StatisticsPeriod.DAILY, date(2026, 8, 6))
        statistics_sql = sql(session.scalar.await_args.args[0])
        assert "statistics.period = 'daily'" in statistics_sql
        assert "statistics.period_start = '2026-08-06'" in statistics_sql

        await SystemSettingsRepository(session).get_current()
        assert "FROM system_settings" in sql(session.scalar.await_args.args[0])

        await SystemLogRepository(session).list_recent(level=SystemLogLevel.ERROR)
        assert "system_logs.log_level = 'error'" in sql(session.scalars.await_args.args[0])

    asyncio.run(exercise())
