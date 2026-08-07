"""Create Order FSM shell with all business work delegated."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import CreateOrderCommand, PrepareCreateOrderCommand
from sensflow.application.errors import ApplicationError, InputValidationError
from sensflow.application.ports import OrderUseCases
from sensflow.application.queries import FindSimilarOrderQuery, GetOrderQuery
from sensflow.application.validation import (
    validate_input,
    validate_positive_integer,
    validate_username,
)
from sensflow.presentation.telegram.callbacks import (
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    OrderCallback,
    OrderCallbackAction,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.formatting import escape_text
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import (
    Screen,
    render_draft_created,
    render_main_menu,
    render_order_card,
    render_similar_order,
    show_screen,
)
from sensflow.presentation.telegram.states import CreateOrderStates

router = Router(name="create_order")


def _username_prompt() -> Screen:
    return Screen(
        text="<b>Create Order</b>\n\nSend the Roblox username.",
        reply_markup=navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER),
    )


def _amount_prompt(username: str) -> Screen:
    return Screen(
        text=(f"Username: <b>{escape_text(username)}</b>\n\nSend the Requested Robux amount."),
        reply_markup=navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER),
    )


def _place_id_prompt() -> Screen:
    return Screen(
        text=(
            "Send the Roblox Place ID.\n\n"
            "You can copy it from the game URL:\n"
            "https://www.roblox.com/games/PLACE_ID/..."
        ),
        reply_markup=navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER),
    )


@router.callback_query(MenuCallback.filter(F.section == MainSection.CREATE_ORDER))
async def begin_create_order(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(CreateOrderStates.username)
    await show_screen(
        callback,
        _username_prompt(),
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
        _amount_prompt(username),
    )


@router.message(CreateOrderStates.requested_robux)
async def receive_requested_robux(
    message: Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    try:
        requested_robux = validate_positive_integer(message.text, "requested_robux")
        command = validate_input(
            PrepareCreateOrderCommand,
            {"username": data.get("username"), "requested_robux": requested_robux},
        )
    except ApplicationError as error:
        await show_error(message, error)
        return
    await state.update_data(
        username=command.username,
        requested_robux=command.requested_robux,
    )
    await state.set_state(CreateOrderStates.manual_place_id)
    await show_screen(
        message,
        _place_id_prompt(),
    )


@router.callback_query(
    CreateOrderStates.username,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_username(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await show_screen(callback, render_main_menu())


@router.callback_query(
    CreateOrderStates.requested_robux,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_amount(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(CreateOrderStates.username)
    await show_screen(callback, _username_prompt())


@router.callback_query(
    CreateOrderStates.manual_place_id,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_place_id(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    username = str(data.get("username", ""))
    await state.set_state(CreateOrderStates.requested_robux)
    await show_screen(callback, _amount_prompt(username))


@router.callback_query(
    CreateOrderStates.duplicate_confirmation,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_duplicate_confirmation(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(CreateOrderStates.manual_place_id)
    await show_screen(callback, _place_id_prompt())


@router.message(CreateOrderStates.manual_place_id)
async def receive_manual_place_id(
    message: Message,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    data = await state.get_data()
    try:
        place_id = validate_positive_integer(message.text, "place_id")
        query = validate_input(
            FindSimilarOrderQuery,
            {
                "username": data.get("username"),
                "requested_robux": data.get("requested_robux"),
                "place_id": place_id,
            },
        )
    except InputValidationError:
        await show_screen(
            message,
            Screen(
                text="Invalid Place ID. Send a positive numeric Roblox Place ID.",
                reply_markup=navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER),
            ),
        )
        return

    try:
        similar = await orders.find_similar_order(query)
    except ApplicationError as error:
        await show_error(message, error)
        return
    await state.update_data(place_id=place_id)
    if similar is not None:
        await state.set_state(CreateOrderStates.duplicate_confirmation)
        await state.update_data(similar_order_id=str(similar.id))
        await show_screen(message, render_similar_order(similar))
        return
    await _create_draft(message, state, orders, allow_duplicate=False)


async def _create_draft(
    event: Message | CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
    *,
    allow_duplicate: bool,
) -> None:
    data = await state.get_data()
    try:
        command = validate_input(
            CreateOrderCommand,
            {
                "username": data.get("username"),
                "requested_robux": data.get("requested_robux"),
                "place_id": data.get("place_id"),
                "operator_id": event.from_user.id,
                "allow_duplicate": allow_duplicate,
            },
        )
        result = await orders.create_order(command)
        order = (
            None
            if result.order_id is None
            else await orders.get_order(GetOrderQuery(order_id=result.order_id))
        )
    except ApplicationError as error:
        await show_error(event, error)
        return
    await state.clear()
    if order is None:
        await show_screen(event, render_main_menu())
        return
    await show_screen(event, render_draft_created(order))


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.REUSE_SIMILAR))
async def reuse_similar_order(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    if callback_data.order_id is None:
        await show_error(callback, InputValidationError(("order_id: missing",)))
        return
    try:
        order = await orders.get_order(GetOrderQuery(order_id=callback_data.order_id))
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await state.clear()
    await show_screen(callback, render_order_card(order))


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.CREATE_DUPLICATE))
async def create_duplicate_order(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    await _create_draft(callback, state, orders, allow_duplicate=True)


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.ABORT_CREATE))
async def abort_create_order(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await show_screen(callback, render_main_menu())
