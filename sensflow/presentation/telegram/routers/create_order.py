"""Create Order FSM shell with all business work delegated."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import CreateOrderCommand, PrepareCreateOrderCommand
from sensflow.application.dto import PlaceIDSelectionDTO
from sensflow.application.errors import (
    ApplicationError,
    FeatureUnavailableError,
    InputValidationError,
    RobloxIntegrationError,
)
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
    PlaceCallback,
    PlaceCallbackAction,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.formatting import escape_text
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import (
    Screen,
    render_draft_created,
    render_main_menu,
    render_order_card,
    render_place_lookup_fallback,
    render_public_places,
    render_remembered_place,
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
    orders: OrderUseCases,
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
    await _load_place_selection(message, state, orders, command, refresh=False)


async def _load_place_selection(
    event: Message | CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
    command: PrepareCreateOrderCommand,
    *,
    refresh: bool,
) -> None:
    try:
        selection = (
            await orders.refresh_public_places(command)
            if refresh
            else await orders.prepare_create_order(command)
        )
    except (FeatureUnavailableError, RobloxIntegrationError):
        await state.set_state(CreateOrderStates.place_selection)
        await show_screen(
            event,
            render_place_lookup_fallback(
                "Public places could not be loaded. You can retry or enter a Place ID manually."
            ),
        )
        return
    except ApplicationError as error:
        await show_error(event, error)
        return
    await _show_place_selection(event, state, selection)


async def _show_place_selection(
    event: Message | CallbackQuery,
    state: FSMContext,
    selection: PlaceIDSelectionDTO,
) -> None:
    await state.update_data(
        username=selection.username,
        requested_robux=selection.requested_robux,
        roblox_user_id=selection.roblox_user_id,
        remembered_place=(
            None
            if selection.remembered_place is None
            else {
                "place_id": selection.remembered_place.place_id,
                "place_name": selection.remembered_place.place_name,
            }
        ),
        public_places=[
            {
                "place_id": place.place_id,
                "place_name": place.place_name,
            }
            for place in selection.public_places
        ],
    )
    if selection.remembered_place is not None:
        await state.set_state(CreateOrderStates.place_selection)
        await show_screen(event, render_remembered_place(selection))
    elif selection.public_places:
        await state.set_state(CreateOrderStates.place_selection)
        await show_screen(event, render_public_places(selection))
    else:
        await state.set_state(CreateOrderStates.manual_place_id)
        await show_screen(
            event,
            Screen(
                text=(
                    "<b>No public places found.</b>\n\nPlease enter the Roblox Place ID manually."
                ),
                reply_markup=navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER),
            ),
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
    CreateOrderStates.place_selection,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
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
    CreateOrderStates.place_selection,
    PlaceCallback.filter(F.action == PlaceCallbackAction.ENTER_MANUALLY),
)
async def enter_place_id_manually(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(CreateOrderStates.manual_place_id)
    await show_screen(callback, _place_id_prompt())


@router.callback_query(
    CreateOrderStates.place_selection,
    PlaceCallback.filter(
        F.action.in_({PlaceCallbackAction.CHOOSE_PUBLIC, PlaceCallbackAction.REFRESH})
    ),
)
async def refresh_public_places(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    try:
        command = validate_input(
            PrepareCreateOrderCommand,
            {
                "username": data.get("username"),
                "requested_robux": data.get("requested_robux"),
            },
        )
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await _load_place_selection(callback, state, orders, command, refresh=True)


@router.callback_query(
    CreateOrderStates.place_selection,
    PlaceCallback.filter(F.action == PlaceCallbackAction.USE_REMEMBERED),
)
async def use_remembered_place(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    remembered = data.get("remembered_place")
    if not isinstance(remembered, dict):
        await show_error(callback, InputValidationError(("remembered_place: missing",)))
        return
    await _continue_with_place(
        callback,
        state,
        orders,
        place_id=remembered.get("place_id"),
        place_name=remembered.get("place_name"),
    )


@router.callback_query(
    CreateOrderStates.place_selection,
    PlaceCallback.filter(F.action == PlaceCallbackAction.SELECT),
)
async def select_public_place(
    callback: CallbackQuery,
    callback_data: PlaceCallback,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    places = data.get("public_places")
    if (
        not isinstance(places, list)
        or callback_data.index < 0
        or callback_data.index >= len(places)
        or not isinstance(places[callback_data.index], dict)
    ):
        await show_error(callback, InputValidationError(("place: invalid selection",)))
        return
    place = places[callback_data.index]
    await _continue_with_place(
        callback,
        state,
        orders,
        place_id=place.get("place_id"),
        place_name=place.get("place_name"),
    )


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

    await _continue_with_place(
        message,
        state,
        orders,
        place_id=query.place_id,
        place_name="Manual Place",
    )


async def _continue_with_place(
    event: Message | CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
    *,
    place_id: object,
    place_name: object,
) -> None:
    data = await state.get_data()
    try:
        query = validate_input(
            FindSimilarOrderQuery,
            {
                "username": data.get("username"),
                "requested_robux": data.get("requested_robux"),
                "place_id": place_id,
            },
        )
        similar = await orders.find_similar_order(query)
    except ApplicationError as error:
        await show_error(event, error)
        return
    await state.update_data(
        place_id=query.place_id,
        place_name=place_name if isinstance(place_name, str) else "Manual Place",
    )
    if similar is not None:
        await state.set_state(CreateOrderStates.duplicate_confirmation)
        await state.update_data(similar_order_id=str(similar.id))
        await show_screen(event, render_similar_order(similar))
        return
    await _create_draft(event, state, orders, allow_duplicate=False)


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
                "place_name": data.get("place_name", "Manual Place"),
                "roblox_user_id": data.get("roblox_user_id"),
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
