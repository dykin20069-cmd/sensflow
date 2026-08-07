"""Tests for the aiogram presentation foundation."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, User
from pydantic import SecretStr

from sensflow.application.dto import (
    CustomerAction,
    CustomerDetailDTO,
    OrderAction,
    OrderDetailDTO,
)
from sensflow.application.errors import FeatureUnavailableError, InputValidationError
from sensflow.infrastructure.config import TelegramSettings
from sensflow.infrastructure.database.enums import ClientOrderStatus
from sensflow.presentation.telegram.bot import create_bot
from sensflow.presentation.telegram.callbacks import (
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    OrderCallback,
    OrderCallbackAction,
)
from sensflow.presentation.telegram.dispatcher import create_dispatcher
from sensflow.presentation.telegram.errors import error_screen
from sensflow.presentation.telegram.formatting import format_decimal
from sensflow.presentation.telegram.keyboards import main_menu_keyboard
from sensflow.presentation.telegram.middleware import AuthorizationMiddleware
from sensflow.presentation.telegram.pagination import Pagination
from sensflow.presentation.telegram.rendering import (
    render_customer_details,
    render_main_menu,
    render_order_details,
)
from sensflow.presentation.telegram.states import (
    CreateOrderStates,
    CustomerPlaceIDStates,
    CustomerSearchStates,
    DraftEditStates,
    OrderSearchStates,
    SettingsEditStates,
)


def test_callback_payloads_are_typed_and_fit_telegram_limit() -> None:
    order_id = uuid4()
    packed = OrderCallback(
        action=OrderCallbackAction.DETAILS,
        order_id=order_id,
    ).pack()

    assert len(packed.encode()) <= 64
    assert OrderCallback.unpack(packed).order_id == order_id
    assert MenuCallback.unpack(MenuCallback(section=MainSection.ORDERS).pack()).section == (
        MainSection.ORDERS
    )
    assert NavigationCallback(action=NavigationAction.HOME).pack() == "n:home:main"


def test_main_menu_and_fsm_cover_documented_skeleton() -> None:
    keyboard = main_menu_keyboard()
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert labels == [
        "+ Create Order",
        "📦 Orders",
        "👤 Customers",
        "📊 Statistics",
        "⚙️ Settings",
        "🟢 System Status",
    ]
    assert render_main_menu().reply_markup == keyboard
    assert CreateOrderStates.username.state is not None
    assert OrderSearchStates.query.state is not None
    assert DraftEditStates.requested_robux.state is not None
    assert DraftEditStates.place_id.state is not None
    assert CustomerSearchStates.query.state is not None
    assert CustomerPlaceIDStates.place_id.state is not None
    assert SettingsEditStates.value.state is not None


def test_pagination_boundaries_are_stable() -> None:
    first = Pagination(page=1, page_size=10, total_items=21)
    last = Pagination(page=3, page_size=10, total_items=21)
    empty = Pagination(page=1, page_size=10, total_items=0)

    assert first.previous_page is None
    assert first.next_page == 2
    assert last.previous_page == 2
    assert last.next_page is None
    assert empty.total_pages == 1


def test_renderers_escape_content_and_use_service_supplied_actions() -> None:
    now = datetime.now(UTC)
    order = OrderDetailDTO(
        id=uuid4(),
        customer_username="<operator>",
        status=ClientOrderStatus.DRAFT,
        requested_robux=100,
        customer_receives=None,
        current_place_id=2,
        marketplace_rate_limit=Decimal("1.25"),
        marketplace_cost=None,
        marketplace_commission=None,
        final_cost_usd=None,
        final_cost_local_currency=None,
        created_at=now,
        completed_at=None,
        timeline=(),
        available_actions=(
            OrderAction.CONFIRM_PAYMENT,
            OrderAction.EDIT_DRAFT,
            OrderAction.DELETE_DRAFT,
        ),
    )
    customer = CustomerDetailDTO(
        id=uuid4(),
        username="<customer>",
        roblox_user_id=1,
        current_place_id=2,
        archived=False,
        notes="A & B",
        username_history=(),
        place_id_history=(),
        orders=(),
        available_actions=(CustomerAction.UPDATE_PLACE_ID,),
    )

    order_screen = render_order_details(order)
    customer_screen = render_customer_details(customer)
    manual_customer_screen = render_customer_details(replace(customer, roblox_user_id=None))

    assert "&lt;operator&gt;" in order_screen.text
    assert "Confirm Payment" in str(order_screen.reply_markup)
    assert "Edit Draft" in str(order_screen.reply_markup)
    assert "Delete Draft" in str(order_screen.reply_markup)
    assert "&lt;customer&gt;" in customer_screen.text
    assert "A &amp; B" in customer_screen.text
    assert "Update Place ID" in str(customer_screen.reply_markup)
    assert "Roblox User ID: Not verified" in manual_customer_screen.text
    assert format_decimal(Decimal("0.0000")) == "0"


def test_error_presentation_is_safe_and_specific() -> None:
    validation = error_screen(InputValidationError(("username: required",)))
    unavailable = error_screen(FeatureUnavailableError("Create Order"))
    unexpected = error_screen(RuntimeError("database-secret"))

    assert "username: required" in validation.text
    assert "later milestone" in unavailable.text
    assert "database-secret" not in unexpected.text


def test_authorization_middleware_allows_only_configured_operator() -> None:
    async def exercise() -> None:
        middleware = AuthorizationMiddleware(operator_id=42)
        handler = AsyncMock(return_value="handled")
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        operator = User(id=42, is_bot=False, first_name="Operator")
        stranger = User(id=7, is_bot=False, first_name="Stranger")

        result = await middleware(handler, event, {"event_from_user": operator})
        denied = await middleware(handler, event, {"event_from_user": stranger})

        assert result == "handled"
        assert denied is None
        handler.assert_awaited_once()
        event.answer.assert_awaited_once_with("Access denied.")

        callback = MagicMock(spec=CallbackQuery)
        callback.answer = AsyncMock()
        await middleware(handler, callback, {"event_from_user": stranger})
        callback.answer.assert_awaited_once_with("Access denied.", show_alert=True)

    asyncio.run(exercise())


def test_bot_and_dispatcher_wiring_use_aiogram_memory_foundation() -> None:
    async def exercise() -> None:
        bot = create_bot(
            TelegramSettings(
                bot_token=SecretStr("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"),
                operator_id=42,
                notifications_enabled=True,
            )
        )
        orders = MagicMock()
        customers = MagicMock()
        settings = MagicMock()
        statistics = MagicMock()
        system = MagicMock()
        dispatcher = create_dispatcher(
            orders=orders,
            customers=customers,
            settings=settings,
            statistics=statistics,
            system=system,
            operator_id=42,
        )

        assert bot.default.parse_mode == ParseMode.HTML
        assert isinstance(dispatcher.storage, MemoryStorage)
        assert dispatcher.workflow_data["orders"] is orders
        assert dispatcher.workflow_data["customers"] is customers
        assert dispatcher.workflow_data["settings"] is settings
        assert dispatcher.workflow_data["statistics"] is statistics
        assert dispatcher.workflow_data["system"] is system
        root = dispatcher.sub_routers[0]
        assert {router.name for router in root.sub_routers} == {
            "main",
            "create_order",
            "orders",
            "customers",
            "settings",
            "statistics",
            "fallback",
        }

        await bot.session.close()

    asyncio.run(exercise())
