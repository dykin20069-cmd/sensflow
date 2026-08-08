"""Safe, consistent formatting helpers for Telegram screens."""

from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")

_SPECIAL_LABELS = {
    "preorder": "PreOrder",
    "usd": "USD",
    "id": "ID",
}


def escape_text(value: object) -> str:
    """Escape untrusted text for Telegram HTML parse mode."""
    return escape(str(value), quote=True)


def format_robux(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,} R$".replace(",", " ")


def format_decimal(value: Decimal | None, suffix: str = "") -> str:
    if value is None:
        return "—"
    formatted = format(value, "f").rstrip("0").rstrip(".") or "0"
    return f"{formatted}{suffix}"


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone(MOSCOW_TIMEZONE).strftime("%Y-%m-%d %H:%M MSK")


def format_boolean(value: bool) -> str:
    return "Enabled" if value else "Disabled"


def humanize(value: object) -> str:
    raw_value = getattr(value, "value", value)
    words = str(raw_value).split("_")
    return " ".join(_SPECIAL_LABELS.get(word, word.title()) for word in words)
