"""Telegram Bot construction."""

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from sensflow.infrastructure.config import TelegramSettings


def create_bot(settings: TelegramSettings) -> Bot:
    """Create one HTML-configured aiogram Bot without starting network activity."""
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
