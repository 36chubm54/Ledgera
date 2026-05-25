from __future__ import annotations

import sqlite3
from typing import Any

from domain.debt import Debt, DebtPayment
from domain.records import MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import to_money_float

SYSTEM_WALLET_ID = 1


class SQLiteRowMutationsMixin:
    _conn: sqlite3.Connection

    @staticmethod
    def _require_lastrowid(lastrowid: int | None, table: str) -> int: ...

    @staticmethod
    def _wallet_balance_columns(balance: object) -> tuple[float, int]: ...

    @staticmethod
    def _money_columns(
        amount_original: object,
        rate_at_operation: object,
        amount_base: object,
    ) -> tuple[float, int, float, str, float, int]: ...

    @staticmethod
    def _date_as_text(value: Any) -> str: ...

    @staticmethod
    def _record_type(record: Record) -> str: ...

    def _default_base_currency(self) -> str: ...

    def _insert_wallet_row(self, wallet: Wallet) -> int:
        initial_balance, initial_balance_minor = self._wallet_balance_columns(
            wallet.initial_balance
        )
        cursor = self._conn.execute(
            """
            INSERT INTO wallets (
                name,
                currency,
                initial_balance,
                initial_balance_minor,
                system,
                allow_negative,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(wallet.name),
                str(wallet.currency).upper(),
                initial_balance,
                initial_balance_minor,
                int(bool(wallet.system)),
                int(bool(wallet.allow_negative)),
                int(bool(wallet.is_active)),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "wallets")

    def _update_wallet_row(self, wallet_id: int, wallet: Wallet) -> None:
        initial_balance, initial_balance_minor = self._wallet_balance_columns(
            wallet.initial_balance
        )
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
                str(wallet.name),
                str(wallet.currency).upper(),
                initial_balance,
                initial_balance_minor,
                int(bool(wallet.system)),
                int(bool(wallet.allow_negative)),
                int(bool(wallet.is_active)),
                int(wallet_id),
            ),
        )

    def _insert_transfer_row(
        self,
        transfer: Transfer,
        *,
        from_wallet_id: int | None = None,
        to_wallet_id: int | None = None,
    ) -> int:
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = self._money_columns(
            transfer.amount_original,
            transfer.rate_at_operation,
            transfer.amount_base,
        )
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
                int(from_wallet_id if from_wallet_id is not None else transfer.from_wallet_id),
                int(to_wallet_id if to_wallet_id is not None else transfer.to_wallet_id),
                self._date_as_text(transfer.date),
                amount_original,
                amount_original_minor,
                str(transfer.currency).upper(),
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                str(transfer.description or ""),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "transfers")

    def _update_transfer_row(
        self,
        transfer_id: int,
        transfer: Transfer,
        *,
        from_wallet_id: int | None = None,
        to_wallet_id: int | None = None,
    ) -> None:
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = self._money_columns(
            transfer.amount_original,
            transfer.rate_at_operation,
            transfer.amount_base,
        )
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
                int(from_wallet_id if from_wallet_id is not None else transfer.from_wallet_id),
                int(to_wallet_id if to_wallet_id is not None else transfer.to_wallet_id),
                self._date_as_text(transfer.date),
                amount_original,
                amount_original_minor,
                str(transfer.currency).upper(),
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                str(transfer.description or ""),
                int(transfer_id),
            ),
        )

    def _insert_debt_row(self, debt: Debt) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO debts (
                contact_name,
                kind,
                total_amount_minor,
                remaining_amount_minor,
                currency,
                interest_rate,
                status,
                created_at,
                closed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(debt.contact_name),
                str(debt.kind.value),
                int(debt.total_amount_minor),
                int(debt.remaining_amount_minor),
                str(debt.currency).upper(),
                float(debt.interest_rate),
                str(debt.status.value),
                str(debt.created_at),
                str(debt.closed_at) if debt.closed_at else None,
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "debts")

    def _update_debt_row(self, debt_id: int, debt: Debt) -> None:
        self._conn.execute(
            """
            UPDATE debts
            SET
                contact_name = ?,
                kind = ?,
                total_amount_minor = ?,
                remaining_amount_minor = ?,
                currency = ?,
                interest_rate = ?,
                status = ?,
                created_at = ?,
                closed_at = ?
            WHERE id = ?
            """,
            (
                str(debt.contact_name),
                str(debt.kind.value),
                int(debt.total_amount_minor),
                int(debt.remaining_amount_minor),
                str(debt.currency).upper(),
                float(debt.interest_rate),
                str(debt.status.value),
                str(debt.created_at),
                str(debt.closed_at) if debt.closed_at else None,
                int(debt_id),
            ),
        )

    def _insert_debt_payment_row(
        self,
        payment: DebtPayment,
        *,
        debt_id: int | None = None,
        record_id: int | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO debt_payments (
                debt_id,
                record_id,
                operation_type,
                principal_paid_minor,
                is_write_off,
                payment_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(debt_id if debt_id is not None else payment.debt_id),
                int(record_id)
                if record_id is not None
                else (int(payment.record_id) if payment.record_id is not None else None),
                str(payment.operation_type.value),
                int(payment.principal_paid_minor),
                int(bool(payment.is_write_off)),
                str(payment.payment_date),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "debt_payments")

    def _update_debt_payment_row(
        self,
        payment_id: int,
        payment: DebtPayment,
        *,
        debt_id: int | None = None,
        record_id: int | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE debt_payments
            SET
                debt_id = ?,
                record_id = ?,
                operation_type = ?,
                principal_paid_minor = ?,
                is_write_off = ?,
                payment_date = ?
            WHERE id = ?
            """,
            (
                int(debt_id if debt_id is not None else payment.debt_id),
                int(record_id)
                if record_id is not None
                else (int(payment.record_id) if payment.record_id is not None else None),
                str(payment.operation_type.value),
                int(payment.principal_paid_minor),
                int(bool(payment.is_write_off)),
                str(payment.payment_date),
                int(payment_id),
            ),
        )

    def _insert_record_row(
        self,
        record: Record,
        *,
        wallet_id: int | None = None,
        transfer_id: int | None = None,
        related_debt_id: int | None = None,
    ) -> int:
        period = record.period if isinstance(record, MandatoryExpenseRecord) else None
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = self._money_columns(
            record.amount_original or 0.0,
            record.rate_at_operation,
            record.amount_base or 0.0,
        )
        cursor = self._conn.execute(
            """
            INSERT INTO records (
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._record_type(record),
                self._date_as_text(record.date),
                int(wallet_id if wallet_id is not None else record.wallet_id),
                int(transfer_id) if transfer_id is not None else None,
                int(related_debt_id)
                if related_debt_id is not None
                else (int(record.related_debt_id) if record.related_debt_id is not None else None),
                amount_original,
                amount_original_minor,
                str(record.currency).upper(),
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                str(record.category),
                str(record.description or ""),
                str(period) if period is not None else None,
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "records")

    def _update_record_row(
        self,
        record_id: int,
        record: Record,
        *,
        wallet_id: int | None = None,
        transfer_id: int | None = None,
        related_debt_id: int | None = None,
    ) -> None:
        period = record.period if isinstance(record, MandatoryExpenseRecord) else None
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = self._money_columns(
            record.amount_original or 0.0,
            record.rate_at_operation,
            record.amount_base or 0.0,
        )
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
                int(wallet_id if wallet_id is not None else record.wallet_id),
                int(transfer_id) if transfer_id is not None else None,
                int(related_debt_id)
                if related_debt_id is not None
                else (int(record.related_debt_id) if record.related_debt_id is not None else None),
                amount_original,
                amount_original_minor,
                str(record.currency).upper(),
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                str(record.category),
                str(record.description or ""),
                str(period) if period is not None else None,
                int(record_id),
            ),
        )

    def _insert_mandatory_row(self, expense: MandatoryExpenseRecord, *, wallet_id: int) -> int:
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = self._money_columns(
            expense.amount_original or 0.0,
            expense.rate_at_operation,
            expense.amount_base or 0.0,
        )
        cursor = self._conn.execute(
            """
            INSERT INTO mandatory_expenses (
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
                period,
                date,
                auto_pay
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(wallet_id),
                amount_original,
                amount_original_minor,
                str(expense.currency).upper(),
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                str(expense.category),
                str(expense.description or ""),
                str(expense.period),
                str(expense.date) if expense.date else None,
                int(bool(expense.auto_pay)),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "mandatory_expenses")

    def _upsert_system_wallet_balance(self, balance: float) -> None:
        initial_balance, initial_balance_minor = self._wallet_balance_columns(balance)
        row = self._conn.execute(
            "SELECT id FROM wallets WHERE id = ?",
            (SYSTEM_WALLET_ID,),
        ).fetchone()
        if row is not None:
            self._conn.execute(
                """
                UPDATE wallets
                    SET initial_balance = ?,
                    initial_balance_minor = ?,
                    system = 1 WHERE id = ?
                """,
                (initial_balance, initial_balance_minor, SYSTEM_WALLET_ID),
            )
            return

        fallback_row = self._conn.execute(
            "SELECT id FROM wallets WHERE system = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if fallback_row is not None:
            self._conn.execute(
                """
                UPDATE wallets
                SET initial_balance = ?,
                initial_balance_minor = ?,
                system = 1 WHERE id = ?
                """,
                (initial_balance, initial_balance_minor, int(fallback_row[0])),
            )
            return

        wallet = Wallet(
            id=SYSTEM_WALLET_ID,
            name="Main wallet",
            currency=self._default_base_currency(),
            initial_balance=to_money_float(balance),
            system=True,
            allow_negative=False,
            is_active=True,
        )
        self._insert_wallet_row(wallet)

    def _load_debt_payment_record_links(self) -> dict[int, int]:
        rows = self._conn.execute(
            """
            SELECT id, record_id
            FROM debt_payments
            WHERE record_id IS NOT NULL
            """
        ).fetchall()
        return {
            int(row["id"]): int(row["record_id"]) for row in rows if row["record_id"] is not None
        }

    def _remap_debt_payment_record_ids(
        self,
        record_id_map: dict[int, int],
        payment_record_links: dict[int, int],
    ) -> None:
        if not payment_record_links:
            return
        for payment_id, source_record_id in payment_record_links.items():
            mapped_record_id = record_id_map.get(int(source_record_id))
            self._conn.execute(
                "UPDATE debt_payments SET record_id = ? WHERE id = ?",
                (
                    int(mapped_record_id) if mapped_record_id is not None else None,
                    int(payment_id),
                ),
            )
