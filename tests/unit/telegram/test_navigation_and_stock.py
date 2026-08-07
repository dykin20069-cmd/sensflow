"""Regression coverage for production navigation and stock refresh UX."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Message, User

from sensflow.application.dto import CurrentStockDTO, MarketplaceStockDTO
from sensflow.presentation.telegram.callbacks import (
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
)
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import render_current_stock
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
        ),
        maximum_purchase_rate=Decimal("4.5"),
        preferred_rate=Decimal("4.3"),
        updated_at=datetime(2026, 8, 7, 14, 54, 12, tzinfo=UTC),
    )


def test_stock_rendering_formats_rate_tiers_and_policy() -> None:
    screen = render_current_stock(stock_snapshot())

    assert "🟢 4.2$ — 1,325 R$ available" in screen.text
    assert "🟢 4.3$ — 9,071 R$ available" in screen.text
    assert "🟡 4.5$ — 367 R$ available" in screen.text
    assert "🔴 4.8$ — 100 R$ ignored" in screen.text
    assert "Total available within limit: 10,763 R$" in screen.text
    assert "Maximum instant order: 427 R$" in screen.text
    assert "Current limit: ≤ 4.5$" in screen.text
    assert "Updated: 14:54:12 UTC" in screen.text


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


def test_back_returns_place_id_step_to_amount_step() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {"username": "builder", "requested_robux": 100}
        state.current = CreateOrderStates.manual_place_id
        callback = callback_event()

        await back_from_place_id(callback, state)  # type: ignore[arg-type]

        assert state.current == CreateOrderStates.requested_robux
        assert "Requested Robux amount" in callback.message.edit_text.await_args.args[0]

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
