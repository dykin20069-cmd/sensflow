"""Pure screen renderers and Telegram message presentation mechanics."""

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from sensflow.application.dto import (
    ActionResultDTO,
    CurrentStockDTO,
    CustomerDetailDTO,
    OrderDetailDTO,
    OrderStatusCountsDTO,
    PageDTO,
    PlaceIDSelectionDTO,
    SettingsDTO,
    StatisticsDTO,
    SystemStatusDTO,
    TimelineEventDTO,
)
from sensflow.domain.enums import ClientOrderStatus, StatisticsPeriod
from sensflow.presentation.telegram.callbacks import NavigationTarget
from sensflow.presentation.telegram.formatting import (
    MOSCOW_TIMEZONE,
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
    no_stock_fallback_keyboard,
    order_details_keyboard,
    order_list_keyboard,
    orders_menu_keyboard,
    place_lookup_fallback_keyboard,
    public_places_keyboard,
    remembered_place_keyboard,
    settings_keyboard,
    similar_order_keyboard,
    statistics_keyboard,
    system_status_keyboard,
)
from sensflow.presentation.telegram.pagination import Pagination

MAX_PREVIEW_ITEMS = 10
STOCK_VIEW_THRESHOLD = Decimal("5.0")


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


async def show_fresh_dashboard(callback: CallbackQuery) -> None:
    """Remove the current inline screen and send a clean Dashboard message."""
    if isinstance(callback.message, Message):
        dashboard = render_main_menu()
        with suppress(TelegramBadRequest):
            await callback.message.delete()
        await callback.message.answer(
            dashboard.text,
            reply_markup=dashboard.reply_markup,
        )


def render_main_menu() -> Screen:
    return Screen(
        text="<b>🏠 SensFlow Dashboard</b>\n\nChoose an action:",
        reply_markup=main_menu_keyboard(),
    )


def render_remembered_place(selection: PlaceIDSelectionDTO) -> Screen:
    place = selection.remembered_place
    if place is None:
        return render_place_lookup_fallback("No remembered place is available.")
    return Screen(
        text=(
            "<b>🎮 Remembered place found</b>\n\n"
            f"Customer: {escape_text(selection.username)}\n"
            "Saved place:\n"
            f"[{escape_text(place.place_name)}]\n"
            f"Place ID: <code>{place.place_id}</code>"
        ),
        reply_markup=remembered_place_keyboard(),
    )


def render_public_places(selection: PlaceIDSelectionDTO) -> Screen:
    lines = [f"<b>🎮 Public places for {escape_text(selection.username)}</b>"]
    for place in selection.public_places:
        lines.append(
            f"\n🎮 {escape_text(place.place_name)}\n⭐ {_compact_number(place.visits)} visits"
        )
    return Screen(
        text="\n".join(lines),
        reply_markup=public_places_keyboard(selection.public_places),
    )


def render_place_lookup_fallback(message: str = "No public places found.") -> Screen:
    return Screen(
        text=(f"<b>{escape_text(message)}</b>\n\nPlease enter the Roblox Place ID manually."),
        reply_markup=place_lookup_fallback_keyboard(),
    )


def _compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(value)


def render_current_stock(stock: CurrentStockDTO) -> Screen:
    ordered_levels = sorted(stock.items, key=lambda item: item.rate)
    visible_levels = [item for item in ordered_levels if item.rate <= STOCK_VIEW_THRESHOLD]
    above_threshold = not visible_levels
    displayed_levels = visible_levels if visible_levels else ordered_levels[:5]
    displayed_levels.sort(key=lambda item: item.rate, reverse=True)

    lines: list[str] = []
    if above_threshold:
        lines.append(f"⚠️ No offers up to {STOCK_VIEW_THRESHOLD:.1f}$")
    for item in displayed_levels:
        if item.rate <= stock.preferred_rate:
            marker = "🟢"
        elif item.rate <= stock.maximum_purchase_rate:
            marker = "🟡"
        else:
            marker = "🔴"
        rate = format_decimal(item.rate)
        if "." not in rate:
            rate = f"{rate}.0"
        lines.append(
            f"{marker} {rate}$ | 👥 {item.accounts_count:,} | "
            f"💰 {item.total_robux_amount:,} R$ | ⚡ {item.max_instant_order:,} R$"
        )
    if above_threshold and ordered_levels:
        lines.append("Market currently above your viewing threshold.")
    body = "\n".join(lines) or "No stock is currently available."
    levels_within_limit = [
        item for item in displayed_levels if item.rate <= stock.maximum_purchase_rate
    ]
    total_available = sum(item.total_robux_amount for item in levels_within_limit)
    maximum_instant = max((item.max_instant_order for item in levels_within_limit), default=0)
    updated = stock.updated_at.astimezone(MOSCOW_TIMEZONE).strftime("%H:%M MSK")
    return Screen(
        text=(
            "<b>📊 Current RBXCrate Stock</b>\n\n"
            f"{body}\n\n"
            "━━━━━━━━━━━━\n"
            f"📦 Total within limit: {total_available:,} R$\n"
            f"⚡ Best instant order: {maximum_instant:,} R$\n"
            f"🎯 Limit: ≤ {format_decimal(stock.maximum_purchase_rate, '$')} | "
            f"Preferred: ≤ {format_decimal(stock.preferred_rate, '$')}\n"
            f"🕒 {updated}"
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
    preferred_details = (
        "⚡ Preferred: disabled\n🚀 Immediate execution allowed\n"
        if not order.preferred_mode_enabled
        else (
            f"Preferred rate: {format_decimal(order.preferred_rate)}\n"
            f"Preferred timeout: {order.preferred_timeout_minutes or '—'} min\n"
            f"Fallback active: {format_boolean(order.fallback_active)}\n"
        )
    )
    text = (
        "<b>Order Details</b>\n\n"
        f"Customer: {escape_text(order.customer_username)}\n"
        f"Status: {humanize(order.status)}\n"
        f"Requested: {format_robux(order.requested_robux)}\n"
        f"Customer receives: {format_robux(order.customer_receives)}\n"
        f"Place ID: <code>{order.current_place_id}</code>\n"
        f"Maximum rate: {format_decimal(order.marketplace_rate_limit)}\n"
        f"{preferred_details}"
        f"Marketplace rate: {format_decimal(order.marketplace_rate)}\n"
        f"Executed rate: {format_decimal(order.executed_rate)}\n"
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
    preferred_disabled = (
        "⚡ Preferred: disabled\n🚀 Immediate execution allowed"
        if not order.preferred_mode_enabled
        else None
    )
    if order.status is ClientOrderStatus.PURCHASING:
        title = "📦 Active Order"
        body = (
            f"👤 {escape_text(order.customer_username)}\n"
            f"🛒 {format_robux(order.requested_robux)}\n"
            f"🎁 Client: {format_robux(order.customer_receives)}\n"
            "Status: Purchasing\n"
            f"Marketplace rate limit: ≤ {format_decimal(order.marketplace_rate_limit, '$')}\n"
            f"Auto Requeue: {format_boolean(order.automatic_requeue_enabled)}\n"
            f"Requeue attempts: {order.requeue_attempts}\n"
            f"⏱ Created: {_format_card_datetime(order.created_at)}"
            f"{'' if preferred_disabled is None else f'\n{preferred_disabled}'}"
        )
    elif order.status is ClientOrderStatus.PREORDER:
        title = "⏳ PreOrder"
        remembered = "Yes" if order.remembered_place else "No"
        waited_minutes = min(
            (order.waiting_seconds or 0) // 60,
            order.preferred_timeout_minutes or 0,
        )
        if preferred_disabled is not None:
            preferred_status = preferred_disabled
        elif order.fallback_active:
            preferred_status = (
                "🟠 Preferred timeout expired\n"
                f"🔓 Fallback active up to {format_decimal(order.marketplace_rate_limit, '$')}"
            )
        else:
            preferred_status = (
                f"🟡 Preferred: {format_decimal(order.preferred_rate, '$')}\n"
                f"🔒 Max: {format_decimal(order.marketplace_rate_limit, '$')}\n"
                f"⏳ Waiting: {waited_minutes}"
                f" / {order.preferred_timeout_minutes or '—'} min"
            )
        body = (
            f"👤 {escape_text(order.customer_username)}\n"
            f"🛒 {format_robux(order.requested_robux)}\n"
            f"🎁 Client: {format_robux(order.customer_receives)}\n"
            f"Waiting: {_format_duration(order.waiting_seconds)}\n"
            "Next automatic retry: "
            f"in {format_decimal(order.next_automatic_retry_seconds, 's')}\n"
            f"Remembered place: {remembered}\n"
            "Priority: Maximum clients (smallest amount first)\n"
            f"{preferred_status}"
        )
    else:
        title = f"📋 {humanize(order.status)} Order"
        body = (
            f"👤 {escape_text(order.customer_username)}\n"
            f"💰 {format_robux(order.requested_robux)}\n"
            f"🎮 <code>{order.current_place_id}</code>\n"
            f"Status: {humanize(order.status)}\n"
            f"Max rate: {format_decimal(order.marketplace_rate_limit, '$')}\n"
            f"{preferred_disabled or f'Preferred: {format_decimal(order.preferred_rate, "$")}'}"
        )
    reference = (
        ""
        if order.marketplace_order_reference is None
        else f"\nMarketplace order: <code>{escape_text(order.marketplace_order_reference)}</code>"
    )
    notice_text = "" if notice is None else f"\n\n{escape_text(notice)}"
    return Screen(
        text=(f"<b>{title}</b>\n\n{body}{reference}{notice_text}"),
        reply_markup=order_details_keyboard(order.id, order.status, order.available_actions),
    )


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _format_card_datetime(value: datetime) -> str:
    return value.astimezone(MOSCOW_TIMEZONE).strftime("%d.%m.%Y %H:%M MSK")


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


def render_no_suitable_stock(requested_robux: int, maximum_rate: Decimal) -> Screen:
    return Screen(
        text=(
            "<b>⚠️ No suitable stock available</b>\n\n"
            f"Requested: {format_robux(requested_robux)}\n"
            f"Current limit: ≤ {format_decimal(maximum_rate, '$')}\n\n"
            "What do you want to do?"
        ),
        reply_markup=no_stock_fallback_keyboard(),
    )


def render_preorder_created(order: OrderDetailDTO) -> Screen:
    return Screen(
        text=(
            "<b>📦 PreOrder created</b>\n\n"
            f"Customer: {escape_text(order.customer_username)}\n"
            f"Requested: {format_robux(order.requested_robux)}\n"
            f"Place ID: <code>{order.current_place_id}</code>\n\n"
            "The bot will automatically monitor stock and purchase the order "
            "when a suitable rate appears."
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
        body = (
            "<b>⚙️ Purchase settings</b>\n"
            f"Max rate: {format_decimal(settings.maximum_purchase_rate, '$')}\n"
            "Preferred Mode By Default: "
            f"{'ON' if settings.preferred_mode_default else 'OFF'}\n"
            f"Preferred rate: {format_decimal(settings.preferred_purchase_rate, '$')}\n"
            f"Preferred timeout: {settings.preferred_timeout_minutes} min\n\n"
            "<b>⚙️ Balance alerts</b>\n"
            f"Low balance: {format_decimal(settings.low_balance_threshold, '$')}\n"
            f"Critical balance: {format_decimal(settings.critical_balance_threshold, '$')}\n\n"
            "<b>⚙️ Stock notifications</b>\n"
            f"Enabled: {format_boolean(settings.stock_notifications_enabled)}\n\n"
            "<b>Marketplace Commission</b>\n"
            "Decimal fee rate applied to marketplace cost (0.05 = 5%).\n"
            f"Current: {format_decimal(settings.marketplace_commission)}\n\n"
            f"USD exchange rate: {format_decimal(settings.usd_exchange_rate)}\n"
            f"Automatic reorder: {format_boolean(settings.automatic_reorder_enabled)}\n"
            "\n<b>Automatic Reorder Interval</b>\n"
            "How often active marketplace orders are checked for automatic requeue.\n"
            f"Current: {format_decimal(settings.automatic_reorder_interval_seconds, 's')}\n"
            "Minimum: 0.300s\n\n"
            "<b>Auto Requeue Delay</b>\n"
            "How long an ACTIVE order waits before its queue priority is refreshed.\n"
            f"Current: {format_decimal(settings.auto_requeue_delay_seconds, 's')}\n\n"
            "<b>Stock Monitoring Interval</b>\n"
            "How often RBXCrate stock is refreshed for PreOrders.\n"
            f"Current: {settings.marketplace_monitoring_interval_seconds}s\n"
            f"Synchronization interval: {settings.synchronization_interval_seconds}s\n"
            f"Telegram notifications: {format_boolean(settings.telegram_notifications_enabled)}\n\n"
            "<b>Notification Categories</b>\n"
            "Use the inline switches below."
        )
    return Screen(
        text=f"<b>Settings</b>\n\n{body}",
        reply_markup=settings_keyboard(settings),
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
