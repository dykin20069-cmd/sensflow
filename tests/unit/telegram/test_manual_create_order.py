"""Focused tests for the manual Create Order Telegram conversation."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from aiogram.types import CallbackQuery, Message, User

from sensflow.application.dto import (
    ActionResultDTO,
    OrderAction,
    OrderDetailDTO,
    PlaceIDSelectionDTO,
    PublicPlaceDTO,
    StockAvailabilityDTO,
)
from sensflow.application.errors import MarketplaceGamepassNotFoundError
from sensflow.domain.enums import ClientOrderStatus
from sensflow.presentation.telegram.callbacks import (
    PlaceCallback,
    PlaceCallbackAction,
    PurchaseMode,
    PurchaseModeCallback,
)
from sensflow.presentation.telegram.routers.create_order import (
    create_duplicate_order,
    receive_manual_place_id,
    receive_requested_robux,
    receive_username,
    select_public_place,
    select_purchase_mode,
    send_to_preorders,
    use_remembered_place,
)
from sensflow.presentation.telegram.states import CreateOrderStates


class MemoryState:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.current: object | None = None
        self.cleared = False

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **values: object) -> None:
        self.data.update(values)

    async def set_state(self, state: object) -> None:
        self.current = state

    async def clear(self) -> None:
        self.cleared = True
        self.data.clear()
        self.current = None


def telegram_message(text: str) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.from_user = User(id=42, is_bot=False, first_name="Operator")
    message.answer = AsyncMock()
    return message


def telegram_callback() -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = User(id=42, is_bot=False, first_name="Operator")
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    return callback


def draft_details(order_id: UUID) -> OrderDetailDTO:
    return OrderDetailDTO(
        id=order_id,
        customer_username="viki_show2010435",
        status=ClientOrderStatus.DRAFT,
        requested_robux=100,
        customer_receives=None,
        current_place_id=1_234_567_890,
        marketplace_rate_limit=Decimal("1.25"),
        marketplace_cost=None,
        marketplace_commission=None,
        final_cost_usd=None,
        final_cost_local_currency=None,
        created_at=datetime(2026, 8, 7, 12, 0, tzinfo=UTC),
        completed_at=None,
        timeline=(),
        available_actions=(
            OrderAction.CONFIRM_PAYMENT,
            OrderAction.EDIT_DRAFT,
            OrderAction.DELETE_DRAFT,
            OrderAction.TIMELINE,
        ),
    )


def preorder_details(order_id: UUID) -> OrderDetailDTO:
    return replace(
        draft_details(order_id),
        status=ClientOrderStatus.PREORDER,
        available_actions=(OrderAction.START_PURCHASE, OrderAction.CANCEL, OrderAction.TIMELINE),
    )


def purchasing_details(order_id: UUID) -> OrderDetailDTO:
    return replace(
        draft_details(order_id),
        status=ClientOrderStatus.PURCHASING,
        available_actions=(OrderAction.MANUAL_REORDER, OrderAction.CANCEL, OrderAction.TIMELINE),
    )


def test_manual_create_order_offers_and_creates_preorder_when_stock_is_unavailable() -> None:
    async def scenario() -> None:
        state = MemoryState()
        orders = MagicMock()
        settings = MagicMock()
        settings.get_settings = AsyncMock(return_value=SimpleNamespace(preferred_mode_default=True))
        order_id = uuid4()
        orders.prepare_create_order = AsyncMock(
            return_value=PlaceIDSelectionDTO(
                username="viki_show2010435",
                requested_robux=100,
            )
        )
        orders.find_similar_order = AsyncMock(return_value=None)
        orders.check_stock = AsyncMock(
            return_value=StockAvailabilityDTO(
                available=False,
                maximum_purchase_rate=Decimal("4.5"),
            )
        )
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(
                message=f"Draft order {order_id} was created.",
                order_id=order_id,
            )
        )
        orders.send_to_preorder = AsyncMock(
            return_value=ActionResultDTO(message="PreOrder created.", order_id=order_id)
        )
        orders.get_order = AsyncMock(return_value=preorder_details(order_id))
        username_message = telegram_message("viki_show2010435")
        amount_message = telegram_message("100")
        place_message = telegram_message("1234567890")

        await receive_username(username_message, state)  # type: ignore[arg-type]
        await receive_requested_robux(amount_message, state, settings)  # type: ignore[arg-type]

        assert state.current == CreateOrderStates.purchase_mode
        mode_labels = [
            button.text
            for row in amount_message.answer.await_args.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        assert "⚡ Quick" in mode_labels
        assert "⏳ Preferred" in mode_labels

        mode_callback = telegram_callback()
        await select_purchase_mode(
            mode_callback,
            PurchaseModeCallback(mode=PurchaseMode.PREFERRED),
            state,  # type: ignore[arg-type]
            orders,
        )

        assert state.current == CreateOrderStates.manual_place_id
        place_screen = mode_callback.message.edit_text.await_args.args[0]
        assert "No public places found" in place_screen
        assert "enter the Roblox Place ID manually" in place_screen

        await receive_manual_place_id(
            place_message,
            state,  # type: ignore[arg-type]
            orders,
        )

        assert state.current == CreateOrderStates.stock_unavailable
        assert state.cleared is False
        orders.create_order.assert_not_awaited()
        no_stock_text = place_message.answer.await_args.args[0]
        no_stock_markup = place_message.answer.await_args.kwargs["reply_markup"]
        assert "No suitable stock available" in no_stock_text
        assert "Requested: 100 R$" in no_stock_text
        assert "Current limit: ≤ 4.5$" in no_stock_text
        assert "📦 Send to PreOrders" in [
            button.text for row in no_stock_markup.inline_keyboard for button in row
        ]

        callback = telegram_callback()
        await send_to_preorders(callback, state, orders)  # type: ignore[arg-type]

        command = orders.create_order.await_args.args[0]
        assert command.username == "viki_show2010435"
        assert command.requested_robux == 100
        assert command.place_id == 1_234_567_890
        assert command.operator_id == 42
        assert command.preferred_mode_enabled is True
        orders.prepare_create_order.assert_awaited_once()
        orders.send_to_preorder.assert_awaited_once()
        orders.get_order.assert_awaited_once()
        assert state.cleared is True

        text = callback.message.edit_text.await_args.args[0]
        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        assert "PreOrder created" in text
        assert "viki_show2010435" in text
        assert "100 R$" in text
        assert "1234567890" in text
        labels = [button.text for row in markup.inline_keyboard for button in row]
        assert "📦 Retry Stock Check" in labels
        assert "❌ Cancel" in labels

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid_place_id",
    ["not-a-place-id", "0", "-1", "42.0", str(2**63)],
)
def test_invalid_manual_place_id_keeps_conversation_open(invalid_place_id: str) -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {"username": "viki_show2010435", "requested_robux": 100}
        state.current = CreateOrderStates.manual_place_id
        orders = MagicMock()
        orders.create_order = AsyncMock()
        orders.find_similar_order = AsyncMock(return_value=None)
        message = telegram_message(invalid_place_id)

        await receive_manual_place_id(
            message,
            state,  # type: ignore[arg-type]
            orders,
        )

        orders.create_order.assert_not_awaited()
        assert state.current == CreateOrderStates.manual_place_id
        assert state.cleared is False
        assert message.answer.await_args.args[0] == (
            "Invalid Place ID. Send a positive numeric Roblox Place ID."
        )

    asyncio.run(scenario())


def test_similar_order_requires_explicit_reuse_or_duplicate_choice() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {"username": "viki_show2010435", "requested_robux": 100}
        state.current = CreateOrderStates.manual_place_id
        existing = replace(
            draft_details(uuid4()),
            status=ClientOrderStatus.PREORDER,
        )
        orders = MagicMock()
        orders.find_similar_order = AsyncMock(return_value=existing)
        orders.create_order = AsyncMock()
        message = telegram_message("1234567890")

        await receive_manual_place_id(message, state, orders)  # type: ignore[arg-type]

        assert state.current == CreateOrderStates.duplicate_confirmation
        orders.create_order.assert_not_awaited()
        assert "Similar order already exists" in message.answer.await_args.args[0]

    asyncio.run(scenario())


def test_create_another_sets_explicit_duplicate_override() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {
            "username": "viki_show2010435",
            "requested_robux": 100,
            "place_id": 1_234_567_890,
        }
        state.current = CreateOrderStates.duplicate_confirmation
        order_id = uuid4()
        orders = MagicMock()
        orders.check_stock = AsyncMock(return_value=StockAvailabilityDTO(True, Decimal("4.5")))
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(message="created", order_id=order_id)
        )
        orders.start_purchase = AsyncMock(
            return_value=ActionResultDTO(message="Purchase started.", order_id=order_id)
        )
        orders.get_order = AsyncMock(return_value=purchasing_details(order_id))
        callback = telegram_callback()

        await create_duplicate_order(callback, state, orders)  # type: ignore[arg-type]

        command = orders.create_order.await_args.args[0]
        assert command.allow_duplicate is True
        assert state.cleared is True
        assert "Active Order" in callback.message.edit_text.await_args.args[0]

    asyncio.run(scenario())


def test_public_place_selection_creates_verified_purchase() -> None:
    async def scenario() -> None:
        state = MemoryState()
        order_id = uuid4()
        orders = MagicMock()
        settings = MagicMock()
        settings.get_settings = AsyncMock(
            return_value=SimpleNamespace(preferred_mode_default=False)
        )
        orders.prepare_create_order = AsyncMock(
            return_value=PlaceIDSelectionDTO(
                username="VerifiedUser",
                requested_robux=100,
                roblox_user_id=42,
                public_places=(
                    PublicPlaceDTO(
                        place_id=1_234_567_890,
                        universe_id=999,
                        place_name="My Tycoon",
                        visits=1_200_000,
                        updated_at=datetime(2026, 8, 7, tzinfo=UTC),
                    ),
                ),
            )
        )
        orders.find_similar_order = AsyncMock(return_value=None)
        orders.check_stock = AsyncMock(return_value=StockAvailabilityDTO(True, Decimal("4.5")))
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(message="created", order_id=order_id)
        )
        orders.start_purchase = AsyncMock(
            return_value=ActionResultDTO(
                message=(
                    "⚠️ Товар временно оформлен как предзаказ. Выдача произойдёт "
                    "автоматически после появления свободного аккаунта поставщика."
                ),
                order_id=order_id,
            )
        )
        orders.get_order = AsyncMock(
            return_value=replace(
                purchasing_details(order_id),
                preferred_mode_enabled=False,
                preferred_rate=None,
                preferred_timeout_minutes=None,
                fallback_active=True,
            )
        )

        await receive_username(telegram_message("verifieduser"), state)  # type: ignore[arg-type]
        amount = telegram_message("100")
        await receive_requested_robux(amount, state, settings)  # type: ignore[arg-type]

        assert state.current == CreateOrderStates.purchase_mode
        mode_callback = telegram_callback()
        await select_purchase_mode(
            mode_callback,
            PurchaseModeCallback(mode=PurchaseMode.QUICK),
            state,  # type: ignore[arg-type]
            orders,
        )

        assert state.current == CreateOrderStates.place_selection
        assert (
            "Public places for VerifiedUser" in mode_callback.message.edit_text.await_args.args[0]
        )
        assert "1.2M visits" in mode_callback.message.edit_text.await_args.args[0]

        callback = telegram_callback()
        await select_public_place(
            callback,
            PlaceCallback(action=PlaceCallbackAction.SELECT, index=0),
            state,  # type: ignore[arg-type]
            orders,
        )

        command = orders.create_order.await_args.args[0]
        assert command.username == "VerifiedUser"
        assert command.roblox_user_id == 42
        assert command.place_id == 1_234_567_890
        assert command.place_name == "My Tycoon"
        assert command.preferred_mode_enabled is False
        rendered = callback.message.edit_text.await_args.args[0]
        assert "Active Order" in rendered
        assert "⚡ Preferred: disabled" in rendered
        assert "🚀 Immediate execution allowed" in rendered
        assert "временно оформлен как предзаказ" in rendered

    asyncio.run(scenario())


def test_quick_public_place_404_shows_specific_gamepass_guidance() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.current = CreateOrderStates.place_selection
        state.data = {
            "username": "VerifiedUser",
            "requested_robux": 100,
            "roblox_user_id": 42,
            "preferred_mode_enabled": False,
            "public_places": [
                {
                    "place_id": 1_234_567_890,
                    "place_name": "My Tycoon",
                }
            ],
        }
        order_id = uuid4()
        orders = MagicMock()
        orders.find_similar_order = AsyncMock(return_value=None)
        orders.check_stock = AsyncMock(return_value=StockAvailabilityDTO(True, Decimal("4.5")))
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(message="created", order_id=order_id)
        )
        orders.start_purchase = AsyncMock(
            side_effect=MarketplaceGamepassNotFoundError(
                "❌ Для выбранной игры не удалось автоматически найти подходящий gamepass.\n"
                "Попробуйте:\n"
                "• выбрать другой плейс,\n"
                "• или использовать режим \u0441 ручным gamepass ID."
            )
        )
        orders.get_order = AsyncMock()
        callback = telegram_callback()

        await select_public_place(
            callback,
            PlaceCallback(action=PlaceCallbackAction.SELECT, index=0),
            state,  # type: ignore[arg-type]
            orders,
        )

        rendered = callback.message.edit_text.await_args.args[0]
        assert "Для выбранной игры не удалось" in rendered
        assert "выбрать другой плейс" in rendered
        assert "ручным gamepass ID" in rendered
        assert "The action could not be completed" not in rendered
        assert state.cleared is False
        orders.get_order.assert_not_awaited()

    asyncio.run(scenario())


def test_remembered_place_has_priority_and_starts_purchase_in_one_tap() -> None:
    async def scenario() -> None:
        state = MemoryState()
        state.data = {
            "username": "viki_show2010435",
            "requested_robux": 100,
            "remembered_place": {
                "place_id": 1_234_567_890,
                "place_name": "My Tycoon",
            },
        }
        state.current = CreateOrderStates.place_selection
        order_id = uuid4()
        orders = MagicMock()
        orders.find_similar_order = AsyncMock(return_value=None)
        orders.check_stock = AsyncMock(return_value=StockAvailabilityDTO(True, Decimal("4.5")))
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(message="created", order_id=order_id)
        )
        orders.start_purchase = AsyncMock(
            return_value=ActionResultDTO(message="Purchase started.", order_id=order_id)
        )
        orders.get_order = AsyncMock(return_value=purchasing_details(order_id))
        callback = telegram_callback()

        await use_remembered_place(callback, state, orders)  # type: ignore[arg-type]

        command = orders.create_order.await_args.args[0]
        assert command.place_id == 1_234_567_890
        assert command.place_name == "My Tycoon"
        assert state.cleared is True

    asyncio.run(scenario())
