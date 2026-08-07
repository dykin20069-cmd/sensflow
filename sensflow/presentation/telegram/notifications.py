"""Telegram implementation of operator notification delivery."""

from aiogram import Bot


class TelegramOperatorNotifier:
    """Send application notifications to the configured operator chat."""

    def __init__(self, bot: Bot, operator_id: int) -> None:
        self._bot = bot
        self._operator_id = operator_id

    async def send(self, message: str) -> None:
        await self._bot.send_message(chat_id=self._operator_id, text=message)
