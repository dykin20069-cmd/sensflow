"""Main Menu, global navigation, and System Status handlers."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sensflow.application.commands import SystemActionCommand
from sensflow.application.errors import ApplicationError
from sensflow.application.ports import SystemUseCases
from sensflow.presentation.telegram.callbacks import (
    MainSection,
    MenuCallback,
    NavigationAction,
    NavigationCallback,
    NavigationTarget,
    SystemCallback,
    SystemCallbackAction,
)
from sensflow.presentation.telegram.errors import show_error
from sensflow.presentation.telegram.rendering import (
    render_action_result,
    render_main_menu,
    render_system_status,
    show_screen,
)

router = Router(name="main")


@router.message(CommandStart())
async def show_main_menu(message: Message) -> None:
    await show_screen(message, render_main_menu())


@router.callback_query(NavigationCallback.filter(F.action == NavigationAction.NOOP))
async def ignore_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(NavigationCallback.filter(F.action == NavigationAction.HOME))
async def navigate_home(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await show_screen(callback, render_main_menu())


@router.callback_query(NavigationCallback.filter(F.action == NavigationAction.CLOSE))
async def close_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.delete()


@router.callback_query(MenuCallback.filter(F.section == MainSection.SYSTEM_STATUS))
@router.callback_query(
    NavigationCallback.filter(
        (F.action == NavigationAction.REFRESH) & (F.target == NavigationTarget.SYSTEM_STATUS)
    )
)
async def show_system_status(
    callback: CallbackQuery,
    system: SystemUseCases,
) -> None:
    await callback.answer()
    status = await system.get_status()
    await show_screen(callback, render_system_status(status))


@router.callback_query(SystemCallback.filter())
async def run_system_action(
    callback: CallbackQuery,
    callback_data: SystemCallback,
    system: SystemUseCases,
) -> None:
    await callback.answer()
    command = SystemActionCommand(operator_id=callback.from_user.id)
    action = {
        SystemCallbackAction.RUN_RECOVERY: system.run_recovery_now,
        SystemCallbackAction.RUN_SYNC: system.run_sync_pass_now,
    }[callback_data.action]
    try:
        result = await action(command)
    except ApplicationError as error:
        await show_error(callback, error)
        return
    await show_screen(callback, render_action_result(result))
