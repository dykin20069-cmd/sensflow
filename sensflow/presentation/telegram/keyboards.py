"""Inline keyboard builders for all Telegram skeleton screens."""

from collections.abc import Iterable
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sensflow.application.commands import SettingField
from sensflow.application.dto import (
    CustomerAction,
    CustomerSummaryDTO,
    OrderAction,
    OrderStatusCountsDTO,
    OrderSummaryDTO,
    PublicPlaceDTO,
)
from sensflow.domain.enums import ClientOrderStatus, StatisticsPeriod
from sensflow.presentation.telegram.callbacks import (
    CustomerCallback,
    CustomerCallbackAction,
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    OrderCallback,
    OrderCallbackAction,
    PageCallback,
    PageScope,
    PlaceCallback,
    PlaceCallbackAction,
    SettingsCallback,
    SettingsCallbackAction,
    StatisticsCallback,
    SystemCallback,
    SystemCallbackAction,
)
from sensflow.presentation.telegram.formatting import humanize
from sensflow.presentation.telegram.pagination import Pagination


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, section in (
        ("🏠 Dashboard", MainSection.DASHBOARD),
        ("🛒 Create Order", MainSection.CREATE_ORDER),
        ("📦 Active Orders", MainSection.ACTIVE_ORDERS),
        ("⏳ PreOrders", MainSection.PREORDERS),
        ("📊 Current Stock", MainSection.CURRENT_STOCK),
        ("⚙️ Settings", MainSection.SETTINGS),
    ):
        builder.button(text=label, callback_data=MenuCallback(section=section))
    builder.adjust(1)
    return builder.as_markup()


def navigation_keyboard(
    *,
    back_target: NavigationTarget | None = None,
    refresh_target: NavigationTarget | None = None,
    include_home: bool = True,
    include_close: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if back_target is not None:
        builder.button(
            text="⬅️ Back",
            callback_data=NavigationCallback(
                action=NavigationAction.BACK,
                target=back_target,
            ),
        )
    if include_home:
        builder.button(
            text="🏠 Home",
            callback_data=NavigationCallback(action=NavigationAction.HOME),
        )
    if refresh_target is not None:
        builder.button(
            text="🔄 Refresh",
            callback_data=NavigationCallback(
                action=NavigationAction.REFRESH,
                target=refresh_target,
            ),
        )
    if include_close:
        builder.button(
            text="❌ Close",
            callback_data=NavigationCallback(
                action=(NavigationAction.CLOSE if back_target is None else NavigationAction.BACK),
                target=back_target or NavigationTarget.MAIN,
            ),
        )
    builder.adjust(2, 1)
    return builder.as_markup()


def current_stock_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Refresh",
        callback_data=NavigationCallback(
            action=NavigationAction.REFRESH,
            target=NavigationTarget.CURRENT_STOCK,
        ),
    )
    builder.button(
        text="🏠 Home",
        callback_data=NavigationCallback(action=NavigationAction.HOME),
    )
    builder.button(
        text="❌ Close",
        callback_data=NavigationCallback(action=NavigationAction.CLOSE),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def similar_order_keyboard(order_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Reuse existing",
        callback_data=OrderCallback(
            action=OrderCallbackAction.REUSE_SIMILAR,
            order_id=order_id,
        ),
    )
    builder.button(
        text="➕ Create another",  # noqa: RUF001
        callback_data=OrderCallback(action=OrderCallbackAction.CREATE_DUPLICATE),
    )
    builder.button(
        text="❌ Cancel",
        callback_data=OrderCallback(action=OrderCallbackAction.ABORT_CREATE),
    )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER)
        )
    )
    return builder.as_markup()


def system_status_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Run Recovery Now",
        callback_data=SystemCallback(action=SystemCallbackAction.RUN_RECOVERY),
    )
    builder.button(
        text="Run Sync Pass Now",
        callback_data=SystemCallback(action=SystemCallbackAction.RUN_SYNC),
    )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(refresh_target=NavigationTarget.SYSTEM_STATUS)
        )
    )
    return builder.as_markup()


def orders_menu_keyboard(counts: OrderStatusCountsDTO) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for status in ClientOrderStatus:
        count = counts.counts.get(status, 0)
        builder.button(
            text=f"{humanize(status)} ({count})",
            callback_data=OrderCallback(action=OrderCallbackAction.LIST, status=status),
        )
    builder.button(
        text="🔎 Search Orders",
        callback_data=OrderCallback(action=OrderCallbackAction.SEARCH),
    )
    builder.attach(InlineKeyboardBuilder.from_markup(navigation_keyboard()))
    builder.adjust(1, 2)
    return builder.as_markup()


def _pagination_buttons(
    pagination: Pagination,
    *,
    scope: PageScope,
    key: str = "",
) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if pagination.previous_page is not None:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=PageCallback(
                    scope=scope,
                    page=pagination.previous_page,
                    key=key,
                ).pack(),
            )
        )
    buttons.append(
        InlineKeyboardButton(
            text=f"{pagination.page}/{pagination.total_pages}",
            callback_data=NavigationCallback(action=NavigationAction.NOOP).pack(),
        )
    )
    if pagination.next_page is not None:
        buttons.append(
            InlineKeyboardButton(
                text="➡️ Next",
                callback_data=PageCallback(
                    scope=scope,
                    page=pagination.next_page,
                    key=key,
                ).pack(),
            )
        )
    return buttons


def order_list_keyboard(
    orders: Iterable[OrderSummaryDTO],
    pagination: Pagination,
    key: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        builder.button(
            text=f"{order.customer_username} · {order.requested_robux} R$",
            callback_data=OrderCallback(
                action=OrderCallbackAction.DETAILS,
                order_id=order.id,
            ),
        )
    builder.adjust(1)
    builder.row(*_pagination_buttons(pagination, scope=PageScope.ORDERS, key=key))
    builder.attach(
        InlineKeyboardBuilder.from_markup(navigation_keyboard(back_target=NavigationTarget.ORDERS))
    )
    return builder.as_markup()


def order_details_keyboard(
    order_id: UUID,
    status: ClientOrderStatus,
    actions: Iterable[OrderAction],
) -> InlineKeyboardMarkup:
    action_config = {
        OrderAction.CONFIRM_PAYMENT: ("Confirm Payment", OrderCallbackAction.CONFIRM_PAYMENT),
        OrderAction.EDIT_DRAFT: ("Edit Draft", OrderCallbackAction.EDIT_DRAFT),
        OrderAction.DELETE_DRAFT: ("Delete Draft", OrderCallbackAction.DELETE_DRAFT),
        OrderAction.START_PURCHASE: ("📦 Retry Stock Check", OrderCallbackAction.START_PURCHASE),
        OrderAction.MANUAL_REORDER: ("🔄 Requeue Now", OrderCallbackAction.MANUAL_REORDER),
        OrderAction.CANCEL: ("❌ Cancel", OrderCallbackAction.CANCEL),
        OrderAction.REFRESH: ("🔄 Refresh Status", OrderCallbackAction.REFRESH),
        OrderAction.TIMELINE: ("📋 Details", OrderCallbackAction.TIMELINE),
    }
    builder = InlineKeyboardBuilder()
    for action in actions:
        label, callback_action = action_config[action]
        builder.button(
            text=label,
            callback_data=OrderCallback(action=callback_action, order_id=order_id),
        )
    builder.adjust(1)
    builder.button(
        text="⬅️ Back",
        callback_data=OrderCallback(action=OrderCallbackAction.LIST, status=status),
    )
    builder.button(
        text="🏠 Home",
        callback_data=NavigationCallback(action=NavigationAction.HOME),
    )
    builder.button(
        text="❌ Close",
        callback_data=OrderCallback(action=OrderCallbackAction.LIST, status=status),
    )
    builder.adjust(1, 2, 1)
    return builder.as_markup()


def remembered_place_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Use remembered",
        callback_data=PlaceCallback(action=PlaceCallbackAction.USE_REMEMBERED),
    )
    builder.button(
        text="🎮 Choose public place",
        callback_data=PlaceCallback(action=PlaceCallbackAction.CHOOSE_PUBLIC),
    )
    builder.button(
        text="⌨️ Enter manually",
        callback_data=PlaceCallback(action=PlaceCallbackAction.ENTER_MANUALLY),
    )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER)
        )
    )
    return builder.as_markup()


def public_places_keyboard(places: Iterable[PublicPlaceDTO]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, place in enumerate(places):
        label = place.place_name if len(place.place_name) <= 38 else f"{place.place_name[:35]}…"
        builder.button(
            text=f"✅ Select · {label}",
            callback_data=PlaceCallback(action=PlaceCallbackAction.SELECT, index=index),
        )
    builder.button(
        text="⌨️ Enter manually",
        callback_data=PlaceCallback(action=PlaceCallbackAction.ENTER_MANUALLY),
    )
    builder.button(
        text="🔄 Refresh places",
        callback_data=PlaceCallback(action=PlaceCallbackAction.REFRESH),
    )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER)
        )
    )
    return builder.as_markup()


def place_lookup_fallback_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⌨️ Enter manually",
        callback_data=PlaceCallback(action=PlaceCallbackAction.ENTER_MANUALLY),
    )
    builder.button(
        text="🔄 Refresh places",
        callback_data=PlaceCallback(action=PlaceCallbackAction.REFRESH),
    )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(back_target=NavigationTarget.CREATE_ORDER)
        )
    )
    return builder.as_markup()


def customer_list_keyboard(
    customers: Iterable[CustomerSummaryDTO],
    pagination: Pagination,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for customer in customers:
        suffix = " · Archived" if customer.archived else ""
        builder.button(
            text=f"{customer.username}{suffix}",
            callback_data=CustomerCallback(
                action=CustomerCallbackAction.DETAILS,
                customer_id=customer.id,
            ),
        )
    builder.adjust(1)
    builder.row(*_pagination_buttons(pagination, scope=PageScope.CUSTOMERS))
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(back_target=NavigationTarget.CUSTOMERS)
        )
    )
    return builder.as_markup()


def customer_details_keyboard(
    customer_id: UUID,
    actions: Iterable[CustomerAction],
) -> InlineKeyboardMarkup:
    action_config = {
        CustomerAction.REFRESH: ("Refresh Information", CustomerCallbackAction.REFRESH),
        CustomerAction.UPDATE_PLACE_ID: (
            "Update Place ID",
            CustomerCallbackAction.UPDATE_PLACE_ID,
        ),
        CustomerAction.ARCHIVE: ("Archive Customer", CustomerCallbackAction.ARCHIVE),
    }
    builder = InlineKeyboardBuilder()
    for action in actions:
        label, callback_action = action_config[action]
        builder.button(
            text=label,
            callback_data=CustomerCallback(
                action=callback_action,
                customer_id=customer_id,
            ),
        )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(back_target=NavigationTarget.CUSTOMERS)
        )
    )
    return builder.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field in SettingField:
        builder.button(
            text=humanize(field),
            callback_data=SettingsCallback(action=SettingsCallbackAction.EDIT, field=field),
        )
    builder.adjust(1)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(refresh_target=NavigationTarget.SETTINGS)
        )
    )
    return builder.as_markup()


def statistics_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in StatisticsPeriod:
        builder.button(
            text=humanize(period),
            callback_data=StatisticsCallback(period=period),
        )
    builder.adjust(3)
    builder.attach(
        InlineKeyboardBuilder.from_markup(
            navigation_keyboard(refresh_target=NavigationTarget.STATISTICS)
        )
    )
    return builder.as_markup()
