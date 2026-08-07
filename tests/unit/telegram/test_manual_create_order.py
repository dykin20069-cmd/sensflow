"""Focused tests for the manual Create Order Telegram conversation."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from aiogram.types import CallbackQuery, Message, User

from sensflow.application.dto import ActionResultDTO, OrderAction, OrderDetailDTO
from sensflow.domain.enums import ClientOrderStatus
from sensflow.presentation.telegram.routers.create_order import (
    create_duplicate_order,
    receive_manual_place_id,
    receive_requested_robux,
    receive_username,
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


def test_manual_create_order_conversation_creates_and_renders_draft() -> None:
    async def scenario() -> None:
        state = MemoryState()
        orders = MagicMock()
        order_id = uuid4()
        orders.prepare_create_order = AsyncMock()
        orders.find_similar_order = AsyncMock(return_value=None)
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(
                message=f"Draft order {order_id} was created.",
                order_id=order_id,
            )
        )
        orders.get_order = AsyncMock(return_value=draft_details(order_id))
        username_message = telegram_message("viki_show2010435")
        amount_message = telegram_message("100")
        place_message = telegram_message("1234567890")

        await receive_username(username_message, state)  # type: ignore[arg-type]
        await receive_requested_robux(amount_message, state)  # type: ignore[arg-type]

        assert state.current == CreateOrderStates.manual_place_id
        amount_screen = amount_message.answer.await_args.args[0]
        assert "Send the Roblox Place ID" in amount_screen
        assert "https://www.roblox.com/games/PLACE_ID/..." in amount_screen

        await receive_manual_place_id(
            place_message,
            state,  # type: ignore[arg-type]
            orders,
        )

        command = orders.create_order.await_args.args[0]
        assert command.username == "viki_show2010435"
        assert command.requested_robux == 100
        assert command.place_id == 1_234_567_890
        assert command.operator_id == 42
        orders.prepare_create_order.assert_not_awaited()
        orders.get_order.assert_awaited_once()
        assert state.cleared is True

        text = place_message.answer.await_args.args[0]
        markup = place_message.answer.await_args.kwargs["reply_markup"]
        assert "Draft Created" in text
        assert str(order_id) in text
        assert "viki_show2010435" in text
        assert "100 R$" in text
        assert "1234567890" in text
        assert "Status: Draft" in text
        labels = [button.text for row in markup.inline_keyboard for button in row]
        assert "Confirm Payment" in labels
        assert "Edit Draft" in labels
        assert "Delete Draft" in labels

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
        orders.create_order = AsyncMock(
            return_value=ActionResultDTO(message="created", order_id=order_id)
        )
        orders.get_order = AsyncMock(return_value=draft_details(order_id))
        callback = telegram_callback()

        await create_duplicate_order(callback, state, orders)  # type: ignore[arg-type]

        command = orders.create_order.await_args.args[0]
        assert command.allow_duplicate is True
        assert state.cleared is True
        assert "Draft Created" in callback.message.edit_text.await_args.args[0]

    asyncio.run(scenario())
