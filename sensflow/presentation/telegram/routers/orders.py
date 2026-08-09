"""Client Order list, search, details, timeline, and action handlers."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import EditDraftCommand, OrderActionCommand
from sensflow.application.errors import ApplicationError, InputValidationError
from sensflow.application.ports import OrderUseCases
from sensflow.application.queries import GetOrderQuery, ListOrdersQuery, SearchOrdersQuery
from sensflow.application.validation import validate_input, validate_positive_integer
from sensflow.domain.enums import ClientOrderStatus
from sensflow.presentation.telegram.callbacks import (
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    OrderCallback,
    OrderCallbackAction,
    PageCallback,
    PageScope,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import (
    Screen,
    render_action_result,
    render_main_menu,
    render_order_card,
    render_order_details,
    render_order_list,
    render_order_search_prompt,
    render_order_search_results,
    render_orders_menu,
    show_screen,
)
from sensflow.presentation.telegram.states import DraftEditStates, OrderSearchStates

router = Router(name="orders")


async def _show_orders_menu(callback: CallbackQuery, orders: OrderUseCases) -> None:
    counts = await orders.get_status_counts()
    await show_screen(callback, render_orders_menu(counts))


async def _show_status_page(
    callback: CallbackQuery,
    orders: OrderUseCases,
    status: ClientOrderStatus,
) -> None:
    page = await orders.list_orders(ListOrdersQuery(status=status))
    await show_screen(callback, render_order_list(page, status))


@router.callback_query(MenuCallback.filter(F.section == MainSection.ACTIVE_ORDERS))
async def show_active_orders(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    await state.clear()
    await _show_status_page(callback, orders, ClientOrderStatus.PURCHASING)


@router.callback_query(MenuCallback.filter(F.section == MainSection.PREORDERS))
async def show_preorders(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    await state.clear()
    await _show_status_page(callback, orders, ClientOrderStatus.PREORDER)


@router.callback_query(MenuCallback.filter(F.section == MainSection.ORDERS))
@router.callback_query(
    NavigationCallback.filter(
        (F.target == NavigationTarget.ORDERS)
        & ((F.action == NavigationAction.BACK) | (F.action == NavigationAction.REFRESH))
    )
)
async def show_orders_menu(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    await state.clear()
    await _show_orders_menu(callback, orders)


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.LIST))
async def show_order_status_page(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    if callback_data.status is None:
        await show_error(callback, InputValidationError(("status: missing",)))
        return
    await state.clear()
    await _show_status_page(callback, orders, callback_data.status)


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.SEARCH))
async def begin_order_search(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(OrderSearchStates.query)
    await show_screen(callback, render_order_search_prompt())


@router.callback_query(
    OrderSearchStates.query,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_order_search(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    await state.clear()
    await _show_orders_menu(callback, orders)


@router.message(OrderSearchStates.query)
async def receive_order_search(
    message: Message,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    try:
        query = validate_input(SearchOrdersQuery, {"search_term": message.text})
        page = await orders.search_orders(query)
    except ApplicationError as error:
        await show_error(message, error)
        return
    await state.update_data(order_search_term=query.search_term)
    await show_screen(message, render_order_search_results(page))


@router.callback_query(PageCallback.filter(F.scope == PageScope.ORDERS))
async def paginate_orders(
    callback: CallbackQuery,
    callback_data: PageCallback,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    try:
        if callback_data.key == "search":
            data = await state.get_data()
            query = validate_input(
                SearchOrdersQuery,
                {
                    "search_term": data.get("order_search_term"),
                    "page": callback_data.page,
                },
            )
            page = await orders.search_orders(query)
            screen = render_order_search_results(page)
        else:
            status = ClientOrderStatus(callback_data.key)
            query = ListOrdersQuery(status=status, page=callback_data.page)
            page = await orders.list_orders(query)
            screen = render_order_list(page, status)
    except (ApplicationError, ValueError) as error:
        presentation_error = (
            error
            if isinstance(error, ApplicationError)
            else InputValidationError(("page: invalid callback",))
        )
        await show_error(callback, presentation_error)
        return
    await show_screen(callback, screen)


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.DETAILS))
async def show_order_details(
    callback: CallbackQuery,
    callback_data: OrderCallback,
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
    await show_screen(callback, render_order_card(order))


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.TIMELINE))
async def show_order_timeline(
    callback: CallbackQuery,
    callback_data: OrderCallback,
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
    await show_screen(callback, render_order_details(order))


@router.callback_query(OrderCallback.filter(F.action == OrderCallbackAction.EDIT_DRAFT))
async def begin_draft_edit(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback_data.order_id is None:
        await show_error(callback, InputValidationError(("order_id: missing",)))
        return
    await state.set_state(DraftEditStates.requested_robux)
    await state.update_data(edit_order_id=str(callback_data.order_id))
    await show_screen(
        callback,
        Screen(
            text="Send the new Requested Robux, or <code>-</code> to keep it unchanged.",
            reply_markup=navigation_keyboard(back_target=NavigationTarget.ORDER_EDIT),
        ),
    )


@router.message(DraftEditStates.requested_robux)
async def receive_draft_robux(message: Message, state: FSMContext) -> None:
    raw_value = message.text.strip() if message.text else ""
    try:
        requested_robux = (
            None if raw_value == "-" else validate_positive_integer(raw_value, "requested_robux")
        )
    except ApplicationError as error:
        await show_error(message, error)
        return
    await state.update_data(edit_requested_robux=requested_robux)
    await state.set_state(DraftEditStates.place_id)
    await show_screen(
        message,
        Screen(
            text="Send the new Place ID, or <code>-</code> to keep it unchanged.",
            reply_markup=navigation_keyboard(back_target=NavigationTarget.ORDER_EDIT),
        ),
    )


@router.callback_query(
    DraftEditStates.requested_robux,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_draft_amount(
    callback: CallbackQuery,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    order_id = data.get("edit_order_id")
    await state.clear()
    if order_id is None:
        await show_screen(callback, render_main_menu())
        return
    order = await orders.get_order(GetOrderQuery(order_id=order_id))
    await show_screen(callback, render_order_card(order))


@router.callback_query(
    DraftEditStates.place_id,
    NavigationCallback.filter(F.action == NavigationAction.BACK),
)
async def back_from_draft_place_id(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(DraftEditStates.requested_robux)
    await show_screen(
        callback,
        Screen(
            text="Send the new Requested Robux, or <code>-</code> to keep it unchanged.",
            reply_markup=navigation_keyboard(back_target=NavigationTarget.ORDER_EDIT),
        ),
    )


@router.message(DraftEditStates.place_id)
async def receive_draft_place_id(
    message: Message,
    state: FSMContext,
    orders: OrderUseCases,
) -> None:
    data = await state.get_data()
    raw_value = message.text.strip() if message.text else ""
    try:
        place_id = None if raw_value == "-" else validate_positive_integer(raw_value, "place_id")
        command = validate_input(
            EditDraftCommand,
            {
                "operator_id": message.from_user.id if message.from_user else None,
                "order_id": data.get("edit_order_id"),
                "requested_robux": data.get("edit_requested_robux"),
                "place_id": place_id,
            },
        )
        result = await orders.edit_draft(command)
    except ApplicationError as error:
        await state.clear()
        await show_error(message, error)
        return
    await state.clear()
    await show_screen(message, render_action_result(result))


@router.callback_query(
    OrderCallback.filter(
        F.action.in_(
            {
                OrderCallbackAction.CONFIRM_PAYMENT,
                OrderCallbackAction.DELETE_DRAFT,
                OrderCallbackAction.START_PURCHASE,
                OrderCallbackAction.MANUAL_REORDER,
                OrderCallbackAction.TOGGLE_AUTO_REQUEUE,
                OrderCallbackAction.CANCEL,
                OrderCallbackAction.FORCE_CLOSE,
                OrderCallbackAction.REFRESH,
                OrderCallbackAction.REPEAT,
            }
        )
    )
)
async def handle_order_action(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    orders: OrderUseCases,
) -> None:
    await callback.answer()
    if callback_data.order_id is None:
        await show_error(callback, InputValidationError(("order_id: missing",)))
        return
    command = OrderActionCommand(
        order_id=callback_data.order_id,
        operator_id=callback.from_user.id,
    )
    use_cases = {
        OrderCallbackAction.CONFIRM_PAYMENT: orders.confirm_payment,
        OrderCallbackAction.DELETE_DRAFT: orders.delete_draft,
        OrderCallbackAction.START_PURCHASE: orders.start_purchase,
        OrderCallbackAction.MANUAL_REORDER: orders.manual_reorder,
        OrderCallbackAction.TOGGLE_AUTO_REQUEUE: orders.toggle_auto_requeue,
        OrderCallbackAction.CANCEL: orders.cancel_order,
        OrderCallbackAction.FORCE_CLOSE: orders.force_close_order,
        OrderCallbackAction.REFRESH: orders.refresh_order,
        OrderCallbackAction.REPEAT: orders.repeat_order,
    }
    try:
        result = await use_cases[callback_data.action](command)
        order = await orders.get_order(
            GetOrderQuery(order_id=result.order_id or callback_data.order_id)
        )
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_order_card(order, result.message))
