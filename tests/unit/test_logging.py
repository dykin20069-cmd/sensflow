"""Tests for structured, secret-safe logging."""

import json
import logging

import pytest

from sensflow.infrastructure.logging import JsonFormatter, redact_sensitive_text


@pytest.mark.unit
def test_json_formatter_emits_structured_log_record() -> None:
    record = logging.LogRecord(
        name="sensflow.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="application_started",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "sensflow.test"
    assert payload["message"] == "application_started"
    assert payload["timestamp"].endswith("Z")


def test_json_formatter_includes_only_approved_operational_fields() -> None:
    record = logging.LogRecord(
        name="sensflow.workflow",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="marketplace_purchase_started",
        args=(),
        exc_info=None,
    )
    record.order_id = "order-1"
    record.requested_robux = 1000
    record.selected_rate = "1.5"
    record.customer_notes = "must never be logged"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["order_id"] == "order-1"
    assert payload["requested_robux"] == 1000
    assert payload["selected_rate"] == "1.5"
    assert "customer_notes" not in payload


@pytest.mark.unit
def test_sensitive_values_are_redacted() -> None:
    message = (
        "token=telegram-secret password:database-secret "
        "postgresql://user:url-secret@localhost/sensflow"
    )

    redacted = redact_sensitive_text(message)

    assert "telegram-secret" not in redacted
    assert "database-secret" not in redacted
    assert "url-secret" not in redacted
    assert redacted.count("***") == 3
