from __future__ import annotations

import sqlite3
from datetime import date as dt_date
from typing import Any

from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import rate_to_text, to_minor_units, to_money_float, to_rate_float


class SQLiteEntitiesMixin:
    _conn: Any

    @staticmethod
    def _money_from_row(row: sqlite3.Row, real_column: str, minor_column: str) -> float: ...

    @staticmethod
    def _rate_from_row(row: sqlite3.Row) -> float: ...

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
