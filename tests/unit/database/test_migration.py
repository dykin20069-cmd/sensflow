"""Tests for the initial Alembic migration."""

from io import StringIO

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def alembic_config(output: StringIO | None = None) -> Config:
    config = Config("alembic.ini", stdout=output, output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://localhost/sensflow")
    return config


def test_initial_migration_is_the_only_revision() -> None:
    scripts = ScriptDirectory.from_config(alembic_config())
    revisions = list(scripts.walk_revisions())

    assert len(revisions) == 1
    assert revisions[0].revision == "20260806_0001"
    assert revisions[0].down_revision is None


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
    ):
        assert f"CREATE TABLE {table_name}" in sql
    assert "CREATE UNIQUE INDEX uq_marketplace_orders_one_active_per_client_order" in sql
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
