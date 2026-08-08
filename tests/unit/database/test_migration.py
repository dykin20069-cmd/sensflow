"""Tests for the initial Alembic migration."""

from io import StringIO

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def alembic_config(output: StringIO | None = None) -> Config:
    config = Config("alembic.ini", stdout=output, output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://localhost/sensflow")
    return config


def test_migration_chain_has_nullable_customer_identity_revision() -> None:
    scripts = ScriptDirectory.from_config(alembic_config())
    revisions = list(scripts.walk_revisions())

    assert [item.revision for item in revisions] == [
        "20260808_0006",
        "20260808_0005",
        "20260807_0004",
        "20260807_0003",
        "20260807_0002",
        "20260806_0001",
    ]
    assert revisions[0].down_revision == "20260808_0005"
    assert revisions[1].down_revision == "20260807_0004"
    assert revisions[2].down_revision == "20260807_0003"
    assert revisions[3].down_revision == "20260807_0002"
    assert revisions[4].down_revision == "20260806_0001"
    assert revisions[5].down_revision is None


def test_initial_migration_renders_complete_upgrade_sql() -> None:
    output = StringIO()

    command.upgrade(alembic_config(output), "head", sql=True)

    sql = output.getvalue()
    for table_name in (
        "customers",
        "customer_username_history",
        "customer_place_id_history",
        "client_orders",
        "marketplace_orders",
        "timeline_events",
        "notifications",
        "statistics",
        "system_settings",
        "system_logs",
        "user_place_cache",
    ):
        assert f"CREATE TABLE {table_name}" in sql
    assert "CREATE UNIQUE INDEX uq_marketplace_orders_one_active_per_client_order" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_roblox_user_id_not_null" in sql
    assert "WHERE roblox_user_id IS NOT NULL" in sql
    assert "ALTER TABLE customers ALTER COLUMN roblox_user_id DROP NOT NULL" in sql
    assert "ALTER TABLE customers DROP CONSTRAINT IF EXISTS uq_customers_roblox_user_id" in sql
    assert (
        "ALTER TABLE customers "
        "DROP CONSTRAINT IF EXISTS ck_customers_roblox_user_id_positive" in sql
    )
    assert "ck_customers_ck_customers_roblox_user_id_positive" not in sql
    assert "CREATE UNIQUE INDEX uq_user_place_cache_roblox_username_lower" in sql
    assert "TYPE NUMERIC(8, 3)" in sql
    assert "SET automatic_reorder_interval_seconds = 0.3" in sql
    assert "automatic_reorder_interval_seconds >= 0.3" in sql
    assert "ADD VALUE IF NOT EXISTS 'stock_available'" in sql
    assert "ADD COLUMN automatic_requeue_enabled BOOLEAN DEFAULT true NOT NULL" in sql
    assert "ADD COLUMN last_requeue_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ADD COLUMN requeue_attempts INTEGER DEFAULT 0 NOT NULL" in sql
    assert "ADD COLUMN auto_requeue_delay_seconds NUMERIC(8, 3) DEFAULT 5 NOT NULL" in sql
    assert "auto_requeue_delay_seconds >= 0.3" in sql
    assert "marketplace_commission = marketplace_commission / 100" in sql
    assert "marketplace_commission >= 0 AND marketplace_commission <= 1" in sql
    assert "ADD VALUE IF NOT EXISTS 'low_balance'" in sql
    assert "ADD VALUE IF NOT EXISTS 'critical_balance'" in sql
    assert "ADD COLUMN preferred_rate NUMERIC(20, 8)" in sql
    assert "ADD COLUMN executed_rate NUMERIC(20, 8)" in sql
    assert "WHERE current_status <> 'completed'" in sql
    assert "SET executed_rate = final_cost_usd" not in sql
    assert "ADD COLUMN preferred_purchase_rate NUMERIC(20, 8)" in sql
    assert "preferred_purchase_rate > 0" in sql
    assert "critical_balance_threshold <= low_balance_threshold" in sql
    assert "ADD COLUMN preferred_mode_default BOOLEAN" in sql
    assert "application_timezone = 'Europe/Moscow'" in sql
    assert "CREATE UNIQUE INDEX uq_system_settings_singleton" in sql
    assert sql.count("CREATE FUNCTION reject_protected_row_change()") == 1
    for trigger_name in (
        "trg_customer_username_history_append_only",
        "trg_customer_place_id_history_append_only",
        "trg_timeline_events_append_only",
        "trg_system_logs_append_only",
        "trg_customers_no_delete",
        "trg_marketplace_orders_no_delete",
        "trg_client_orders_completed_immutable",
    ):
        assert f"CREATE TRIGGER {trigger_name}" in sql
    assert "WHEN (OLD.current_status = 'completed')" in sql


def test_initial_migration_renders_complete_downgrade_sql() -> None:
    output = StringIO()

    command.downgrade(alembic_config(output), "20260806_0001:base", sql=True)

    sql = output.getvalue()
    assert "DROP TABLE customers" in sql
    assert "DROP TYPE client_order_status" in sql
    assert "DROP FUNCTION reject_protected_row_change()" in sql


def test_nullable_customer_identity_migration_has_guarded_downgrade() -> None:
    output = StringIO()

    command.downgrade(
        alembic_config(output),
        "20260807_0002:20260806_0001",
        sql=True,
    )

    sql = output.getvalue()
    assert "Cannot downgrade while Customers with NULL roblox_user_id exist" in sql
    assert "ALTER TABLE customers ALTER COLUMN roblox_user_id SET NOT NULL" in sql


def test_place_cache_migration_has_guarded_interval_downgrade() -> None:
    output = StringIO()

    command.downgrade(
        alembic_config(output),
        "20260807_0003:20260807_0002",
        sql=True,
    )

    sql = output.getvalue()
    assert "Cannot downgrade while subsecond automatic reorder intervals exist" in sql
    assert "DROP TABLE user_place_cache" in sql
    assert "TYPE INTEGER" in sql


def test_final_v1_migration_has_guarded_notification_downgrade() -> None:
    output = StringIO()

    command.downgrade(
        alembic_config(output),
        "20260807_0004:20260807_0003",
        sql=True,
    )

    sql = output.getvalue()
    assert "Cannot downgrade while final V1 notification rows exist" in sql
    assert "DROP COLUMN auto_requeue_delay_seconds" in sql
    assert "DROP COLUMN automatic_requeue_enabled" in sql
    assert "DROP TYPE notification_type_final_v1" in sql


def test_v2_1_migration_has_safe_backfill_and_guarded_downgrade() -> None:
    output = StringIO()

    command.downgrade(
        alembic_config(output),
        "20260808_0005:20260807_0004",
        sql=True,
    )

    sql = output.getvalue()
    assert "Cannot downgrade while V2.1 notification rows exist" in sql
    assert "DROP COLUMN executed_rate" in sql
    assert "DROP COLUMN preferred_purchase_rate" in sql
    assert "DROP TYPE notification_type_v2_1" in sql


def test_v2_1_1_downgrade_only_removes_the_default_mode_column() -> None:
    output = StringIO()

    command.downgrade(
        alembic_config(output),
        "20260808_0006:20260808_0005",
        sql=True,
    )

    sql = output.getvalue()
    assert "DROP COLUMN preferred_mode_default" in sql
    assert "client_orders" not in sql
