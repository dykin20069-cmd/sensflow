"""Transaction orchestration tests for business application services."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sensflow.application.commands import (
    CreateOrderCommand,
    CustomerActionCommand,
    FinalizePurchaseCommand,
    OrderActionCommand,
    PrepareCreateOrderCommand,
    UpdateSettingCommand,
)
from sensflow.application.errors import AuthorizationError, ConflictError
from sensflow.application.gateways import MarketplaceCancellationResult
from sensflow.application.services import (
    CustomerApplicationService,
    OrderApplicationService,
    SettingsApplicationService,
)
from sensflow.domain.customer.service import RobloxIdentity
from sensflow.domain.enums import (
    ClientOrderStatus,
    MarketplaceOrderStatus,
    NotificationType,
    SettingField,
    TimelineEventType,
)
from sensflow.domain.marketplace.service import MarketplaceOrderResult
from sensflow.domain.settings.service import SettingsDefaults
from sensflow.infrastructure.database.models import (
    ClientOrder,
    Customer,
    MarketplaceOrder,
    SystemSettings,
)

NOW = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)


class TransactionContext:
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


class TransactionFactory:
    def __init__(self) -> None:
        self.session = MagicMock()

    def begin(self) -> TransactionContext:
        return TransactionContext(self.session)

    def __call__(self) -> TransactionContext:
        return TransactionContext(self.session)


def draft() -> ClientOrder:
    return ClientOrder(
        id=uuid4(),
        customer_id=uuid4(),
        requested_robux=100,
        current_status=ClientOrderStatus.DRAFT,
        current_place_id=200,
        marketplace_rate_limit=Decimal("1.25"),
    )


def settings_row(*, preferred_mode_default: bool = True) -> SystemSettings:
    return SystemSettings(
        id=uuid4(),
        maximum_purchase_rate=Decimal("1.25"),
        preferred_mode_default=preferred_mode_default,
        preferred_purchase_rate=Decimal("1.00"),
        preferred_timeout_minutes=35,
        low_balance_threshold=Decimal("10"),
        critical_balance_threshold=Decimal("5"),
        stock_notifications_enabled=True,
        automatic_reorder_enabled=True,
        automatic_reorder_interval_seconds=300,
        auto_requeue_delay_seconds=Decimal("5"),
        marketplace_monitoring_interval_seconds=30,
        synchronization_interval_seconds=20,
        marketplace_commission=Decimal("0.05"),
        usd_exchange_rate=Decimal("90"),
        telegram_notifications_enabled=True,
        notification_categories=[NotificationType.PURCHASE_COMPLETED],
        application_timezone="UTC",
    )


def settings_defaults() -> SettingsDefaults:
    return SettingsDefaults(
        maximum_purchase_rate=Decimal("1.25"),
        automatic_reorder_enabled=True,
        automatic_reorder_interval_seconds=300,
        marketplace_monitoring_interval_seconds=30,
        synchronization_interval_seconds=20,
        marketplace_commission=Decimal("0.05"),
        usd_exchange_rate=Decimal("90"),
        telegram_notifications_enabled=True,
        notification_categories=(NotificationType.PURCHASE_COMPLETED,),
        application_timezone="UTC",
    )


def test_payment_confirmation_routes_to_preorder_and_appends_timeline_atomically() -> None:
    async def exercise() -> None:
        order = draft()
        orders = MagicMock()
        orders.get_for_update = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda value: value)
        timeline = MagicMock()
        timeline.save = AsyncMock(side_effect=lambda value: value)
        marketplace = SimpleNamespace(has_suitable_stock=AsyncMock(return_value=False))
        service = OrderApplicationService(
            TransactionFactory(),
            marketplace=marketplace,
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch("sensflow.application.services.TimelineEventRepository", return_value=timeline),
        ):
            result = await service.confirm_payment(
                OrderActionCommand(order_id=order.id, operator_id=42)
            )

        events = [call.args[0].event_type for call in timeline.save.await_args_list]
        assert order.current_status is ClientOrderStatus.PREORDER
        assert events == [
            TimelineEventType.PAYMENT_CONFIRMED,
            TimelineEventType.PREORDER_CREATED,
        ]
        assert "PreOrder" in result.message

    asyncio.run(exercise())


def test_explicit_preorder_fallback_transitions_the_draft_without_marketplace_call() -> None:
    async def exercise() -> None:
        order = draft()
        orders = MagicMock()
        orders.get_for_update = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda value: value)
        customers = MagicMock()
        customers.get = AsyncMock(return_value=SimpleNamespace(current_username="Builderman"))
        timeline = MagicMock()
        timeline.save = AsyncMock(side_effect=lambda value: value)
        marketplace = SimpleNamespace(create_order=AsyncMock())
        service = OrderApplicationService(
            TransactionFactory(),
            marketplace=marketplace,
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch("sensflow.application.services.CustomerRepository", return_value=customers),
            patch("sensflow.application.services.TimelineEventRepository", return_value=timeline),
        ):
            result = await service.send_to_preorder(
                OrderActionCommand(order_id=order.id, operator_id=42)
            )

        assert result.message == "PreOrder created."
        assert result.order_id == order.id
        assert order.current_status is ClientOrderStatus.PREORDER
        assert [call.args[0].event_type for call in timeline.save.await_args_list] == [
            TimelineEventType.PAYMENT_CONFIRMED,
            TimelineEventType.PREORDER_CREATED,
        ]
        marketplace.create_order.assert_not_awaited()

    asyncio.run(exercise())


def test_operator_can_disable_auto_requeue_for_one_active_order() -> None:
    async def exercise() -> None:
        order = draft()
        order.current_status = ClientOrderStatus.PURCHASING
        order.automatic_requeue_enabled = True
        orders = MagicMock()
        orders.get_for_update = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda value: value)
        service = OrderApplicationService(TransactionFactory(), operator_id=42)

        with patch(
            "sensflow.application.services.ClientOrderRepository",
            return_value=orders,
        ):
            result = await service.toggle_auto_requeue(
                OrderActionCommand(order_id=order.id, operator_id=42)
            )

        assert order.automatic_requeue_enabled is False
        assert result.message == "Auto Requeue disabled."
        orders.save.assert_awaited_once_with(order)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("preferred_mode_default", "expected_preferred_rate"),
    ((True, Decimal("1.00")), (False, None)),
)
def test_create_order_uses_the_global_default_purchase_mode(
    preferred_mode_default: bool,
    expected_preferred_rate: Decimal | None,
) -> None:
    async def exercise() -> None:
        customer_id = uuid4()
        order_id = uuid4()
        customers = MagicMock()
        customers.get_by_username_for_update = AsyncMock(return_value=None)

        async def save_customer(customer: object) -> object:
            customer.id = customer_id
            return customer

        customers.save = AsyncMock(side_effect=save_customer)
        orders = MagicMock()
        orders.find_similar_active = AsyncMock(return_value=None)

        async def save_order(order: object) -> object:
            order.id = order_id
            return order

        orders.save = AsyncMock(side_effect=save_order)
        settings = MagicMock()
        settings.get_current = AsyncMock(
            return_value=settings_row(preferred_mode_default=preferred_mode_default)
        )
        timeline = MagicMock()
        timeline.save = AsyncMock(side_effect=lambda value: value)
        place_cache = MagicMock()
        place_cache.get_by_username_for_update = AsyncMock(return_value=None)
        place_cache.save = AsyncMock(side_effect=lambda value: value)
        roblox = SimpleNamespace(resolve_username=AsyncMock())
        service = OrderApplicationService(
            TransactionFactory(),
            roblox=roblox,
            settings_defaults=settings_defaults(),
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.CustomerRepository", return_value=customers),
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch(
                "sensflow.application.services.SystemSettingsRepository",
                return_value=settings,
            ),
            patch("sensflow.application.services.TimelineEventRepository", return_value=timeline),
            patch(
                "sensflow.application.services.UserPlaceCacheRepository",
                return_value=place_cache,
            ),
        ):
            result = await service.create_order(
                CreateOrderCommand(
                    username="Builderman",
                    requested_robux=100,
                    place_id=200,
                    operator_id=42,
                )
            )

        created = orders.save.await_args.args[0]
        created_customer = customers.save.await_args.args[0]
        event = timeline.save.await_args.args[0]
        roblox.resolve_username.assert_not_awaited()
        assert created_customer.roblox_user_id is None
        assert created_customer.current_username == "Builderman"
        assert created.customer_id == customer_id
        assert created.current_status is ClientOrderStatus.DRAFT
        assert created.marketplace_rate_limit == Decimal("1.25")
        assert created.preferred_rate == expected_preferred_rate
        assert created.preferred_timeout_minutes == (35 if preferred_mode_default else None)
        assert created.fallback_active is not preferred_mode_default
        assert event.event_type is TimelineEventType.ORDER_CREATED
        assert str(order_id) in result.message
        assert result.order_id == order_id
        remembered = place_cache.save.await_args.args[0]
        assert remembered.roblox_username == "builderman"
        assert remembered.place_id == 200

    asyncio.run(exercise())


def test_prepare_create_order_uses_remembered_place_without_roblox_request() -> None:
    async def exercise() -> None:
        place_cache = MagicMock()
        place_cache.get_by_username = AsyncMock(
            return_value=SimpleNamespace(place_id=200, place_name="My Tycoon")
        )
        roblox = SimpleNamespace(resolve_public_places=AsyncMock())
        service = OrderApplicationService(TransactionFactory(), roblox=roblox)

        with patch(
            "sensflow.application.services.UserPlaceCacheRepository",
            return_value=place_cache,
        ):
            selection = await service.prepare_create_order(
                PrepareCreateOrderCommand(username="Builderman", requested_robux=100)
            )

        assert selection.remembered_place is not None
        assert selection.remembered_place.place_id == 200
        assert selection.remembered_place.place_name == "My Tycoon"
        roblox.resolve_public_places.assert_not_awaited()

    asyncio.run(exercise())


def test_create_order_rejects_matching_waiting_order_without_override() -> None:
    async def exercise() -> None:
        customer = Customer(
            id=uuid4(),
            roblox_user_id=None,
            current_username="Builderman",
            current_place_id=200,
        )
        customers = MagicMock()
        customers.get_by_username_for_update = AsyncMock(return_value=customer)
        customers.save = AsyncMock(side_effect=lambda value: value)
        orders = MagicMock()
        orders.find_similar_active = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
        orders.save = AsyncMock()
        settings = MagicMock()
        settings.get_current = AsyncMock(return_value=settings_row())
        service = OrderApplicationService(
            TransactionFactory(),
            settings_defaults=settings_defaults(),
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.CustomerRepository", return_value=customers),
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch(
                "sensflow.application.services.SystemSettingsRepository",
                return_value=settings,
            ),
            pytest.raises(ConflictError, match="Similar active order"),
        ):
            await service.create_order(
                CreateOrderCommand(
                    username="Builderman",
                    requested_robux=100,
                    place_id=200,
                    operator_id=42,
                )
            )

        orders.save.assert_not_awaited()

    asyncio.run(exercise())


def test_payment_confirmation_creates_one_active_attempt_for_suitable_stock() -> None:
    async def exercise() -> None:
        order = draft()
        orders = MagicMock()
        orders.get_for_update = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda value: value)
        timeline = MagicMock()
        timeline.save = AsyncMock(side_effect=lambda value: value)
        attempts = MagicMock()
        attempts.get_active_for_client_order = AsyncMock(return_value=None)
        attempts.save = AsyncMock(side_effect=lambda value: value)
        marketplace = SimpleNamespace(
            has_suitable_stock=AsyncMock(return_value=True),
            create_order=AsyncMock(
                return_value=MarketplaceOrderResult("rbx-1", Decimal("1.00"), 100)
            ),
        )
        service = OrderApplicationService(
            TransactionFactory(),
            marketplace=marketplace,
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch("sensflow.application.services.TimelineEventRepository", return_value=timeline),
            patch(
                "sensflow.application.services.MarketplaceOrderRepository",
                return_value=attempts,
            ),
        ):
            await service.confirm_payment(OrderActionCommand(order_id=order.id, operator_id=42))

        attempt = attempts.save.await_args.args[0]
        assert order.current_status is ClientOrderStatus.PURCHASING
        assert attempt.marketplace_status is MarketplaceOrderStatus.ACTIVE
        assert attempt.client_order_id == order.id
        attempts.save.assert_awaited_once()

    asyncio.run(exercise())


def test_purchasing_cancellation_requires_external_confirmation() -> None:
    async def exercise() -> None:
        order = draft()
        order.current_status = ClientOrderStatus.PURCHASING
        attempt = MarketplaceOrder(
            id=uuid4(),
            client_order_id=order.id,
            rbxcreate_order_id="rbx-1",
            marketplace_status=MarketplaceOrderStatus.ACTIVE,
            purchase_rate=Decimal("1"),
            requested_robux=100,
            purchased_robux=0,
            remaining_robux=100,
        )
        orders = MagicMock()
        orders.get_for_update = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda value: value)
        attempts = MagicMock()
        attempts.get_active_for_client_order_for_update = AsyncMock(return_value=attempt)
        attempts.save = AsyncMock(side_effect=lambda value: value)
        timeline = MagicMock()
        timeline.save = AsyncMock(side_effect=lambda value: value)
        marketplace = SimpleNamespace(
            cancel_order=AsyncMock(return_value=MarketplaceCancellationResult(25, 75))
        )
        service = OrderApplicationService(
            TransactionFactory(),
            marketplace=marketplace,
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch(
                "sensflow.application.services.MarketplaceOrderRepository",
                return_value=attempts,
            ),
            patch("sensflow.application.services.TimelineEventRepository", return_value=timeline),
        ):
            await service.cancel_order(OrderActionCommand(order_id=order.id, operator_id=42))

        assert order.current_status is ClientOrderStatus.CANCELLED
        assert attempt.marketplace_status is MarketplaceOrderStatus.CANCELLED
        marketplace.cancel_order.assert_awaited_once_with("rbx-1")

    asyncio.run(exercise())


def test_purchase_completion_captures_finance_and_is_idempotent() -> None:
    async def exercise() -> None:
        order = draft()
        order.current_status = ClientOrderStatus.PURCHASING
        attempt = MarketplaceOrder(
            id=uuid4(),
            client_order_id=order.id,
            rbxcreate_order_id="rbx-1",
            marketplace_status=MarketplaceOrderStatus.ACTIVE,
            purchase_rate=Decimal("1"),
            requested_robux=100,
            purchased_robux=0,
            remaining_robux=100,
        )
        orders = MagicMock()
        orders.get_for_update = AsyncMock(return_value=order)
        orders.save = AsyncMock(side_effect=lambda value: value)
        attempts = MagicMock()
        attempts.get_for_update = AsyncMock(return_value=attempt)
        attempts.save = AsyncMock(side_effect=lambda value: value)
        timeline = MagicMock()
        timeline.save = AsyncMock(side_effect=lambda value: value)
        settings = MagicMock()
        settings.get_current = AsyncMock(return_value=settings_row())
        service = OrderApplicationService(
            TransactionFactory(),
            settings_defaults=settings_defaults(),
            operator_id=42,
            clock=lambda: NOW,
        )
        command = FinalizePurchaseCommand(
            order_id=order.id,
            marketplace_order_id=attempt.id,
            purchased_robux=100,
            marketplace_cost=Decimal("10"),
            roblox_tax_rate=Decimal("0.30"),
            robux_rounding="ROUND_DOWN",
            money_rounding="ROUND_HALF_UP",
        )

        with (
            patch("sensflow.application.services.ClientOrderRepository", return_value=orders),
            patch(
                "sensflow.application.services.MarketplaceOrderRepository",
                return_value=attempts,
            ),
            patch("sensflow.application.services.TimelineEventRepository", return_value=timeline),
            patch(
                "sensflow.application.services.SystemSettingsRepository",
                return_value=settings,
            ),
        ):
            result = await service.finalize_purchase(command)
            repeated = await service.finalize_purchase(command)

        assert result.message == "Order was completed."
        assert repeated.message == "Order is already completed."
        assert order.current_status is ClientOrderStatus.COMPLETED
        assert order.customer_receives == 70
        assert order.marketplace_commission == Decimal("0.5000")
        assert order.final_cost_usd == Decimal("10.5000")
        assert order.final_cost_local_currency == Decimal("945.0000")
        assert order.executed_rate == Decimal("105.00000000")
        assert attempt.marketplace_status is MarketplaceOrderStatus.COMPLETED
        assert timeline.save.await_count == 2

    asyncio.run(exercise())


def test_mutating_services_enforce_operator_authorization() -> None:
    async def exercise() -> None:
        service = OrderApplicationService(TransactionFactory(), operator_id=42)

        with pytest.raises(AuthorizationError):
            await service.cancel_order(OrderActionCommand(order_id=uuid4(), operator_id=7))

    asyncio.run(exercise())


def test_customer_refresh_updates_verified_username_and_place_histories_together() -> None:
    async def exercise() -> None:
        customer = Customer(
            id=uuid4(),
            roblox_user_id=42,
            current_username="OldName",
            current_place_id=100,
            archived=False,
            last_activity=NOW,
        )
        customers = MagicMock()
        customers.get_for_update = AsyncMock(return_value=customer)
        customers.save = AsyncMock(side_effect=lambda value: value)
        username_history = MagicMock()
        username_history.save = AsyncMock(side_effect=lambda value: value)
        place_history = MagicMock()
        place_history.save = AsyncMock(side_effect=lambda value: value)
        roblox = SimpleNamespace(
            refresh_identity=AsyncMock(return_value=RobloxIdentity(42, "NewName")),
            discover_place_id=AsyncMock(return_value=200),
        )
        service = CustomerApplicationService(
            TransactionFactory(),
            roblox=roblox,
            operator_id=42,
            clock=lambda: NOW,
        )

        with (
            patch("sensflow.application.services.CustomerRepository", return_value=customers),
            patch(
                "sensflow.application.services.CustomerUsernameHistoryRepository",
                return_value=username_history,
            ),
            patch(
                "sensflow.application.services.CustomerPlaceIDHistoryRepository",
                return_value=place_history,
            ),
        ):
            result = await service.refresh_customer(
                CustomerActionCommand(customer_id=customer.id, operator_id=42)
            )

        assert customer.current_username == "NewName"
        assert customer.current_place_id == 200
        assert username_history.save.await_args.args[0].username == "OldName"
        assert place_history.save.await_args.args[0].place_id == 100
        assert "refreshed" in result.message

    asyncio.run(exercise())


def test_settings_changes_are_validated_and_persisted_without_rewriting_orders() -> None:
    async def exercise() -> None:
        stored = settings_row()
        repository = MagicMock()
        repository.get_current_for_update = AsyncMock(return_value=stored)
        repository.save = AsyncMock(side_effect=lambda value: value)
        service = SettingsApplicationService(
            TransactionFactory(),
            defaults=settings_defaults(),
            operator_id=42,
        )

        with patch(
            "sensflow.application.services.SystemSettingsRepository",
            return_value=repository,
        ):
            result = await service.update_setting(
                UpdateSettingCommand(
                    operator_id=42,
                    field=SettingField.USD_EXCHANGE_RATE,
                    value="95.5",
                )
            )

        assert stored.usd_exchange_rate == Decimal("95.5")
        repository.save.assert_awaited_once_with(stored)
        assert "95.5" in result.message

    asyncio.run(exercise())
