"""Pure screen renderers and Telegram message presentation mechanics."""

from dataclasses import dataclass
from datetime import UTC

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from sensflow.application.dto import (
    ActionResultDTO,
    CurrentStockDTO,
    CustomerDetailDTO,
    OrderDetailDTO,
    OrderStatusCountsDTO,
    PageDTO,
    SettingsDTO,
    StatisticsDTO,
    SystemStatusDTO,
    TimelineEventDTO,
)
from sensflow.domain.enums import ClientOrderStatus, StatisticsPeriod
from sensflow.presentation.telegram.callbacks import NavigationTarget
from sensflow.presentation.telegram.formatting import (
    escape_text,
    format_boolean,
    format_datetime,
    format_decimal,
    format_robux,
    humanize,
)
from sensflow.presentation.telegram.keyboards import (
    current_stock_keyboard,
    customer_details_keyboard,
    customer_list_keyboard,
    main_menu_keyboard,
    navigation_keyboard,
    order_details_keyboard,
    order_list_keyboard,
    orders_menu_keyboard,
    settings_keyboard,
    similar_order_keyboard,
    statistics_keyboard,
    system_status_keyboard,
)
from sensflow.presentation.telegram.pagination import Pagination

MAX_PREVIEW_ITEMS = 10


@dataclass(frozen=True, slots=True)
class Screen:
    """Rendered Telegram message and optional inline keyboard."""

    text: str
    reply_markup: InlineKeyboardMarkup | None = None


async def show_screen(event: Message | CallbackQuery, screen: Screen) -> None:
    """Send a new screen or replace the message behind a callback."""
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            try:
                await event.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
        return
    await event.answer(screen.text, reply_markup=screen.reply_markup)


def render_main_menu() -> Screen:
    return Screen(
        text="<b>🏠 SensFlow Dashboard</b>\n\nChoose an action:",
        reply_markup=main_menu_keyboard(),
    )


def render_current_stock(stock: CurrentStockDTO) -> Screen:
    lines: list[str] = []
    for item in sorted(stock.items, key=lambda value: value.rate):
        if item.rate <= stock.preferred_rate:
            marker = "🟢"
            details = (
                f"{item.accounts_count} "
                f"{'account' if item.accounts_count == 1 else 'accounts'} — "
                f"{item.total_robux_amount} R$"
            )
        elif item.rate <= stock.maximum_purchase_rate:
            marker = "🟡"
            details = (
                f"{item.accounts_count} "
                f"{'account' if item.accounts_count == 1 else 'accounts'} — "
                f"{item.total_robux_amount} R$"
            )
        else:
            marker = "🔴"
            details = "ignored"
        lines.append(f"{marker} {format_decimal(item.rate, '$')} — {details}")
    body = "\n".join(lines) or "No stock is currently available."
    updated = stock.updated_at.astimezone(UTC).strftime("%H:%M:%S UTC")
    return Screen(
        text=(
            "<b>📊 Current RBXCrate Stock</b>\n\n"
            f"{body}\n\n"
            f"Current limit: ≤ {format_decimal(stock.maximum_purchase_rate, '$')}\n"
            f"Preferred: ≤ {format_decimal(stock.preferred_rate, '$')}\n"
            f"Updated: {updated}"
        ),
        reply_markup=current_stock_keyboard(),
    )


def render_system_status(status: SystemStatusDTO) -> Screen:
    def marker(value: bool | None, true_label: str = "OK", false_label: str = "Unavailable") -> str:
        if value is None:
            return "Not configured"
        return true_label if value else false_label

    balance = "—" if status.rbxcrate_balance is None else f"${status.rbxcrate_balance:.2f}"
    active = "—" if status.active_marketplace_orders is None else status.active_marketplace_orders
    preorders = "—" if status.pending_preorders is None else status.pending_preorders

    return Screen(
        text=(
            "<b>System Status</b>\n\n"
            f"Application: {marker(status.application_available)}\n"
            f"Database: {marker(status.database_available)}\n"
            f"Telegram: {marker(status.telegram_available)}\n"
            f"RBXCrate API: {marker(status.marketplace_available)}\n"
            f"RBXCrate Balance: {balance}\n"
            f"Automation Loop: {marker(status.automation_available, 'Running', 'Stopped')}\n"
            f"Active Marketplace Orders: {active}\n"
            f"Pending PreOrders: {preorders}"
        ),
        reply_markup=system_status_keyboard(),
    )


def render_orders_menu(counts: OrderStatusCountsDTO) -> Screen:
    return Screen(
        text="<b>Orders</b>\n\nChoose a status:",
        reply_markup=orders_menu_keyboard(counts),
    )


def render_order_list(
    page: PageDTO,
    status: ClientOrderStatus,
) -> Screen:
    if page.items:
        lines = [
            f"{index}. {escape_text(item.customer_username)} — {format_robux(item.requested_robux)}"
            for index, item in enumerate(page.items, start=1 + (page.page - 1) * page.page_size)
        ]
        body = "\n".join(lines)
    else:
        body = "No orders in this status."
    pagination = Pagination(page.page, page.page_size, page.total_items)
    title = {
        ClientOrderStatus.PURCHASING: "📦 Active Orders",
        ClientOrderStatus.PREORDER: "⏳ PreOrders",
    }.get(status, f"{humanize(status)} Orders")
    return Screen(
        text=f"<b>{title}</b>\n\n{body}",
        reply_markup=order_list_keyboard(page.items, pagination, status.value),
    )


def render_order_search_prompt() -> Screen:
    return Screen(
        text="<b>Search Orders</b>\n\nSend an Order UUID or current Customer username.",
        reply_markup=navigation_keyboard(back_target=NavigationTarget.ORDERS),
    )


def render_order_search_results(page: PageDTO) -> Screen:
    if page.items:
        lines = [
            f"• {escape_text(item.customer_username)} — {format_robux(item.requested_robux)}"
            for item in page.items
        ]
        body = "\n".join(lines)
    else:
        body = "No matching orders found."
    pagination = Pagination(page.page, page.page_size, page.total_items)
    return Screen(
        text=f"<b>Order Search</b>\n\n{body}",
        reply_markup=order_list_keyboard(page.items, pagination, "search"),
    )


def render_order_details(order: OrderDetailDTO) -> Screen:
    timeline_preview = order.timeline[-MAX_PREVIEW_ITEMS:]
    timeline = (
        "\n".join(
            f"• {format_datetime(item.created_at)} — {escape_text(item.description)}"
            for item in timeline_preview
        )
        or "No timeline events."
    )
    text = (
        "<b>Order Details</b>\n\n"
        f"Customer: {escape_text(order.customer_username)}\n"
        f"Status: {humanize(order.status)}\n"
        f"Requested: {format_robux(order.requested_robux)}\n"
        f"Customer receives: {format_robux(order.customer_receives)}\n"
        f"Place ID: <code>{order.current_place_id}</code>\n"
        f"Maximum rate: {format_decimal(order.marketplace_rate_limit)}\n"
        f"Marketplace rate: {format_decimal(order.marketplace_rate)}\n"
        f"Marketplace cost: {format_decimal(order.marketplace_cost)}\n"
        f"Marketplace commission: {format_decimal(order.marketplace_commission)}\n"
        f"Final cost USD: {format_decimal(order.final_cost_usd, ' USD')}\n"
        f"Final cost local: {format_decimal(order.final_cost_local_currency)}\n"
        f"Created: {format_datetime(order.created_at)}\n"
        f"Completed: {format_datetime(order.completed_at)}\n\n"
        f"<b>Timeline</b>\n{timeline}"
    )
    return Screen(
        text=text,
        reply_markup=order_details_keyboard(order.id, order.status, order.available_actions),
    )


def render_order_card(order: OrderDetailDTO, notice: str | None = None) -> Screen:
    if order.status is ClientOrderStatus.PURCHASING:
        title = "📦 Active Order"
        marketplace = humanize(order.marketplace_status) if order.marketplace_status else "Active"
        status_line = f"Marketplace status: {marketplace}"
    elif order.status is ClientOrderStatus.PREORDER:
        title = "⏳ PreOrder"
        status_line = f"Waiting for stock ≤ {format_decimal(order.marketplace_rate_limit, '$')}"
    else:
        title = f"📋 {humanize(order.status)} Order"
        status_line = f"Status: {humanize(order.status)}"
    reference = (
        ""
        if order.marketplace_order_reference is None
        else f"\nMarketplace order: <code>{escape_text(order.marketplace_order_reference)}</code>"
    )
    notice_text = "" if notice is None else f"\n\n{escape_text(notice)}"
    return Screen(
        text=(
            f"<b>{title}</b>\n\n"
            f"👤 {escape_text(order.customer_username)}\n"
            f"💰 {format_robux(order.requested_robux)}\n"
            f"🎮 <code>{order.current_place_id}</code>\n"
            f"{status_line}\n"
            f"Max rate: {format_decimal(order.marketplace_rate_limit, '$')}"
            f"{reference}{notice_text}"
        ),
        reply_markup=order_details_keyboard(order.id, order.status, order.available_actions),
    )


def render_similar_order(order: OrderDetailDTO) -> Screen:
    return Screen(
        text=(
            "<b>⚠️ Similar order already exists</b>\n\n"
            f"Customer: {escape_text(order.customer_username)}\n"
            f"Amount: {format_robux(order.requested_robux)}\n"
            f"Status: {humanize(order.status)}"
        ),
        reply_markup=similar_order_keyboard(order.id),
    )


def render_draft_created(order: OrderDetailDTO) -> Screen:
    """Render a newly created Draft with its immediately available actions."""
    return Screen(
        text=(
            "<b>Draft Created</b>\n\n"
            f"Order: <code>{order.id}</code>\n"
            f"Username: {escape_text(order.customer_username)}\n"
            f"Requested: {format_robux(order.requested_robux)}\n"
            f"Place ID: <code>{order.current_place_id}</code>\n"
            f"Status: {humanize(order.status)}"
        ),
        reply_markup=order_details_keyboard(order.id, order.status, order.available_actions),
    )


def render_timeline(events: tuple[TimelineEventDTO, ...]) -> Screen:
    body = (
        "\n".join(
            f"• {format_datetime(item.created_at)}\n  {escape_text(item.description)}"
            for item in events[-MAX_PREVIEW_ITEMS:]
        )
        or "No timeline events."
    )
    return Screen(text=f"<b>Order Timeline</b>\n\n{body}", reply_markup=navigation_keyboard())


def render_customer_search_prompt() -> Screen:
    return Screen(
        text=(
            "<b>Customers</b>\n\nSend a current username to search, "
            "or send <code>*</code> to list Customers."
        ),
        reply_markup=navigation_keyboard(back_target=NavigationTarget.MAIN),
    )


def render_customer_list(page: PageDTO) -> Screen:
    if page.items:
        lines = [
            f"• {escape_text(item.username)} — Place <code>{item.current_place_id}</code>"
            for item in page.items
        ]
        body = "\n".join(lines)
    else:
        body = "No Customers found."
    pagination = Pagination(page.page, page.page_size, page.total_items)
    return Screen(
        text=f"<b>Customers</b>\n\n{body}",
        reply_markup=customer_list_keyboard(page.items, pagination),
    )


def render_customer_details(customer: CustomerDetailDTO) -> Screen:
    usernames = (
        "\n".join(
            f"• {escape_text(item.username)} — {format_datetime(item.created_at)}"
            for item in customer.username_history[-MAX_PREVIEW_ITEMS:]
        )
        or "None"
    )
    place_ids = (
        "\n".join(
            f"• <code>{item.place_id}</code> — {format_datetime(item.created_at)}"
            for item in customer.place_id_history[-MAX_PREVIEW_ITEMS:]
        )
        or "None"
    )
    orders = (
        "\n".join(
            f"• {humanize(item.status)} — {format_robux(item.requested_robux)}"
            for item in customer.orders[-MAX_PREVIEW_ITEMS:]
        )
        or "None"
    )
    notes = escape_text(customer.notes) if customer.notes else "—"
    archived = "Yes" if customer.archived else "No"
    roblox_user_id = (
        "Not verified"
        if customer.roblox_user_id is None
        else f"<code>{customer.roblox_user_id}</code>"
    )
    text = (
        "<b>Customer Details</b>\n\n"
        f"Username: {escape_text(customer.username)}\n"
        f"Roblox User ID: {roblox_user_id}\n"
        f"Current Place ID: <code>{customer.current_place_id}</code>\n"
        f"Archived: {archived}\n"
        f"Notes: {notes}\n\n"
        f"<b>Previous usernames</b>\n{usernames}\n\n"
        f"<b>Previous Place IDs</b>\n{place_ids}\n\n"
        f"<b>Order history</b>\n{orders}"
    )
    return Screen(
        text=text,
        reply_markup=customer_details_keyboard(customer.id, customer.available_actions),
    )


def render_settings(settings: SettingsDTO | None) -> Screen:
    if settings is None:
        body = "System Settings have not been initialized."
    else:
        categories = (
            ", ".join(humanize(item) for item in settings.notification_categories) or "None"
        )
        body = (
            f"Maximum purchase rate: {format_decimal(settings.maximum_purchase_rate)}\n"
            f"Marketplace commission: {format_decimal(settings.marketplace_commission)}\n"
            f"USD exchange rate: {format_decimal(settings.usd_exchange_rate)}\n"
            f"Automatic reorder: {format_boolean(settings.automatic_reorder_enabled)}\n"
            f"Reorder interval: {settings.automatic_reorder_interval_seconds}s\n"
            f"Monitoring interval: {settings.marketplace_monitoring_interval_seconds}s\n"
            f"Synchronization interval: {settings.synchronization_interval_seconds}s\n"
            f"Telegram notifications: {format_boolean(settings.telegram_notifications_enabled)}\n"
            f"Notification categories: {categories}\n"
            f"Timezone: {escape_text(settings.application_timezone)}"
        )
    return Screen(
        text=f"<b>Settings</b>\n\n{body}",
        reply_markup=settings_keyboard(),
    )


def render_statistics(
    statistics: StatisticsDTO | None,
    period: StatisticsPeriod,
) -> Screen:
    if statistics is None:
        body = "No persisted statistics are available for this period."
    else:
        body = (
            f"Period start: {statistics.period_start.isoformat()}\n"
            f"Completed Orders: {statistics.completed_orders}\n"
            f"PreOrders: {statistics.preorder_orders}\n"
            f"Purchasing Orders: {statistics.purchasing_orders}\n"
            f"Purchased Robux: {format_robux(statistics.total_purchased_robux)}\n"
            f"Average purchase rate: {format_decimal(statistics.average_marketplace_rate)}\n"
            "Marketplace commission paid: "
            f"{format_decimal(statistics.total_marketplace_commission)}\n"
            f"Total spending: {format_decimal(statistics.total_amount_paid)}"
        )
    return Screen(
        text=f"<b>{humanize(period)} Statistics</b>\n\n{body}",
        reply_markup=statistics_keyboard(),
    )


def render_action_result(result: ActionResultDTO) -> Screen:
    return Screen(text=escape_text(result.message), reply_markup=navigation_keyboard())
