from __future__ import annotations

import sqlite3
from pathlib import Path

from migrations.migration_002_rename_amount_kzt_to_base import up as migrate_002


def _create_legacy_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE records (
            id INTEGER PRIMARY KEY,
            amount_kzt REAL NOT NULL,
            amount_kzt_minor INTEGER
        );
        CREATE TABLE transfers (
            id INTEGER PRIMARY KEY,
            amount_kzt REAL NOT NULL,
            amount_kzt_minor INTEGER
        );
        CREATE TABLE mandatory_expenses (
            id INTEGER PRIMARY KEY,
            amount_kzt REAL NOT NULL,
            amount_kzt_minor INTEGER
        );
        CREATE TABLE budgets (
            id INTEGER PRIMARY KEY,
            limit_kzt REAL NOT NULL,
            limit_kzt_minor INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()


def _create_legacy_schema_without_minor_columns(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE records (
            id INTEGER PRIMARY KEY,
            amount_kzt REAL NOT NULL
        );
        CREATE TABLE transfers (
            id INTEGER PRIMARY KEY,
            amount_kzt REAL NOT NULL
        );
        CREATE TABLE mandatory_expenses (
            id INTEGER PRIMARY KEY,
            amount_kzt REAL NOT NULL
        );
        CREATE TABLE budgets (
            id INTEGER PRIMARY KEY,
            limit_kzt REAL NOT NULL
        );
        """
    )
    conn.commit()


def test_migration_002_renames_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        _create_legacy_schema(conn)
        migrate_002(conn)
        columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(records)").fetchall()]
        assert "amount_base" in columns
        assert "amount_kzt" not in columns


def test_migration_002_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        _create_legacy_schema(conn)
        migrate_002(conn)
        migrate_002(conn)
        columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(budgets)").fetchall()]
        assert "limit_base" in columns
        assert "limit_kzt" not in columns


def test_base_currency_stored_in_schema_meta(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        _create_legacy_schema(conn)
        migrate_002(conn)
        row = conn.execute("SELECT value FROM schema_meta WHERE key = 'base_currency'").fetchone()
        assert row is not None
        assert str(row[0]) == "KZT"


def test_migration_002_adds_missing_legacy_minor_columns_before_rename(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_missing_minor.db"
    with sqlite3.connect(db_path) as conn:
        _create_legacy_schema_without_minor_columns(conn)
        migrate_002(conn)

        record_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(records)")}
        transfer_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(transfers)")}
        mandatory_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(mandatory_expenses)")
        }
        budget_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(budgets)")}

        assert "amount_base" in record_columns
        assert "amount_base_minor" in record_columns
        assert "amount_base" in transfer_columns
        assert "amount_base_minor" in transfer_columns
        assert "amount_base" in mandatory_columns
        assert "amount_base_minor" in mandatory_columns
        assert "limit_base" in budget_columns
        assert "limit_base_minor" in budget_columns
