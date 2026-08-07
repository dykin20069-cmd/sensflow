"""Single-operator Telegram authorization middleware."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AuthorizationMiddleware(BaseMiddleware):
    """Allow only the configured Telegram operator."""

    def __init__(self, operator_id: int) -> None:
        self._operator_id = operator_id

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not isinstance(user, User) or user.id != self._operator_id:
            if isinstance(event, CallbackQuery):
                await event.answer("Access denied.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Access denied.")
            return None
        return await handler(event, data)
