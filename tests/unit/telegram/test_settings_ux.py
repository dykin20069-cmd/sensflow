"""Focused V2.1.1 settings UX regression tests."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Message, User

from sensflow.application.dto import SettingsDTO
from sensflow.domain.enums import NotificationType, SettingField
from sensflow.presentation.telegram.callbacks import (
    NotificationCategoryCallback,
    NotificationCategoryGroup,
    SettingsCallback,
    SettingsCallbackAction,
)
from sensflow.presentation.telegram.rendering import render_settings
from sensflow.presentation.telegram.routers.settings import (
    toggle_boolean_setting,
    toggle_notification_category,
)


def settings_dto(
    *,
    preferred_mode_default: bool = True,
    categories: tuple[NotificationType, ...] = (NotificationType.PURCHASE_COMPLETED,),
) -> SettingsDTO:
    return SettingsDTO(
        maximum_purchase_rate=Decimal("4.5"),
        preferred_mode_default=preferred_mode_default,
        preferred_purchase_rate=Decimal("4.3"),
        preferred_timeout_minutes=35,
        low_balance_threshold=Decimal("10"),
        critical_balance_threshold=Decimal("5"),
        stock_notifications_enabled=True,
        automatic_reorder_enabled=True,
        automatic_reorder_interval_seconds=Decimal("0.3"),
        auto_requeue_delay_seconds=Decimal("5"),
        marketplace_monitoring_interval_seconds=5,
        synchronization_interval_seconds=30,
        marketplace_commission=Decimal("0.05"),
        usd_exchange_rate=Decimal("90"),
        telegram_notifications_enabled=True,
        notification_categories=categories,
        application_timezone="Europe/Moscow",
    )


def callback_event() -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = User(id=42, is_bot=False, first_name="Operator")
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    return callback


def test_settings_use_grouped_inline_categories_and_hide_timezone() -> None:
    screen = render_settings(settings_dto())
    labels = [button.text for row in screen.reply_markup.inline_keyboard for button in row]

    assert "✅ Preferred Mode By Default: ON" in labels
    assert "✅ Purchases" in labels
    assert "❌ Stock Alerts" in labels
    assert "❌ Low Balance" in labels
    assert "❌ Critical Balance" in labels
    assert "❌ Errors" in labels
    assert "❌ Order Status" in labels
    assert "Notification Categories" not in labels
    assert all("Timezone" not in label for label in labels)
    assert "Timezone:" not in screen.text


def test_notification_category_button_updates_the_underlying_types() -> None:
    async def scenario() -> None:
        callback = callback_event()
        service = MagicMock()
        error_types = {
            NotificationType.AUTO_REQUEUE_FAILED,
            NotificationType.MARKETPLACE_ERROR,
            NotificationType.SYNCHRONIZATION_FAILED,
        }
        service.get_settings = AsyncMock(
            return_value=settings_dto(
                categories=tuple(item for item in NotificationType if item not in error_types)
            )
        )
        service.update_setting = AsyncMock()

        await toggle_notification_category(
            callback,
            NotificationCategoryCallback(category=NotificationCategoryGroup.ERRORS),
            service,
        )

        command = service.update_setting.await_args.args[0]
        assert command.field is SettingField.NOTIFICATION_CATEGORIES
        assert set(command.value.split(",")) == {item.value for item in NotificationType}

    asyncio.run(scenario())


def test_preferred_default_is_an_inline_boolean_toggle() -> None:
    async def scenario() -> None:
        callback = callback_event()
        service = MagicMock()
        service.get_settings = AsyncMock(return_value=settings_dto(preferred_mode_default=True))
        service.update_setting = AsyncMock()

        await toggle_boolean_setting(
            callback,
            SettingsCallback(
                action=SettingsCallbackAction.TOGGLE,
                field=SettingField.PREFERRED_MODE_DEFAULT,
            ),
            service,
        )

        command = service.update_setting.await_args.args[0]
        assert command.field is SettingField.PREFERRED_MODE_DEFAULT
        assert command.value == "off"

    asyncio.run(scenario())
