"""Tests for the documented modular package boundaries."""

import importlib

import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "module_name",
    [
        "sensflow.application",
        "sensflow.domain.automation",
        "sensflow.domain.customer",
        "sensflow.domain.finance",
        "sensflow.domain.marketplace",
        "sensflow.domain.notification",
        "sensflow.domain.order",
        "sensflow.domain.recovery",
        "sensflow.domain.settings",
        "sensflow.domain.statistics",
        "sensflow.infrastructure",
        "sensflow.infrastructure.database",
        "sensflow.integrations.rbxcreate",
        "sensflow.integrations.roblox",
        "sensflow.presentation.telegram",
        "sensflow.repositories",
    ],
)
def test_architecture_package_is_importable(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None
