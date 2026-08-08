"""Tests for ORM schema metadata."""

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

from sensflow.infrastructure.database.models import (
    Base,
    ClientOrder,
    Customer,
    CustomerPlaceIDHistory,
    CustomerUsernameHistory,
    MarketplaceOrder,
    Notification,
)

EXPECTED_TABLES = {
    "client_orders",
    "customer_place_id_history",
    "customer_username_history",
    "customers",
    "marketplace_orders",
    "notifications",
    "statistics",
    "system_logs",
    "system_settings",
    "timeline_events",
    "user_place_cache",
}

EXPECTED_INDEXES = {
    "ix_client_orders_created_at",
    "ix_client_orders_current_status",
    "ix_client_orders_customer_id",
    "ix_customer_place_id_history_customer_id_created_at",
    "ix_customer_username_history_customer_id_created_at",
    "ix_customers_current_username",
    "ix_marketplace_orders_client_order_id",
    "ix_marketplace_orders_marketplace_status",
    "ix_notifications_client_order_id",
    "ix_notifications_delivery_status",
    "ix_system_logs_created_at",
    "ix_timeline_events_client_order_id_created_at",
    "uq_customers_roblox_user_id_not_null",
    "uq_marketplace_orders_one_active_per_client_order",
    "uq_system_settings_singleton",
    "uq_user_place_cache_roblox_username_lower",
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    "uq_marketplace_orders_rbxcreate_order_id",
    "uq_statistics_period_start",
}


def all_indexes() -> set[str]:
    return {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name is not None
    }


def all_unique_constraints() -> set[str]:
    return {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name is not None
    }


def all_check_constraints() -> set[str]:
    return {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }


def test_schema_contains_only_v1_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_has_uuid_primary_key() -> None:
    for table in Base.metadata.tables.values():
        assert [column.name for column in table.primary_key.columns] == ["id"]
        assert isinstance(table.c.id.type, PostgreSQLUUID)


def test_all_timestamps_are_timezone_aware() -> None:
    timestamp_columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime)
    ]

    assert timestamp_columns
    assert all(column.type.timezone for column in timestamp_columns)


def test_robux_and_financial_column_types() -> None:
    assert isinstance(ClientOrder.__table__.c.requested_robux.type, BigInteger)
    assert isinstance(ClientOrder.__table__.c.customer_receives.type, BigInteger)
    assert isinstance(MarketplaceOrder.__table__.c.requested_robux.type, BigInteger)
    assert isinstance(MarketplaceOrder.__table__.c.purchased_robux.type, BigInteger)
    assert isinstance(MarketplaceOrder.__table__.c.remaining_robux.type, BigInteger)

    for column_name in (
        "marketplace_rate_limit",
        "marketplace_cost",
        "marketplace_commission",
        "final_cost_usd",
        "final_cost_local_currency",
        "usd_exchange_rate",
        "preferred_rate",
        "executed_rate",
    ):
        assert isinstance(ClientOrder.__table__.c[column_name].type, Numeric)


def test_documented_indexes_are_present() -> None:
    assert all_indexes() == EXPECTED_INDEXES


def test_documented_unique_constraints_are_present() -> None:
    assert all_unique_constraints() == EXPECTED_UNIQUE_CONSTRAINTS


def test_single_active_marketplace_order_index_is_partial_and_unique() -> None:
    index = next(
        item
        for item in MarketplaceOrder.__table__.indexes
        if item.name == "uq_marketplace_orders_one_active_per_client_order"
    )

    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == "marketplace_status = 'active'"


def test_customer_roblox_user_id_is_nullable_positive_and_unique_when_present() -> None:
    column = Customer.__table__.c.roblox_user_id
    index = next(
        item
        for item in Customer.__table__.indexes
        if item.name == "uq_customers_roblox_user_id_not_null"
    )
    check = next(
        item
        for item in Customer.__table__.constraints
        if item.name == "ck_customers_roblox_user_id_positive"
    )

    assert column.nullable is True
    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == "roblox_user_id IS NOT NULL"
    assert str(check.sqltext) == "roblox_user_id IS NULL OR roblox_user_id > 0"


def test_core_check_constraints_are_present() -> None:
    check_constraints = all_check_constraints()

    assert "ck_customers_current_username_not_empty" in check_constraints
    assert "ck_client_orders_completed_order_fields" in check_constraints
    assert "ck_client_orders_requeue_attempts_nonnegative" in check_constraints
    assert "ck_client_orders_preferred_rate_valid" in check_constraints
    assert "ck_client_orders_preferred_timeout_positive" in check_constraints
    assert "ck_client_orders_executed_rate_positive" in check_constraints
    assert "ck_marketplace_orders_robux_amounts_consistent" in check_constraints
    assert "ck_notifications_delivery_timestamp_consistent" in check_constraints
    assert "ck_system_settings_reorder_interval_minimum" in check_constraints
    assert "ck_system_settings_auto_requeue_delay_minimum" in check_constraints
    assert "ck_system_settings_marketplace_commission_rate" in check_constraints
    assert "ck_system_settings_preferred_purchase_rate_valid" in check_constraints
    assert "ck_system_settings_preferred_timeout_positive" in check_constraints
    assert "ck_system_settings_low_balance_threshold_nonnegative" in check_constraints
    assert "ck_system_settings_critical_balance_threshold_valid" in check_constraints
    assert "ck_system_settings_sync_interval_positive" in check_constraints


def test_documented_relationships_are_present() -> None:
    assert set(Customer.__mapper__.relationships.keys()) == {
        "username_history",
        "place_id_history",
        "client_orders",
    }
    assert set(ClientOrder.__mapper__.relationships.keys()) == {
        "customer",
        "marketplace_orders",
        "timeline_events",
        "notifications",
    }
    assert set(MarketplaceOrder.__mapper__.relationships.keys()) == {"client_order"}
    assert set(CustomerUsernameHistory.__mapper__.relationships.keys()) == {"customer"}
    assert set(CustomerPlaceIDHistory.__mapper__.relationships.keys()) == {"customer"}
    assert set(Notification.__mapper__.relationships.keys()) == {"client_order"}


def test_foreign_key_delete_policies_preserve_history() -> None:
    foreign_keys = {
        (table.name, foreign_key.parent.name): foreign_key.ondelete
        for table in Base.metadata.tables.values()
        for foreign_key in table.foreign_keys
    }

    assert foreign_keys == {
        ("client_orders", "customer_id"): "RESTRICT",
        ("customer_place_id_history", "customer_id"): "RESTRICT",
        ("customer_username_history", "customer_id"): "RESTRICT",
        ("marketplace_orders", "client_order_id"): "RESTRICT",
        ("notifications", "client_order_id"): "SET NULL",
        ("timeline_events", "client_order_id"): "RESTRICT",
    }
