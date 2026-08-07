"""Create Order FSM shell with all business work delegated."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import CreateOrderCommand, PrepareCreateOrderCommand
from sensflow.application.errors import ApplicationError, InputValidationError
from sensflow.application.ports import OrderUseCases
from sensflow.application.validation import (
    validate_input,
    validate_positive_integer,
    validate_username,
)
from sensflow.presentation.telegram.callbacks import (
    MainSection,
    MenuCallback,
    OrderCallback,
    OrderCallbackAction,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.formatting import escape_text
from sensflow.presentation.telegram.keyboards import navigation_keyboard, place_id_choice_keyboard
from sensflow.presentation.telegram.rendering import Screen, render_action_result, show_screen
from sensflow.presentation.telegram.states import CreateOrderStates

router = Router(name="create_order")


@router.callback_query(MenuCallback.filter(F.section == MainSection.CREATE_ORDER))
async def begin_create_order(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(CreateOrderStates.username)
    await show_screen(
        callback,
        Screen(
            text="<b>Create Order</b>\n\nSend the Roblox username.",
            reply_markup=navigation_keyboard(),
        ),
    )


@router.message(CreateOrderStates.username)
async def receive_username(message: Message, state: FSMContext) -> None:
    try:
        username = validate_username(message.text)
    except InputValidationError as error:
        await show_error(message, error)
        return
    await state.update_data(username=username)
    await state.set_state(CreateOrderStates.requested_robux)
    await show_screen(
        message,
        Screen(
            text=f"Username: <b>{escape_text(username)}</b>\n\nSend the Requested Robux amount.",
            reply_markup=navigation_keyboard(),
        ),
    )


@router.message(CreateOrderStates.requested_robux)
async def receive_requested_robux(
    message: Message,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    data = await state.get_data()
    try:
        requested_robux = validate_positive_integer(message.text, "requested_robux")
        command = validate_input(
            PrepareCreateOrderCommand,
            {"username": data.get("username"), "requested_robux": requested_robux},
        )
        selection = await orders.prepare_create_order(command)
    except ApplicationError as error:
        await show_error(message, error)
        return
    await state.update_data(
        requested_robux=requested_robux,
        discovered_place_id=selection.discovered_place_id,
    )
    if selection.discovered_place_id is None:
        await state.set_state(CreateOrderStates.manual_place_id)
        await show_screen(
            message,
            Screen(
                text="No Place ID was discovered. Send the Place ID manually.",
                reply_markup=navigation_keyboard(),
            ),
        )
        return
    await state.set_state(CreateOrderStates.place_id_confirmation)
    await show_screen(
        message,
        Screen(
            text=f"Discovered Place ID: <code>{selection.discovered_place_id}</code>",
            reply_markup=place_id_choice_keyboard(),
        ),
    )


@router.callback_query(
    CreateOrderStates.place_id_confirmation,
    OrderCallback.filter(F.action == OrderCallbackAction.ENTER_PLACE_ID),
)
async def request_manual_place_id(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(CreateOrderStates.manual_place_id)
    await show_screen(
        callback,
        Screen(text="Send the Place ID manually.", reply_markup=navigation_keyboard()),
    )


@router.callback_query(
    CreateOrderStates.place_id_confirmation,
    OrderCallback.filter(F.action == OrderCallbackAction.CONFIRM_PLACE_ID),
)
async def confirm_discovered_place_id(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    try:
        command = validate_input(
            CreateOrderCommand,
            {
                "username": data.get("username"),
                "requested_robux": data.get("requested_robux"),
                "place_id": data.get("discovered_place_id"),
                "operator_id": callback.from_user.id,
            },
        )
        await state.clear()
        result = await orders.create_order(command)
    except ApplicationError as error:
        await state.clear()
        await show_error(callback, error)
        return
    await show_screen(callback, render_action_result(result))


@router.message(CreateOrderStates.manual_place_id)
async def receive_manual_place_id(
    message: Message,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    data = await state.get_data()
    try:
        place_id = validate_positive_integer(message.text, "place_id")
        command = validate_input(
            CreateOrderCommand,
            {
                "username": data.get("username"),
                "requested_robux": data.get("requested_robux"),
                "place_id": place_id,
                "operator_id": message.from_user.id if message.from_user else None,
            },
        )
        await state.clear()
        result = await orders.create_order(command)
    except ApplicationError as error:
        await state.clear()
        await show_error(message, error)
        return
    await show_screen(message, render_action_result(result))
