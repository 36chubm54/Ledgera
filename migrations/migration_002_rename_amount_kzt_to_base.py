"""Migration 002: rename amount_kzt to amount_base across all tables."""

from __future__ import annotations

import sqlite3

MIGRATION_ID = "002"


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_legacy_minor_columns(conn: sqlite3.Connection) -> None:
    table_specs = (
        ("records", "amount_kzt", "amount_kzt_minor"),
        ("transfers", "amount_kzt", "amount_kzt_minor"),
        ("mandatory_expenses", "amount_kzt", "amount_kzt_minor"),
        ("budgets", "limit_kzt", "limit_kzt_minor"),
    )
    for table, amount_column, minor_column in table_specs:
        columns = _column_names(conn, table)
        if amount_column not in columns or minor_column in columns:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {minor_column} INTEGER NOT NULL DEFAULT 0")


def up(conn: sqlite3.Connection) -> None:
    """Apply migration 002 if old column names are still present."""
    record_columns = _column_names(conn, "records")
    if "amount_base" in record_columns:
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('base_currency', 'KZT')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_migration', ?)",
            (MIGRATION_ID,),
        )
        conn.commit()
        return

    _ensure_legacy_minor_columns(conn)

    conn.executescript(
        """
        ALTER TABLE records RENAME COLUMN amount_kzt TO amount_base;
        ALTER TABLE records RENAME COLUMN amount_kzt_minor TO amount_base_minor;
        ALTER TABLE transfers RENAME COLUMN amount_kzt TO amount_base;
        ALTER TABLE transfers RENAME COLUMN amount_kzt_minor TO amount_base_minor;
        ALTER TABLE mandatory_expenses RENAME COLUMN amount_kzt TO amount_base;
        ALTER TABLE mandatory_expenses RENAME COLUMN amount_kzt_minor TO amount_base_minor;
        ALTER TABLE budgets RENAME COLUMN limit_kzt TO limit_base;
        ALTER TABLE budgets RENAME COLUMN limit_kzt_minor TO limit_base_minor;
        """
    )
    conn.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('base_currency', 'KZT')")
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_migration', ?)",
        (MIGRATION_ID,),
    )
    conn.commit()
