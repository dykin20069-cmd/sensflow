"""Safe responses for stale or malformed Telegram updates."""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from sensflow.presentation.telegram.rendering import render_main_menu, show_screen

router = Router(name="fallback")


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    await callback.answer("This control is no longer available.", show_alert=True)


@router.message()
async def unknown_message(message: Message) -> None:
    await show_screen(message, render_main_menu())
