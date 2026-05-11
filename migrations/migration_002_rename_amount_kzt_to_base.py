"""Migration 002: rename amount_kzt to amount_base across all tables."""

from __future__ import annotations

import sqlite3

MIGRATION_ID = "002"


def up(conn: sqlite3.Connection) -> None:
    """Apply migration 002 if old column names are still present."""
    record_columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(records)").fetchall()]
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
