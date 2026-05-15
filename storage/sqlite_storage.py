from __future__ import annotations

import sqlite3
import threading
import typing
from datetime import date as dt_date
from pathlib import Path

from app_paths import get_schema_sql_path
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from migrations.migration_002_rename_amount_kzt_to_base import up as migrate_002
from utils.money import minor_to_money, rate_to_text, to_minor_units, to_money_float, to_rate_float

from .base import Storage


class _LockedCursor:
    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock) -> None:
        self._cursor = cursor
        self._lock = lock
        self._released = False

    def _release(self) -> None:
        if self._released:
            return
        self._released = True
        self._lock.release()

    def fetchone(self) -> sqlite3.Row | None:
        try:
            return self._cursor.fetchone()
        finally:
            self._release()

    def fetchall(self) -> list[sqlite3.Row]:
        try:
            return self._cursor.fetchall()
        finally:
            self._release()

    def fetchmany(self, size: int | None = None) -> list[sqlite3.Row]:
        rows = self._cursor.fetchmany() if size is None else self._cursor.fetchmany(size)
        if not rows:
            self._release()
        return rows

    def close(self) -> None:
        try:
            self._cursor.close()
        finally:
            self._release()

    def __iter__(self) -> typing.Iterator[sqlite3.Row]:
        try:
            yield from self._cursor
        finally:
            self._release()

    def __next__(self) -> sqlite3.Row:
        try:
            return next(self._cursor)
        except StopIteration:
            self._release()
            raise

    def __getattr__(self, name: str) -> typing.Any:
        return getattr(self._cursor, name)

    def __del__(self) -> None:
        self._release()


class _SynchronizedConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def __enter__(self):
        self._lock.acquire()
        try:
            self._conn.__enter__()
        except (sqlite3.Error, RuntimeError):
            self._lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._conn.__exit__(exc_type, exc, tb)
        finally:
            self._lock.release()

    def _execute_locked(self, method_name: str, *args) -> sqlite3.Cursor | _LockedCursor:
        self._lock.acquire()
        try:
            cursor = getattr(self._conn, method_name)(*args)
        except (sqlite3.Error, RuntimeError):
            self._lock.release()
            raise
        if cursor.description is None:
            self._lock.release()
            return cursor
        return _LockedCursor(cursor, self._lock)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor | _LockedCursor:
        return self._execute_locked("execute", sql, params)

    def executemany(self, sql: str, seq_of_parameters) -> sqlite3.Cursor:
        self._lock.acquire()
        try:
            return self._conn.executemany(sql, seq_of_parameters)
        finally:
            self._lock.release()

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        self._lock.acquire()
        try:
            return self._conn.executescript(sql_script)
        finally:
            self._lock.release()

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def backup(self, target, *args, **kwargs) -> None:
        raw_target = getattr(target, "_conn", target)
        with self._lock:
            self._conn.backup(raw_target, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


class SQLiteStorage(Storage):
    """SQLite-backed storage adapter without domain/business logic."""

    def __init__(self, db_path: str = "records.db") -> None:
        self._db_path = db_path
        raw_conn = sqlite3.connect(db_path, check_same_thread=False)
        raw_conn.row_factory = sqlite3.Row
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        raw_conn.execute("PRAGMA journal_mode = WAL;")
        self._conn = _SynchronizedConnection(raw_conn)

    def close(self) -> None:
        self._conn.close()

    def set_sqlite_sequence(self, table: str, seq: int | None = None) -> None:
        table_name = str(table)
        next_seq = int(seq) if seq is not None else 0
        if seq is None:
            row = self.query_one(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
            next_seq = int(row[0]) if row else 0
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table_name,))
        self._conn.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)",
            (table_name, int(next_seq)),
        )

    def initialize_schema(self, schema_path: str | None = None) -> None:
        if schema_path is None:
            schema_path = str(get_schema_sql_path())
        self._ensure_pre_schema_compatibility()
        schema = Path(schema_path).read_text(encoding="utf-8")
        self._conn.executescript(schema)
        migrate_002(self._conn._conn)
        self._ensure_money_precision_columns()
        self._conn.commit()

    def _table_exists(self, table: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (str(table),),
        ).fetchone()
        return row is not None

    def _ensure_pre_schema_compatibility(self) -> None:
        if self._table_exists("records"):
            self._add_column_if_missing("records", "related_debt_id", "INTEGER DEFAULT NULL")
        if self._table_exists("budgets"):
            self._add_column_if_missing("budgets", "scope_type", "TEXT NOT NULL DEFAULT 'category'")
            self._add_column_if_missing("budgets", "scope_value", "TEXT NOT NULL DEFAULT ''")
        if self._table_exists("tags"):
            self._add_column_if_missing("tags", "color", "TEXT NOT NULL DEFAULT ''")
            self._add_column_if_missing("tags", "usage_count", "INTEGER NOT NULL DEFAULT 0")
            self._add_column_if_missing("tags", "last_used_at", "TEXT NOT NULL DEFAULT ''")

    def _column_names(self, table: str) -> set[str]:
        return {
            str(row["name"]) for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }

    def _add_column_if_missing(self, table: str, column_name: str, definition: str) -> None:
        if column_name in self._column_names(table):
            return
        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {definition}")

    def _backfill_minor_column(self, table: str, real_column: str, minor_column: str) -> None:
        rows = self._conn.execute(
            f"SELECT id, {real_column}, {minor_column} FROM {table}"
        ).fetchall()
        updates: list[tuple[int, int]] = []
        for row in rows:
            if int(row[minor_column] or 0) != 0:
                continue
            updates.append((to_minor_units(row[real_column] or 0.0), int(row["id"])))
        if updates:
            self._conn.executemany(
                f"UPDATE {table} SET {minor_column} = ? WHERE id = ?",
                updates,
            )

    def _ensure_money_precision_columns(self) -> None:
        self._add_column_if_missing("budgets", "scope_type", "TEXT NOT NULL DEFAULT 'category'")
        self._add_column_if_missing("budgets", "scope_value", "TEXT NOT NULL DEFAULT ''")
        if self._table_exists("tags"):
            self._add_column_if_missing("tags", "color", "TEXT NOT NULL DEFAULT ''")
            self._add_column_if_missing("tags", "usage_count", "INTEGER NOT NULL DEFAULT 0")
            self._add_column_if_missing("tags", "last_used_at", "TEXT NOT NULL DEFAULT ''")
        self._conn.execute(
            """
            UPDATE budgets
            SET scope_value = category
            WHERE length(trim(COALESCE(scope_value, ''))) = 0
            """
        )
        self._add_column_if_missing("wallets", "initial_balance_minor", "INTEGER DEFAULT NULL")
        self._add_column_if_missing("transfers", "amount_original_minor", "INTEGER DEFAULT NULL")
        self._add_column_if_missing("transfers", "rate_at_operation_text", "TEXT DEFAULT NULL")
        self._add_column_if_missing("transfers", "amount_base_minor", "INTEGER DEFAULT NULL")
        self._add_column_if_missing("records", "amount_original_minor", "INTEGER DEFAULT NULL")
        self._add_column_if_missing("records", "rate_at_operation_text", "TEXT DEFAULT NULL")
        self._add_column_if_missing("records", "amount_base_minor", "INTEGER DEFAULT NULL")
        self._add_column_if_missing(
            "mandatory_expenses", "amount_original_minor", "INTEGER DEFAULT NULL"
        )
        self._add_column_if_missing(
            "mandatory_expenses", "rate_at_operation_text", "TEXT DEFAULT NULL"
        )
        self._add_column_if_missing(
            "mandatory_expenses", "amount_base_minor", "INTEGER DEFAULT NULL"
        )
        self._backfill_minor_column("wallets", "initial_balance", "initial_balance_minor")
        self._backfill_minor_column("transfers", "amount_original", "amount_original_minor")
        self._backfill_minor_column("transfers", "amount_base", "amount_base_minor")
        self._backfill_minor_column("records", "amount_original", "amount_original_minor")
        self._backfill_minor_column("records", "amount_base", "amount_base_minor")
        self._backfill_minor_column(
            "mandatory_expenses", "amount_original", "amount_original_minor"
        )
        self._backfill_minor_column("mandatory_expenses", "amount_base", "amount_base_minor")
        self._backfill_rate_text("transfers")
        self._backfill_rate_text("records")
        self._backfill_rate_text("mandatory_expenses")

    @staticmethod
    def _money_from_row(row: sqlite3.Row, real_column: str, minor_column: str) -> float:
        real_value = row[real_column]
        minor_value = row[minor_column] if minor_column in row.keys() else None
        if minor_value is not None:
            if int(minor_value) != 0 or to_money_float(real_value or 0.0) == 0.0:
                return minor_to_money(minor_value)
        return to_money_float(real_value or 0.0)

    def _backfill_rate_text(self, table: str) -> None:
        rows = self._conn.execute(
            f"SELECT id, rate_at_operation, rate_at_operation_text FROM {table}"
        ).fetchall()
        updates: list[tuple[str, int]] = []
        for row in rows:
            if str(row["rate_at_operation_text"] or "").strip():
                continue
            updates.append((rate_to_text(row["rate_at_operation"] or 1.0), int(row["id"])))
        if updates:
            self._conn.executemany(
                f"UPDATE {table} SET rate_at_operation_text = ? WHERE id = ?",
                updates,
            )

    @staticmethod
    def _rate_from_row(row: sqlite3.Row) -> float:
        if "rate_at_operation_text" in row.keys():
            rate_text = str(row["rate_at_operation_text"] or "").strip()
            if rate_text:
                return to_rate_float(rate_text)
        return to_rate_float(row["rate_at_operation"] or 1.0)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor | _LockedCursor:
        return self._conn.execute(sql, params)

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def begin(self) -> None:
        self._conn.execute("BEGIN")

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def connection_is_available(self) -> bool:
        self._conn.execute("SELECT 1")
        return True

    def get_wallets(self) -> list[Wallet]:
        rows = self._conn.execute(
            """
            SELECT
                id,
                name,
                currency,
                initial_balance,
                initial_balance_minor,
                system,
                allow_negative,
                is_active
            FROM wallets
            ORDER BY id
            """
        ).fetchall()
        return [
            Wallet(
                id=int(row["id"]),
                name=str(row["name"]),
                currency=str(row["currency"]),
                initial_balance=self._money_from_row(
                    row, "initial_balance", "initial_balance_minor"
                ),
                system=bool(row["system"]),
                allow_negative=bool(row["allow_negative"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def save_wallet(self, wallet: Wallet) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM wallets WHERE id = ?",
            (int(wallet.id),),
        ).fetchone()
        if row is not None:
            self._conn.execute(
                """
                UPDATE wallets
                SET
                    name = ?,
                    currency = ?,
                    initial_balance = ?,
                    initial_balance_minor = ?,
                    system = ?,
                    allow_negative = ?,
                    is_active = ?
                WHERE id = ?
                """,
                (
                    wallet.name,
                    wallet.currency.upper(),
                    to_money_float(wallet.initial_balance),
                    to_minor_units(wallet.initial_balance),
                    int(bool(wallet.system)),
                    int(bool(wallet.allow_negative)),
                    int(bool(wallet.is_active)),
                    int(wallet.id),
                ),
            )
        else:
            cursor = self._conn.execute(
                """
                INSERT INTO wallets (
                    id,
                    name,
                    currency,
                    initial_balance,
                    initial_balance_minor,
                    system,
                    allow_negative,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(wallet.id),
                    wallet.name,
                    wallet.currency.upper(),
                    to_money_float(wallet.initial_balance),
                    to_minor_units(wallet.initial_balance),
                    int(bool(wallet.system)),
                    int(bool(wallet.allow_negative)),
                    int(bool(wallet.is_active)),
                ),
            )
            wallet_id = cursor.lastrowid
            if wallet_id is None:
                raise RuntimeError("Failed to obtain lastrowid for wallets insert")
        self._conn.commit()

    def get_records(self) -> list[Record]:
        rows = self._conn.execute(
            """
            SELECT
                id,
                type,
                date,
                wallet_id,
                transfer_id,
                related_debt_id,
                amount_original,
                amount_original_minor,
                currency,
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                category,
                description,
                period
            FROM records
            ORDER BY id
            """
        ).fetchall()
        records: list[Record] = []
        for row in rows:
            payload = {
                "id": int(row["id"]),
                "date": str(row["date"]),
                "wallet_id": int(row["wallet_id"]),
                "transfer_id": int(row["transfer_id"]) if row["transfer_id"] is not None else None,
                "related_debt_id": (
                    int(row["related_debt_id"]) if row["related_debt_id"] is not None else None
                ),
                "amount_original": self._money_from_row(
                    row, "amount_original", "amount_original_minor"
                ),
                "currency": str(row["currency"]).upper(),
                "rate_at_operation": self._rate_from_row(row),
                "amount_base": self._money_from_row(row, "amount_base", "amount_base_minor"),
                "category": str(row["category"]),
                "description": str(row["description"] or ""),
            }
            record_type = str(row["type"])
            if record_type == "income":
                records.append(IncomeRecord(**payload))
            elif record_type == "expense":
                records.append(ExpenseRecord(**payload))
            elif record_type == "mandatory_expense":
                records.append(
                    MandatoryExpenseRecord(
                        **payload,
                        period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
                    )
                )
        return records

    def save_record(self, record: Record) -> None:
        period = record.period if isinstance(record, MandatoryExpenseRecord) else None
        row = self._conn.execute(
            "SELECT 1 FROM records WHERE id = ?",
            (int(record.id),),
        ).fetchone()
        if row is not None:
            self._conn.execute(
                """
                UPDATE records
                SET
                    type = ?,
                    date = ?,
                    wallet_id = ?,
                    transfer_id = ?,
                    related_debt_id = ?,
                    amount_original = ?,
                    amount_original_minor = ?,
                    currency = ?,
                    rate_at_operation = ?,
                    rate_at_operation_text = ?,
                    amount_base = ?,
                    amount_base_minor = ?,
                    category = ?,
                    description = ?,
                    period = ?
                WHERE id = ?
                """,
                (
                    self._record_type(record),
                    self._date_as_text(record.date),
                    int(record.wallet_id),
                    int(record.transfer_id) if record.transfer_id is not None else None,
                    int(record.related_debt_id) if record.related_debt_id is not None else None,
                    to_money_float(record.amount_original or 0.0),
                    to_minor_units(record.amount_original or 0.0),
                    str(record.currency).upper(),
                    to_rate_float(record.rate_at_operation),
                    rate_to_text(record.rate_at_operation),
                    to_money_float(record.amount_base or 0.0),
                    to_minor_units(record.amount_base or 0.0),
                    str(record.category),
                    str(record.description or ""),
                    str(period) if period is not None else None,
                    int(record.id),
                ),
            )
        else:
            cursor = self._conn.execute(
                """
                INSERT INTO records (
                    id,
                    type,
                    date,
                    wallet_id,
                    transfer_id,
                    related_debt_id,
                    amount_original,
                    amount_original_minor,
                    currency,
                    rate_at_operation,
                    rate_at_operation_text,
                    amount_base,
                    amount_base_minor,
                    category,
                    description,
                    period
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(record.id),
                    self._record_type(record),
                    self._date_as_text(record.date),
                    int(record.wallet_id),
                    int(record.transfer_id) if record.transfer_id is not None else None,
                    int(record.related_debt_id) if record.related_debt_id is not None else None,
                    to_money_float(record.amount_original or 0.0),
                    to_minor_units(record.amount_original or 0.0),
                    str(record.currency).upper(),
                    to_rate_float(record.rate_at_operation),
                    rate_to_text(record.rate_at_operation),
                    to_money_float(record.amount_base or 0.0),
                    to_minor_units(record.amount_base or 0.0),
                    str(record.category),
                    str(record.description or ""),
                    str(period) if period is not None else None,
                ),
            )
            record_id = cursor.lastrowid
            if record_id is None:
                raise RuntimeError("Failed to obtain lastrowid for records insert")
        self._conn.commit()

    def get_transfers(self) -> list[Transfer]:
        rows = self._conn.execute(
            """
            SELECT
                id,
                from_wallet_id,
                to_wallet_id,
                date,
                amount_original,
                amount_original_minor,
                currency,
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                description
            FROM transfers
            ORDER BY id
            """
        ).fetchall()
        return [
            Transfer(
                id=int(row["id"]),
                from_wallet_id=int(row["from_wallet_id"]),
                to_wallet_id=int(row["to_wallet_id"]),
                date=str(row["date"]),
                amount_original=self._money_from_row(
                    row, "amount_original", "amount_original_minor"
                ),
                currency=str(row["currency"]).upper(),
                rate_at_operation=self._rate_from_row(row),
                amount_base=self._money_from_row(row, "amount_base", "amount_base_minor"),
                description=str(row["description"] or ""),
            )
            for row in rows
        ]

    def save_transfer(self, transfer: Transfer) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM transfers WHERE id = ?",
            (int(transfer.id),),
        ).fetchone()
        if row is not None:
            self._conn.execute(
                """
                UPDATE transfers
                SET
                    from_wallet_id = ?,
                    to_wallet_id = ?,
                    date = ?,
                    amount_original = ?,
                    amount_original_minor = ?,
                    currency = ?,
                    rate_at_operation = ?,
                    rate_at_operation_text = ?,
                    amount_base = ?,
                    amount_base_minor = ?,
                    description = ?
                WHERE id = ?
                """,
                (
                    int(transfer.from_wallet_id),
                    int(transfer.to_wallet_id),
                    self._date_as_text(transfer.date),
                    to_money_float(transfer.amount_original),
                    to_minor_units(transfer.amount_original),
                    str(transfer.currency).upper(),
                    to_rate_float(transfer.rate_at_operation),
                    rate_to_text(transfer.rate_at_operation),
                    to_money_float(transfer.amount_base),
                    to_minor_units(transfer.amount_base),
                    str(transfer.description or ""),
                    int(transfer.id),
                ),
            )
        else:
            cursor = self._conn.execute(
                """
                INSERT INTO transfers (
                    from_wallet_id,
                    to_wallet_id,
                    date,
                    amount_original,
                    amount_original_minor,
                    currency,
                    rate_at_operation,
                    rate_at_operation_text,
                    amount_base,
                    amount_base_minor,
                    description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(transfer.from_wallet_id),
                    int(transfer.to_wallet_id),
                    self._date_as_text(transfer.date),
                    to_money_float(transfer.amount_original),
                    to_minor_units(transfer.amount_original),
                    str(transfer.currency).upper(),
                    to_rate_float(transfer.rate_at_operation),
                    rate_to_text(transfer.rate_at_operation),
                    to_money_float(transfer.amount_base),
                    to_minor_units(transfer.amount_base),
                    str(transfer.description or ""),
                ),
            )
            transfer_id = cursor.lastrowid
            if transfer_id is None:
                raise RuntimeError("Failed to obtain lastrowid for transfers insert")
        self._conn.commit()

    def get_mandatory_expenses(self) -> list[MandatoryExpenseRecord]:
        columns = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(mandatory_expenses)").fetchall()
        }
        has_date = "date" in columns
        has_auto_pay = "auto_pay" in columns
        select_columns = """
                id,
                wallet_id,
                amount_original,
                amount_original_minor,
                currency,
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                category,
                description,
                period
        """
        if has_date:
            select_columns += ",\n                date"
        if has_auto_pay:
            select_columns += ",\n                auto_pay"
        rows = self._conn.execute(
            f"""
            SELECT
{select_columns}
            FROM mandatory_expenses
            ORDER BY id
            """
        ).fetchall()
        return [
            MandatoryExpenseRecord(
                id=int(row["id"]),
                wallet_id=int(row["wallet_id"]),
                amount_original=self._money_from_row(
                    row, "amount_original", "amount_original_minor"
                ),
                currency=str(row["currency"]).upper(),
                rate_at_operation=self._rate_from_row(row),
                amount_base=self._money_from_row(row, "amount_base", "amount_base_minor"),
                category=str(row["category"]),
                description=str(row["description"] or ""),
                period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
                date=str(row["date"]) if has_date and row["date"] else "",
                auto_pay=bool(row["auto_pay"]) if has_auto_pay else False,
            )
            for row in rows
        ]

    @staticmethod
    def _record_type(record: Record) -> str:
        if isinstance(record, MandatoryExpenseRecord):
            return "mandatory_expense"
        if isinstance(record, IncomeRecord):
            return "income"
        return "expense"

    @staticmethod
    def _date_as_text(value: dt_date | str) -> str:
        if isinstance(value, dt_date):
            return value.isoformat()
        return str(value)
