from __future__ import annotations

import re
from pathlib import Path

from domain.validation import VALID_PERIODS


def _schema_sql() -> str:
    return (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text(encoding="utf-8")


def test_schema_period_constraints_match_domain_contract() -> None:
    """
    Contract test: the DB schema should accept the same `period` values as the domain.

    We keep domain validation even with DB CHECK constraints:
    - domain: early, user-friendly errors (imports/GUI), no DB dependency
    - DB: last line of defense for integrity (manual edits, legacy code paths)
    """

    periods_sql = ", ".join(f"'{p}'" for p in VALID_PERIODS)
    schema = _schema_sql()

    records_period_check = re.search(
        rf"period\s+TEXT\s+CHECK\s*\(\s*period\s+IN\s*\(\s*{re.escape(periods_sql)}\s*\)\s*OR\s*period\s+IS\s+NULL\s*\)",
        schema,
        flags=re.IGNORECASE,
    )
    assert records_period_check is not None

    mandatory_period_check = re.search(
        rf"mandatory_expenses\s*\(.*?period\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*period\s+IN\s*\(\s*{re.escape(periods_sql)}\s*\)\s*\)",
        schema,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert mandatory_period_check is not None


def test_schema_contains_budgets_table_with_expected_columns() -> None:
    schema = _schema_sql()

    assert "CREATE TABLE IF NOT EXISTS budgets" in schema
    assert "category TEXT NOT NULL" in schema
    assert "start_date TEXT NOT NULL" in schema
    assert "end_date TEXT NOT NULL" in schema
    assert "limit_base REAL NOT NULL" in schema
    assert "limit_base_minor INTEGER NOT NULL DEFAULT 0" in schema
    assert "include_mandatory INTEGER NOT NULL DEFAULT 0" in schema
    assert "CHECK(start_date <= end_date)" in schema
    assert "CREATE INDEX IF NOT EXISTS idx_budgets_category ON budgets(category);" in schema
    assert (
        "CREATE INDEX IF NOT EXISTS idx_budgets_dates ON budgets(start_date, end_date);" in schema
    )


def test_schema_contains_distribution_tables_with_expected_columns() -> None:
    schema = _schema_sql()

    assert "CREATE TABLE IF NOT EXISTS distribution_items" in schema
    assert "group_name TEXT NOT NULL DEFAULT ''" in schema
    assert "pct REAL NOT NULL DEFAULT 0.0 CHECK(pct >= 0 AND pct <= 100)" in schema
    assert "pct_minor INTEGER NOT NULL DEFAULT 0" in schema
    assert "UNIQUE(name)" in schema

    assert "CREATE TABLE IF NOT EXISTS distribution_subitems" in schema
    assert "item_id INTEGER NOT NULL" in schema
    assert "FOREIGN KEY(item_id) REFERENCES distribution_items(id) ON DELETE CASCADE" in schema
    assert "UNIQUE(item_id, name)" in schema
    assert (
        "CREATE INDEX IF NOT EXISTS idx_dist_items_order ON distribution_items(sort_order);"
        in schema
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_dist_subitems_item ON distribution_subitems(item_id);"
        in schema
    )
    assert "CREATE TABLE IF NOT EXISTS distribution_snapshots" in schema
    assert "month TEXT PRIMARY KEY" in schema
    assert "auto_fixed INTEGER NOT NULL DEFAULT 0" in schema
    assert "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP" in schema
    assert "CREATE TABLE IF NOT EXISTS distribution_snapshot_values" in schema
    assert "snapshot_month TEXT NOT NULL" in schema
    assert "column_key TEXT NOT NULL" in schema
    assert "column_label TEXT NOT NULL" in schema
    assert "column_order INTEGER NOT NULL" in schema
    assert "value_text TEXT NOT NULL" in schema
    assert "PRIMARY KEY(snapshot_month, column_key)" in schema
    assert (
        "FOREIGN KEY(snapshot_month) REFERENCES distribution_snapshots(month) ON DELETE CASCADE"
        in schema
    )
    assert "CREATE INDEX IF NOT EXISTS idx_dist_snapshot_values_month_order" in schema


def test_schema_contains_debt_tables_with_expected_columns() -> None:
    schema = _schema_sql()

    assert "CREATE TABLE IF NOT EXISTS debts" in schema
    assert "contact_name TEXT NOT NULL" in schema
    assert "kind TEXT NOT NULL CHECK(kind IN ('debt', 'loan'))" in schema
    assert "total_amount_minor INTEGER NOT NULL CHECK(total_amount_minor > 0)" in schema
    assert "remaining_amount_minor INTEGER NOT NULL CHECK(" in schema
    assert "interest_rate REAL NOT NULL DEFAULT 0 CHECK(interest_rate >= 0)" in schema
    assert "status TEXT NOT NULL CHECK(status IN ('open', 'closed'))" in schema
    assert "created_at TEXT NOT NULL CHECK(created_at GLOB" in schema
    assert "CHECK(status = 'open' OR remaining_amount_minor = 0)" in schema

    assert "CREATE TABLE IF NOT EXISTS debt_payments" in schema
    assert "debt_id INTEGER NOT NULL" in schema
    assert "record_id INTEGER DEFAULT NULL" in schema
    assert "operation_type TEXT NOT NULL CHECK(" in schema
    assert "principal_paid_minor INTEGER NOT NULL CHECK(principal_paid_minor > 0)" in schema
    assert "is_write_off INTEGER NOT NULL DEFAULT 0 CHECK(is_write_off IN (0, 1))" in schema
    assert "payment_date TEXT NOT NULL CHECK(payment_date GLOB" in schema
    assert "FOREIGN KEY(debt_id) REFERENCES debts(id) ON UPDATE CASCADE ON DELETE CASCADE" in schema
    assert (
        "FOREIGN KEY(record_id) REFERENCES records(id) ON UPDATE CASCADE ON DELETE SET NULL"
        in schema
    )

    assert "related_debt_id INTEGER DEFAULT NULL" in schema
    assert (
        "FOREIGN KEY(related_debt_id) REFERENCES debts(id) ON UPDATE CASCADE ON DELETE SET NULL"
        in schema
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_records_related_debt_id ON records(related_debt_id);"
        in schema
    )
    assert "CREATE INDEX IF NOT EXISTS idx_debts_contact_name ON debts(contact_name);" in schema
    assert "CREATE INDEX IF NOT EXISTS idx_debts_status ON debts(status);" in schema
    assert (
        "CREATE INDEX IF NOT EXISTS idx_debt_payments_debt_id ON debt_payments(debt_id);" in schema
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_debt_payments_record_id ON debt_payments(record_id);"
        in schema
    )


def test_schema_contains_assets_and_goals_tables_with_expected_columns() -> None:
    schema = _schema_sql()

    assert "CREATE TABLE IF NOT EXISTS assets" in schema
    assert "name TEXT NOT NULL" in schema
    assert "category TEXT NOT NULL CHECK(category IN ('bank', 'crypto', 'cash', 'other'))" in schema
    assert "is_active INTEGER NOT NULL DEFAULT 1" in schema
    assert "created_at TEXT NOT NULL CHECK(created_at GLOB" in schema

    assert "CREATE TABLE IF NOT EXISTS asset_snapshots" in schema
    assert "asset_id INTEGER NOT NULL" in schema
    assert "snapshot_date TEXT NOT NULL CHECK(" in schema
    assert "value_minor INTEGER NOT NULL CHECK(value_minor >= 0)" in schema
    assert (
        "FOREIGN KEY(asset_id) REFERENCES assets(id) ON UPDATE CASCADE ON DELETE CASCADE" in schema
    )
    assert "UNIQUE(asset_id, snapshot_date)" in schema

    assert "CREATE TABLE IF NOT EXISTS goals" in schema
    assert "title TEXT NOT NULL" in schema
    assert "target_amount_minor INTEGER NOT NULL CHECK(target_amount_minor > 0)" in schema
    assert "target_date TEXT DEFAULT NULL CHECK(" in schema
    assert "is_completed INTEGER NOT NULL DEFAULT 0 CHECK(is_completed IN (0, 1))" in schema

    assert "CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);" in schema
    assert "CREATE INDEX IF NOT EXISTS idx_assets_is_active ON assets(is_active);" in schema
    assert (
        "CREATE INDEX IF NOT EXISTS idx_asset_snapshots_asset_date "
        "ON asset_snapshots(asset_id, snapshot_date DESC);" in schema
    )
    assert "CREATE INDEX IF NOT EXISTS idx_goals_completed ON goals(is_completed);" in schema
    assert "CREATE INDEX IF NOT EXISTS idx_goals_target_date ON goals(target_date);" in schema
