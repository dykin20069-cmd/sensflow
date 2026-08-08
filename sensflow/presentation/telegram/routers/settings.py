"""System Settings read and deferred edit handlers."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import UpdateSettingCommand
from sensflow.application.errors import ApplicationError
from sensflow.application.ports import SettingsUseCases
from sensflow.application.validation import validate_input
from sensflow.domain.enums import NotificationType, SettingField
from sensflow.presentation.telegram.callbacks import (
    NOTIFICATION_CATEGORY_TYPES,
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    NotificationCategoryCallback,
    SettingsCallback,
    SettingsCallbackAction,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.formatting import escape_text, humanize
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import (
    Screen,
    render_action_result,
    render_settings,
    show_screen,
)
from sensflow.presentation.telegram.states import SettingsEditStates

router = Router(name="settings")


@router.callback_query(MenuCallback.filter(F.section == MainSection.SETTINGS))
@router.callback_query(
    NavigationCallback.filter(
        (F.target == NavigationTarget.SETTINGS)
        & ((F.action == NavigationAction.BACK) | (F.action == NavigationAction.REFRESH))
    )
)
async def show_settings(
    callback: CallbackQuery,
    state: FSMContext,
    settings: SettingsUseCases,
) -> None:
    await callback.answer()
    await state.clear()
    current_settings = await settings.get_settings()
    await show_screen(callback, render_settings(current_settings))


@router.callback_query(SettingsCallback.filter(F.action == SettingsCallbackAction.EDIT))
async def begin_setting_edit(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(SettingsEditStates.value)
    await state.update_data(setting_field=callback_data.field.value)
    await show_screen(
        callback,
        Screen(
            text=f"Send the new value for <b>{escape_text(humanize(callback_data.field))}</b>.",
            reply_markup=navigation_keyboard(back_target=NavigationTarget.SETTINGS),
        ),
    )


@router.callback_query(NotificationCategoryCallback.filter())
async def toggle_notification_category(
    callback: CallbackQuery,
    callback_data: NotificationCategoryCallback,
    settings: SettingsUseCases,
) -> None:
    await callback.answer()
    current = await settings.get_settings()
    if current is None:
        await show_screen(callback, render_settings(None))
        return
    enabled = set(current.notification_categories)
    notification_types = NOTIFICATION_CATEGORY_TYPES[callback_data.category]
    if notification_types <= enabled:
        enabled.difference_update(notification_types)
    else:
        enabled.update(notification_types)
    try:
        command = validate_input(
            UpdateSettingCommand,
            {
                "operator_id": callback.from_user.id,
                "field": SettingField.NOTIFICATION_CATEGORIES,
                "value": ",".join(item.value for item in NotificationType if item in enabled)
                or "none",
            },
        )
        await settings.update_setting(command)
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_settings(await settings.get_settings()))


@router.callback_query(SettingsCallback.filter(F.action == SettingsCallbackAction.TOGGLE))
async def toggle_boolean_setting(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    settings: SettingsUseCases,
) -> None:
    await callback.answer()
    current = await settings.get_settings()
    if current is None:
        await show_screen(callback, render_settings(None))
        return
    if callback_data.field is not SettingField.PREFERRED_MODE_DEFAULT:
        return
    try:
        await settings.update_setting(
            UpdateSettingCommand(
                operator_id=callback.from_user.id,
                field=SettingField.PREFERRED_MODE_DEFAULT,
                value="off" if current.preferred_mode_default else "on",
            )
        )
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_settings(await settings.get_settings()))


@router.message(SettingsEditStates.value)
async def receive_setting_value(
    message: Message,
    state: FSMContext,
    settings: SettingsUseCases,
) -> None:
    data = await state.get_data()
    try:
        command = validate_input(
            UpdateSettingCommand,
            {
                "operator_id": message.from_user.id if message.from_user else None,
                "field": data.get("setting_field"),
                "value": message.text,
            },
        )
        await state.clear()
        result = await settings.update_setting(command)
    except ApplicationError as error:
        await state.clear()
        await show_error(message, error)
        return
    await show_screen(message, render_action_result(result))
