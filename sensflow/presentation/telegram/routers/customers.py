"""Customer search, details, and deferred action handlers."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import (
    ArchiveCustomerCommand,
    CustomerActionCommand,
    UpdatePlaceIDCommand,
)
from sensflow.application.errors import ApplicationError
from sensflow.application.ports import CustomerUseCases
from sensflow.application.queries import GetCustomerQuery, SearchCustomersQuery
from sensflow.application.validation import validate_input, validate_positive_integer
from sensflow.presentation.telegram.callbacks import (
    CustomerCallback,
    CustomerCallbackAction,
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    PageCallback,
    PageScope,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import (
    Screen,
    render_action_result,
    render_customer_details,
    render_customer_list,
    render_customer_search_prompt,
    show_screen,
)
from sensflow.presentation.telegram.states import CustomerPlaceIDStates, CustomerSearchStates

router = Router(name="customers")


@router.callback_query(MenuCallback.filter(F.section == MainSection.CUSTOMERS))
@router.callback_query(
    NavigationCallback.filter(
        (F.target == NavigationTarget.CUSTOMERS)
        & ((F.action == NavigationAction.BACK) | (F.action == NavigationAction.REFRESH))
    )
)
async def begin_customer_search(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(CustomerSearchStates.query)
    await show_screen(callback, render_customer_search_prompt())


@router.message(CustomerSearchStates.query)
async def receive_customer_search(
    message: Message,
    state: FSMContext,
    customers: CustomerUseCases,
) -> None:
    raw_search = message.text.strip() if message.text else ""
    search_term = None if raw_search == "*" else raw_search
    try:
        query = validate_input(SearchCustomersQuery, {"search_term": search_term})
        page = await customers.search_customers(query)
    except ApplicationError as error:
        await show_error(message, error)
        return
    await state.update_data(customer_search_term=query.search_term)
    await show_screen(message, render_customer_list(page))


@router.callback_query(PageCallback.filter(F.scope == PageScope.CUSTOMERS))
async def paginate_customers(
    callback: CallbackQuery,
    callback_data: PageCallback,
    state: FSMContext,
    customers: CustomerUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    try:
        query = validate_input(
            SearchCustomersQuery,
            {
                "search_term": data.get("customer_search_term"),
                "page": callback_data.page,
            },
        )
        page = await customers.search_customers(query)
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_customer_list(page))


@router.callback_query(CustomerCallback.filter(F.action == CustomerCallbackAction.DETAILS))
async def show_customer_details(
    callback: CallbackQuery,
    callback_data: CustomerCallback,
    customers: CustomerUseCases,
) -> None:
    await callback.answer()
    try:
        customer = await customers.get_customer(
            GetCustomerQuery(customer_id=callback_data.customer_id)
        )
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_customer_details(customer))


@router.callback_query(CustomerCallback.filter(F.action == CustomerCallbackAction.UPDATE_PLACE_ID))
async def begin_place_id_update(
    callback: CallbackQuery,
    callback_data: CustomerCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(CustomerPlaceIDStates.place_id)
    await state.update_data(place_id_customer_id=str(callback_data.customer_id))
    await show_screen(
        callback,
        Screen(
            text="Send the new Place ID.",
            reply_markup=navigation_keyboard(back_target=NavigationTarget.CUSTOMER_DETAILS),
        ),
    )


@router.callback_query(
    CustomerPlaceIDStates.place_id,
    NavigationCallback.filter(
        (F.action == NavigationAction.BACK) & (F.target == NavigationTarget.CUSTOMER_DETAILS)
    ),
)
async def back_from_place_id_update(
    callback: CallbackQuery,
    state: FSMContext,
    customers: CustomerUseCases,
) -> None:
    await callback.answer()
    data = await state.get_data()
    customer_id = data.get("place_id_customer_id")
    await state.clear()
    if customer_id is None:
        await show_screen(callback, render_customer_search_prompt())
        return
    customer = await customers.get_customer(GetCustomerQuery(customer_id=customer_id))
    await show_screen(callback, render_customer_details(customer))


@router.message(CustomerPlaceIDStates.place_id)
async def receive_place_id_update(
    message: Message,
    state: FSMContext,
    customers: CustomerUseCases,
) -> None:
    data = await state.get_data()
    try:
        place_id = validate_positive_integer(message.text, "place_id")
        command = validate_input(
            UpdatePlaceIDCommand,
            {
                "operator_id": message.from_user.id if message.from_user else None,
                "customer_id": data.get("place_id_customer_id"),
                "place_id": place_id,
            },
        )
        await state.clear()
        result = await customers.update_place_id(command)
    except ApplicationError as error:
        await state.clear()
        await show_error(message, error)
        return
    await show_screen(message, render_action_result(result))


@router.callback_query(
    CustomerCallback.filter(
        F.action.in_({CustomerCallbackAction.REFRESH, CustomerCallbackAction.ARCHIVE})
    )
)
async def handle_customer_action(
    callback: CallbackQuery,
    callback_data: CustomerCallback,
    customers: CustomerUseCases,
) -> None:
    await callback.answer()
    try:
        if callback_data.action == CustomerCallbackAction.REFRESH:
            result = await customers.refresh_customer(
                CustomerActionCommand(
                    customer_id=callback_data.customer_id,
                    operator_id=callback.from_user.id,
                )
            )
        else:
            result = await customers.archive_customer(
                ArchiveCustomerCommand(
                    customer_id=callback_data.customer_id,
                    operator_id=callback.from_user.id,
                )
            )
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_action_result(result))
