"""Safe mapping of application and unexpected errors to Telegram screens."""

import logging
from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, ErrorEvent, Message

from sensflow.application.errors import (
    ApplicationError,
    AuthorizationError,
    ConflictError,
    FeatureUnavailableError,
    InputValidationError,
    NotFoundError,
)
from sensflow.presentation.telegram.formatting import escape_text
from sensflow.presentation.telegram.keyboards import navigation_keyboard
from sensflow.presentation.telegram.rendering import Screen, show_screen

logger = logging.getLogger(__name__)


def error_screen(error: Exception) -> Screen:
    if isinstance(error, InputValidationError):
        detail = "\n".join(f"• {escape_text(issue)}" for issue in error.issues)
        message = f"Please check the entered value:\n{detail}"
    elif isinstance(error, NotFoundError):
        message = f"{escape_text(error.entity_name)} was not found."
    elif isinstance(error, AuthorizationError):
        message = "Access denied."
    elif isinstance(error, ConflictError):
        message = escape_text(str(error))
    elif isinstance(error, FeatureUnavailableError):
        message = f"{escape_text(error.feature_name)} will be enabled in a later milestone."
    elif isinstance(error, ApplicationError):
        message = "The action could not be completed."
    else:
        message = "An unexpected error occurred. No business changes were made."
    return Screen(
        text=f"<b>Unable to continue</b>\n\n{message}", reply_markup=navigation_keyboard()
    )


async def show_error(event: Message | CallbackQuery, error: Exception) -> None:
    await show_screen(event, error_screen(error))


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    logger.error(
        "telegram_update_failed",
        exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
    )
    callback = event.update.callback_query
    if callback is not None:
        with suppress(TelegramBadRequest):
            await callback.answer()
        await show_error(callback, event.exception)
        return True
    message = event.update.message
    if message is not None:
        await show_error(message, event.exception)
    return True
