"""Regression coverage for production navigation and stock refresh UX."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from aiogram.types import CallbackQuery, Message, User

from sensflow.application.dto import (
    CurrentStockDTO,
    MarketplaceStockDTO,
    OrderAction,
    PageDTO,
)
from sensflow.domain.enums import ClientOrderStatus
from sensflow.presentation.telegram.callbacks import (
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
)
from sensflow.presentation.telegram.keyboards import navigation_keyboard, order_details_keyboard
from sensflow.presentation.telegram.rendering import render_current_stock, render_order_list
from sensflow.presentation.telegram.routers.create_order import (
    back_from_place_id,
    begin_create_order,
)
from sensflow.presentation.telegram.routers.main import (
    close_screen,
    navigate_home,
    show_current_stock,
    show_dashboard,
)
from sensflow.presentation.telegram.states import CreateOrderStates


class MemoryState:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.current: object | None = None
        self.cleared = False

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def set_state(self, state: object) -> None:
        self.current = state

    async def clear(self) -> None:
        self.data.clear()
        self.current = None
        self.cleared = True


def callback_event() -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = User(id=42, is_bot=False, first_name="Operator")
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.answer = AsyncMock()
    return callback


def stock_snapshot() -> CurrentStockDTO:
    return CurrentStockDTO(
        items=(
            MarketplaceStockDTO(Decimal("4.2"), 3, 427, 1325),
            MarketplaceStockDTO(Decimal("4.3"), 25, 338, 9071),
            MarketplaceStockDTO(Decimal("4.5"), 1, 257, 367),
            MarketplaceStockDTO(Decimal("4.8"), 1, 100, 100),
            MarketplaceStockDTO(Decimal("5.1"), 100, 50_000, 500_000),
        ),
        maximum_purchase_rate=Decimal("4.5"),
        preferred_rate=Decimal("4.3"),
        updated_at=datetime(2026, 8, 7, 14, 54, 12, tzinfo=UTC),
    )


def test_stock_rendering_formats_rate_tiers_and_policy() -> None:
    screen = render_current_stock(stock_snapshot())

    assert "🟢 4.2$ | 👥 3 | 💰 1,325 R$ | ⚡ 427 R$" in screen.text
    assert "🟢 4.3$ | 👥 25 | 💰 9,071 R$ | ⚡ 338 R$" in screen.text
    assert "🟡 4.5$ | 👥 1 | 💰 367 R$ | ⚡ 257 R$" in screen.text
    assert "🔴 4.8$ | 👥 1 | 💰 100 R$ | ⚡ 100 R$" in screen.text
    assert "5.1$" not in screen.text
    assert "Accounts:" not in screen.text
    assert "📦 Total within limit: 10,763 R$" in screen.text
    assert "⚡ Best instant order: 427 R$" in screen.text
    assert "🎯 Limit: ≤ 4.5$ | Preferred: ≤ 4.3$" in screen.text
    assert "🕒 17:54 MSK" in screen.text


def test_stock_rendering_places_cheapest_visible_level_last() -> None:
    stock = CurrentStockDTO(
        items=tuple(
            MarketplaceStockDTO(
                rate=Decimal(rate),
                accounts_count=1,
                max_instant_order=100,
                total_robux_amount=100,
            )
            for rate in ("3.9", "4.5", "4.8", "5.0")
        ),
        maximum_purchase_rate=Decimal("4.5"),
        preferred_rate=Decimal("4.3"),
        updated_at=datetime(2026, 8, 7, 22, 29, 49, tzinfo=UTC),
    )

    screen = render_current_stock(stock)
    rendered_rates = [
        line.split()[1] for line in screen.text.splitlines() if line.startswith(("🟢", "🟡", "🔴"))
    ]

    assert rendered_rates == ["5.0$", "4.8$", "4.5$", "3.9$"]


def test_stock_footer_excludes_hidden_levels_even_when_within_purchase_limit() -> None:
    stock = CurrentStockDTO(
        items=(
            MarketplaceStockDTO(Decimal("4.5"), 1, 70, 100),
            MarketplaceStockDTO(Decimal("5.1"), 1, 900, 1_000),
        ),
        maximum_purchase_rate=Decimal("5.5"),
        preferred_rate=Decimal("4.3"),
        updated_at=datetime(2026, 8, 7, 22, 29, 49, tzinfo=UTC),
    )

    screen = render_current_stock(stock)

    assert "5.1$" not in screen.text
    assert "📦 Total within limit: 100 R$" in screen.text
    assert "⚡ Best instant order: 70 R$" in screen.text


def test_stock_rendering_falls_back_to_five_cheapest_levels() -> None:
    stock = CurrentStockDTO(
        items=tuple(
            MarketplaceStockDTO(
                rate=Decimal(rate),
                accounts_count=1,
                max_instant_order=instant,
                total_robux_amount=available,
            )
            for rate, instant, available in (
                ("5.6", 10, 60),
                ("5.1", 44_745, 149_112),
                ("5.3", 13_436, 145_105),
                ("5.2", 115_690, 282_570),
                ("5.5", 20, 50),
                ("5.4", 30, 40),
            )
        ),
        maximum_purchase_rate=Decimal("4.5"),
        preferred_rate=Decimal("4.3"),
        updated_at=datetime(2026, 8, 7, 22, 19, 19, tzinfo=UTC),
    )

    screen = render_current_stock(stock)

    assert "⚠️ No offers up to 5.0$" in screen.text
    assert "🔴 5.1$ | 👥 1 | 💰 149,112 R$ | ⚡ 44,745 R$" in screen.text
    assert "🔴 5.2$ | 👥 1 | 💰 282,570 R$ | ⚡ 115,690 R$" in screen.text
    assert "🔴 5.3$ | 👥 1 | 💰 145,105 R$ | ⚡ 13,436 R$" in screen.text
    assert "🔴 5.4$ | 👥 1 | 💰 40 R$ | ⚡ 30 R$" in screen.text
    assert "🔴 5.5$ | 👥 1 | 💰 50 R$ | ⚡ 20 R$" in screen.text
    assert "5.6$" not in screen.text
    assert "Market currently above your viewing threshold." in screen.text
    assert "📦 Total within limit: 0 R$" in screen.text
    assert "⚡ Best instant order: 0 R$" in screen.text
    assert "🕒 01:19 MSK" in screen.text


def test_active_and_preorder_screens_expose_direct_production_actions() -> None:
    active_list = render_order_list(
        PageDTO(items=(), page=1, page_size=10, total_items=0),
        ClientOrderStatus.PURCHASING,
    )
    active_labels = [
        button.text for row in active_list.reply_markup.inline_keyboard for button in row
    ]
    assert "No orders in this status." in active_list.text
    assert "📦 View PreOrders" in active_labels

    preorder_keyboard = order_details_keyboard(
        uuid4(),
        ClientOrderStatus.PREORDER,
        (OrderAction.START_PURCHASE, OrderAction.FORCE_PURCHASE, OrderAction.FORCE_CLOSE),
    )
    preorder_labels = [button.text for row in preorder_keyboard.inline_keyboard for button in row]
    assert "📦 Retry Stock Check" in preorder_labels
    assert "🚀 Force Create Marketplace Order" in preorder_labels
    assert "🔒 Force Close" in preorder_labels

    active_keyboard = order_details_keyboard(
        uuid4(),
        ClientOrderStatus.PURCHASING,
        (
            OrderAction.MANUAL_REORDER,
            OrderAction.DISABLE_AUTO_REQUEUE,
            OrderAction.FORCE_CLOSE,
        ),
    )
    active_action_labels = [
        button.text for row in active_keyboard.inline_keyboard for button in row
    ]
    assert "🔄 Requeue Now" in active_action_labels
    assert "⏸ Disable Auto Requeue" in active_action_labels
    assert "🔒 Force Close" in active_action_labels

    cancelled_keyboard = order_details_keyboard(
        uuid4(),
        ClientOrderStatus.CANCELLED,
        (OrderAction.REPEAT, OrderAction.TIMELINE),
    )
    cancelled_labels = [button.text for row in cancelled_keyboard.inline_keyboard for button in row]
    assert "🔁 Repeat order" in cancelled_labels

    force_closed_keyboard = order_details_keyboard(
        uuid4(),
        ClientOrderStatus.FORCE_CLOSED,
        (OrderAction.TIMELINE,),
    )
    force_closed_labels = [
        button.text for row in force_closed_keyboard.inline_keyboard for button in row
    ]
    assert force_closed_labels == ["📋 Details", "⬅️ Back", "🏠 Home"]


def test_home_clears_state_and_close_deletes_the_screen() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {"username": "stale"}
        state.current = CreateOrderStates.manual_place_id
        home = callback_event()

        await navigate_home(home, state)  # type: ignore[arg-type]

        assert state.cleared is True
        home.message.delete.assert_awaited_once()
        assert "SensFlow Dashboard" in home.message.answer.await_args.args[0]

        create = callback_event()
        await begin_create_order(create, state)  # type: ignore[arg-type]
        assert state.current == CreateOrderStates.username
        assert "Send the Roblox username" in create.message.edit_text.await_args.args[0]

        state.cleared = False
        close = callback_event()
        await close_screen(close, state)  # type: ignore[arg-type]
        assert state.cleared is True
        close.message.delete.assert_awaited_once()
        assert "SensFlow Dashboard" in close.message.answer.await_args.args[0]

    asyncio.run(scenario())


def test_dashboard_reopens_cleanly_and_close_uses_previous_screen_when_known() -> None:
    async def scenario() -> None:
        state = MemoryState()
        callback = callback_event()

        await show_dashboard(callback, state)  # type: ignore[arg-type]

        callback.message.delete.assert_awaited_once()
        assert "SensFlow Dashboard" in callback.message.answer.await_args.args[0]

    asyncio.run(scenario())

    keyboard = navigation_keyboard(back_target=NavigationTarget.SETTINGS)
    close_button = next(
        button for row in keyboard.inline_keyboard for button in row if button.text == "❌ Close"
    )
    callback_data = NavigationCallback.unpack(close_button.callback_data or "")
    assert callback_data.action is NavigationAction.BACK
    assert callback_data.target is NavigationTarget.SETTINGS


def test_back_returns_place_id_step_to_purchase_mode_step() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {"username": "builder", "requested_robux": 100}
        state.current = CreateOrderStates.manual_place_id
        callback = callback_event()

        await back_from_place_id(callback, state)  # type: ignore[arg-type]

        assert state.current == CreateOrderStates.purchase_mode
        assert "Choose purchase mode" in callback.message.edit_text.await_args.args[0]

    asyncio.run(scenario())


def test_stock_refresh_fetches_again_and_edits_current_message() -> None:
    async def scenario() -> None:
        callback = callback_event()
        state = MemoryState()
        orders = MagicMock()
        orders.get_current_stock = AsyncMock(return_value=stock_snapshot())

        await show_current_stock(callback, state, orders)  # type: ignore[arg-type]

        orders.get_current_stock.assert_awaited_once()
        assert state.cleared is True
        assert "Current RBXCrate Stock" in callback.message.edit_text.await_args.args[0]

    asyncio.run(scenario())
