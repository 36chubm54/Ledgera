from __future__ import annotations

import sqlite3
from typing import Any

from domain.debt import Debt, DebtPayment
from domain.records import Record


class SQLiteDebtsMixin:
    _conn: Any

    @staticmethod
    def _debt_from_row(row: sqlite3.Row) -> Debt: ...

    @staticmethod
    def _debt_payment_from_row(row: sqlite3.Row) -> DebtPayment: ...

    def _insert_debt_row(self, debt: Debt) -> int: ...

    def _update_debt_row(self, debt_id: int, debt: Debt) -> None: ...

    def _insert_debt_payment_row(
        self,
        payment: DebtPayment,
        *,
        debt_id: int | None = None,
        record_id: int | None = None,
    ) -> int: ...

    def _update_debt_payment_row(
        self,
        payment_id: int,
        payment: DebtPayment,
        *,
        debt_id: int | None = None,
        record_id: int | None = None,
    ) -> None: ...

    def _reset_autoincrement_many(self, tables: tuple[str, ...]) -> None: ...

    def _restore_debt_payment_record_ids(
        self,
        records: list[Record],
        payments: list[DebtPayment],
    ) -> list[DebtPayment]: ...

    @staticmethod
    def _validate_debt_integrity(
        records: list[Record],
        debts: list[Debt],
        payments: list[DebtPayment],
    ) -> None: ...

    def _renormalize_current_ids(self) -> None: ...

    def load_all(self) -> list[Record]: ...

    def save_debt(self, debt: Debt) -> None:
        with self._conn:
            row = self._conn.execute("SELECT 1 FROM debts WHERE id = ?", (int(debt.id),)).fetchone()
            if row is not None:
                self._update_debt_row(int(debt.id), debt)
            else:
                self._insert_debt_row(debt)

    def load_debts(self) -> list[Debt]:
        rows = self._conn.execute(
            """
            SELECT
                id,
                contact_name,
                kind,
                total_amount_minor,
                remaining_amount_minor,
                currency,
                interest_rate,
                status,
                created_at,
                closed_at
            FROM debts
            ORDER BY id
            """
        ).fetchall()
        return [self._debt_from_row(row) for row in rows]

    def get_debt_by_id(self, debt_id: int) -> Debt:
        row = self._conn.execute(
            """
            SELECT
                id,
                contact_name,
                kind,
                total_amount_minor,
                remaining_amount_minor,
                currency,
                interest_rate,
                status,
                created_at,
                closed_at
            FROM debts
            WHERE id = ?
            """,
            (int(debt_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Debt not found: {debt_id}")
        return self._debt_from_row(row)

    def delete_debt(self, debt_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM debts WHERE id = ?", (int(debt_id),))
        deleted = int(cursor.rowcount or 0) > 0
        if deleted:
            self._renormalize_current_ids()
        return deleted

    def replace_debts(self, debts: list[Debt], payments: list[DebtPayment] | None = None) -> None:
        normalized_payments = list(payments or [])
        normalized_payments = self._restore_debt_payment_record_ids(
            self.load_all(), normalized_payments
        )
        self._validate_debt_integrity(self.load_all(), debts, normalized_payments)
        with self._conn:
            self._conn.execute("DELETE FROM debt_payments")
            self._conn.execute("DELETE FROM debts")
            self._reset_autoincrement_many(("debt_payments", "debts"))

            debt_id_map: dict[int, int] = {}
            for debt in sorted(debts, key=lambda item: item.id):
                debt_id_map[int(debt.id)] = self._insert_debt_row(debt)

            record_id_map = {int(record.id): int(record.id) for record in self.load_all()}
            for payment in sorted(normalized_payments, key=lambda item: item.id):
                mapped_debt_id = debt_id_map.get(int(payment.debt_id))
                if mapped_debt_id is None:
                    raise ValueError(f"Debt payment #{payment.id} references missing debt")
                mapped_record_id = None
                if payment.record_id is not None:
                    mapped_record_id = record_id_map.get(int(payment.record_id))
                    if mapped_record_id is None:
                        raise ValueError(f"Debt payment #{payment.id} references missing record")
                self._insert_debt_payment_row(
                    payment,
                    debt_id=mapped_debt_id,
                    record_id=mapped_record_id,
                )

    def save_debt_payment(self, payment: DebtPayment) -> None:
        with self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM debt_payments WHERE id = ?",
                (int(payment.id),),
            ).fetchone()
            if row is not None:
                self._update_debt_payment_row(int(payment.id), payment)
            else:
                self._insert_debt_payment_row(payment)

    def load_debt_payments(self, debt_id: int | None = None) -> list[DebtPayment]:
        if debt_id is None:
            rows = self._conn.execute(
                """
                SELECT
                    id,
                    debt_id,
                    record_id,
                    operation_type,
                    principal_paid_minor,
                    is_write_off,
                    payment_date
                FROM debt_payments
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT
                    id,
                    debt_id,
                    record_id,
                    operation_type,
                    principal_paid_minor,
                    is_write_off,
                    payment_date
                FROM debt_payments
                WHERE debt_id = ?
                ORDER BY id
                """,
                (int(debt_id),),
            ).fetchall()
        return [self._debt_payment_from_row(row) for row in rows]

    def get_debt_payment_by_id(self, payment_id: int) -> DebtPayment:
        row = self._conn.execute(
            """
            SELECT
                id,
                debt_id,
                record_id,
                operation_type,
                principal_paid_minor,
                is_write_off,
                payment_date
            FROM debt_payments
            WHERE id = ?
            """,
            (int(payment_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Debt payment not found: {payment_id}")
        return self._debt_payment_from_row(row)

    def delete_debt_payment(self, payment_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM debt_payments WHERE id = ?",
                (int(payment_id),),
            )
        deleted = int(cursor.rowcount or 0) > 0
        if deleted:
            self._renormalize_current_ids()
        return deleted
