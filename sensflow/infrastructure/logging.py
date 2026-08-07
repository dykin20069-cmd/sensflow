"""Secret-safe structured logging built on the standard library."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b(authorization|api[_-]?key|password|secret|token)(\s*[:=]\s*)([^\s,;]+)"
)
_POSTGRES_PASSWORD = re.compile(r"(?i)(postgres(?:ql)?(?:\+[^:]+)?://[^:\s]+:)([^@\s]+)(@)")
_STRUCTURED_FIELDS = (
    "order_id",
    "customer_id",
    "marketplace_order_id",
    "external_order_id",
    "requested_robux",
    "selected_rate",
    "synchronization_status",
    "recovery_action",
    "rate",
    "total_robux",
    "max_instant",
    "recipient",
    "previous_marketplace_order_id",
    "new_marketplace_order_id",
    "username",
    "place_id",
    "count",
    "customer",
    "available",
    "requeue_attempt",
    "reason",
)


def redact_sensitive_text(value: str) -> str:
    """Mask common credential forms before text reaches a log sink."""
    redacted = _KEY_VALUE_SECRET.sub(r"\1\2***", value)
    return _POSTGRES_PASSWORD.sub(r"\1***\3", redacted)


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
            "event": redact_sensitive_text(record.getMessage()),
        }

        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = redact_sensitive_text(value) if isinstance(value, str) else value

        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str) -> None:
    """Configure process-wide JSON logging to standard output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logging.captureWarnings(True)
    logging.raiseExceptions = False
