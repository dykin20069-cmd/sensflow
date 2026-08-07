"""Tests for application input, DTO, service, and wiring foundations."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from sensflow.application.commands import CreateOrderCommand, OrderActionCommand
from sensflow.application.dto import PageDTO
from sensflow.application.errors import AuthorizationError, InputValidationError
from sensflow.application.queries import (
    GetStatisticsQuery,
    ListOrdersQuery,
    SearchCustomersQuery,
)
from sensflow.application.services import (
    CustomerApplicationService,
    OrderApplicationService,
    SettingsApplicationService,
    StatisticsApplicationService,
    SystemApplicationService,
)
from sensflow.application.validation import validate_input, validate_positive_integer
from sensflow.infrastructure.database.enums import (
    ClientOrderStatus,
    NotificationType,
    StatisticsPeriod,
)
from sensflow.infrastructure.database.models import (
    ClientOrder,
    Customer,
    Statistics,
    SystemSettings,
)


class SessionContext:
    def __init__(self) -> None:
        self.session = MagicMock()

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


class SessionFactory:
    def __call__(self) -> SessionContext:
        return SessionContext()


def test_validation_converts_untrusted_input_without_business_decisions() -> None:
    command = validate_input(
        CreateOrderCommand,
        {
            "username": "  Builderman  ",
            "requested_robux": "100",
            "place_id": "200",
            "operator_id": "42",
        },
    )

    assert command.username == "Builderman"
    assert command.requested_robux == 100
    assert command.place_id == 200
    assert command.operator_id == 42
    assert validate_positive_integer("42", "value") == 42

    with pytest.raises(InputValidationError):
        validate_positive_integer("42.0", "value")

    with pytest.raises(InputValidationError):
        validate_positive_integer("0", "value")


def test_page_dto_has_stable_empty_and_populated_page_counts() -> None:
    assert PageDTO(items=(), page=1, page_size=10, total_items=0).total_pages == 1
    assert PageDTO(items=(1,), page=2, page_size=10, total_items=21).total_pages == 3


def test_read_services_bound_stale_page_numbers() -> None:
    async def exercise() -> None:
        repository = MagicMock()
        repository.count_by_status = AsyncMock(return_value=21)
        repository.list_by_status = AsyncMock(return_value=[])
        service = OrderApplicationService(SessionFactory())

        with patch(
            "sensflow.application.services.ClientOrderRepository",
            return_value=repository,
        ):
            page = await service.list_orders(
                ListOrdersQuery(status=ClientOrderStatus.DRAFT, page=99, page_size=10)
            )

        assert page.page == 3
        repository.list_by_status.assert_awaited_once_with(
            ClientOrderStatus.DRAFT,
            offset=20,
            limit=10,
        )

    asyncio.run(exercise())


def test_order_application_service_reads_orders_and_defers_commands() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        customer = Customer(
            id=uuid4(),
            roblox_user_id=1,
            current_username="Builderman",
            current_place_id=2,
            created_at=now,
            updated_at=now,
            last_activity=now,
            archived=False,
        )
        order = ClientOrder(
            id=uuid4(),
            customer_id=customer.id,
            requested_robux=100,
            current_status=ClientOrderStatus.DRAFT,
            current_place_id=2,
            marketplace_rate_limit=Decimal("1.25"),
            created_at=now,
            updated_at=now,
        )
        order.customer = customer
        repository = MagicMock()
        repository.list_by_status = AsyncMock(return_value=[order])
        repository.count_by_status = AsyncMock(return_value=1)
        service = OrderApplicationService(SessionFactory())

        with patch(
            "sensflow.application.services.ClientOrderRepository",
            return_value=repository,
        ):
            page = await service.list_orders(ListOrdersQuery(status=ClientOrderStatus.DRAFT))

        assert page.total_items == 1
        assert page.items[0].customer_username == "Builderman"
        with pytest.raises(AuthorizationError):
            await service.confirm_payment(OrderActionCommand(order_id=order.id, operator_id=42))

    asyncio.run(exercise())


def test_customer_application_service_maps_search_results() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        customer = Customer(
            id=uuid4(),
            roblox_user_id=1,
            current_username="Builderman",
            current_place_id=2,
            created_at=now,
            updated_at=now,
            last_activity=now,
            archived=False,
        )
        repository = MagicMock()
        repository.search = AsyncMock(return_value=[customer])
        repository.count = AsyncMock(return_value=1)
        service = CustomerApplicationService(SessionFactory())

        with patch(
            "sensflow.application.services.CustomerRepository",
            return_value=repository,
        ):
            page = await service.search_customers(SearchCustomersQuery(search_term="Build"))

        assert page.items[0].roblox_user_id == 1
        assert page.items[0].archived is False

    asyncio.run(exercise())


def test_settings_and_statistics_services_only_read_persisted_projections() -> None:
    async def exercise() -> None:
        now = datetime.now(UTC)
        settings_row = SystemSettings(
            id=uuid4(),
            maximum_purchase_rate=Decimal("1.25"),
            automatic_reorder_enabled=True,
            automatic_reorder_interval_seconds=300,
            auto_requeue_delay_seconds=Decimal("5"),
            marketplace_monitoring_interval_seconds=30,
            synchronization_interval_seconds=30,
            marketplace_commission=Decimal("0.05"),
            usd_exchange_rate=Decimal("90"),
            telegram_notifications_enabled=True,
            notification_categories=[NotificationType.PURCHASE_COMPLETED],
            application_timezone="UTC",
            created_at=now,
            updated_at=now,
        )
        statistics_row = Statistics(
            id=uuid4(),
            period=StatisticsPeriod.DAILY,
            period_start=date(2026, 8, 6),
            total_orders=1,
            draft_orders=0,
            preorder_orders=0,
            purchasing_orders=0,
            completed_orders=1,
            cancelled_orders=0,
            total_purchased_robux=100,
            total_amount_paid=Decimal("10"),
            average_marketplace_rate=Decimal("1"),
            average_purchase_cost=Decimal("10"),
            total_marketplace_commission=Decimal("1"),
            created_at=now,
            updated_at=now,
        )
        settings_repository = MagicMock()
        settings_repository.get_current = AsyncMock(return_value=settings_row)
        statistics_repository = MagicMock()
        statistics_repository.get_latest = AsyncMock(return_value=statistics_row)

        with (
            patch(
                "sensflow.application.services.SystemSettingsRepository",
                return_value=settings_repository,
            ),
            patch(
                "sensflow.application.services.StatisticsRepository",
                return_value=statistics_repository,
            ),
        ):
            settings = await SettingsApplicationService(SessionFactory()).get_settings()
            statistics = await StatisticsApplicationService(SessionFactory()).get_statistics(
                GetStatisticsQuery(period=StatisticsPeriod.DAILY)
            )

        assert settings is not None
        assert settings.notification_categories == (NotificationType.PURCHASE_COMPLETED,)
        assert statistics is not None
        assert statistics.total_purchased_robux == 100

    asyncio.run(exercise())


def test_system_service_reports_database_failure_without_details() -> None:
    async def exercise() -> None:
        service = SystemApplicationService(MagicMock())
        error = OperationalError("SELECT 1", {}, Exception("database-secret"))

        with patch(
            "sensflow.application.services.verify_database_connection",
            new=AsyncMock(side_effect=error),
        ):
            status = await service.get_status()

        assert status.application_available is True
        assert status.database_available is False
        assert status.marketplace_available is None

    asyncio.run(exercise())
