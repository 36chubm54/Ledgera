from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import date as dt_date
from typing import TYPE_CHECKING

from app.repository import RecordRepository
from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.goal import Goal
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from storage.sqlite_storage import SQLiteStorage
from utils.money import rate_to_text, to_minor_units, to_money_float, to_rate_float
from utils.tag_utils import color_for_tag, normalize_tag_name, normalize_tag_names

if TYPE_CHECKING:
    from app.services import CurrencyService

SYSTEM_WALLET_ID = 1


class SQLiteRecordRepository(RecordRepository):
    """RecordRepository implementation backed by SQLite."""

    def __init__(self, db_path: str = "finance.db", schema_path: str | None = None) -> None:
        self._storage = SQLiteStorage(db_path)
        self._storage.initialize_schema(schema_path)
        self._conn = self._storage._conn
        self._normalize_existing_ids_from_one_if_needed()

    def close(self) -> None:
        self._storage.close()

    @property
    def db_path(self) -> str:
        return str(self._storage._db_path)

    def set_sqlite_sequence(self, table: str, seq: int | None = None) -> None:
        self._storage.set_sqlite_sequence(table, seq)

    def ensure_schema_meta(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get_schema_meta(self, key: str) -> str | None:
        self.ensure_schema_meta()
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            (str(key),),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def set_schema_meta(self, key: str, value: str) -> None:
        self.ensure_schema_meta()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO schema_meta (key, value)
            VALUES (?, ?)
            """,
            (str(key), str(value)),
        )
        self._conn.commit()

    def has_system_wallet_row(self) -> bool:
        row = self._conn.execute(
            "SELECT id FROM wallets WHERE system = 1 OR id = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        return row is not None

    def foreign_key_issues(self) -> list:
        return self._conn.execute("PRAGMA foreign_key_check").fetchall()

    def query_all(self, sql: str, params: tuple = ()) -> list:
        return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql, params).fetchone()

    def query_iter(self, sql: str, params: tuple = (), *, chunk_size: int = 1000):
        cursor = self._conn.execute(sql, params)
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break
            yield from rows

    def execute(self, sql: str, params: tuple = ()) -> None:
        self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def list_tags(self) -> list[Tag]:
        rows = self._conn.execute(
            """
            SELECT id, name, color, usage_count, last_used_at
            FROM tags
            ORDER BY last_used_at DESC, usage_count DESC, name COLLATE NOCASE, name
            """
        ).fetchall()
        return [
            Tag(
                id=int(row["id"]),
                name=str(row["name"]),
                color=str(row["color"] or ""),
                usage_count=int(row["usage_count"] or 0),
                last_used_at=str(row["last_used_at"] or ""),
            )
            for row in rows
        ]

    def search_tags(self, prefix: str) -> list[Tag]:
        needle = normalize_tag_name(prefix)
        if not needle:
            return self.list_tags()
        rows = self._conn.execute(
            """
            SELECT id, name, color, usage_count, last_used_at
            FROM tags
            WHERE lower(name) LIKE lower(?)
            ORDER BY last_used_at DESC, usage_count DESC, name COLLATE NOCASE, name
            """,
            (f"{needle}%",),
        ).fetchall()
        return [
            Tag(
                id=int(row["id"]),
                name=str(row["name"]),
                color=str(row["color"] or ""),
                usage_count=int(row["usage_count"] or 0),
                last_used_at=str(row["last_used_at"] or ""),
            )
            for row in rows
        ]

    def load_tags_for_record_ids(self, record_ids: list[int]) -> dict[int, tuple[str, ...]]:
        return self._record_tags_map(record_ids)

    def replace_record_tags(self, record_id: int, names: list[str] | tuple[str, ...]) -> None:
        with self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM records WHERE id = ?",
                (int(record_id),),
            ).fetchone()
            if row is None:
                raise ValueError(f"Record not found: {record_id}")
            self._replace_record_tags_many({int(record_id): normalize_tag_names(tuple(names))})

    def rename_tag(self, old_name: str, new_name: str) -> None:
        old_tag = normalize_tag_name(old_name)
        new_tag = normalize_tag_name(new_name)
        if not old_tag or not new_tag:
            raise ValueError("Tag name must not be empty")
        with self._conn:
            row = self._conn.execute(
                "SELECT id FROM tags WHERE lower(name) = lower(?) LIMIT 1",
                (old_tag,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Tag not found: {old_name}")
            old_id = int(row["id"])
            existing = self._conn.execute(
                "SELECT id FROM tags WHERE lower(name) = lower(?) LIMIT 1",
                (new_tag,),
            ).fetchone()
            if existing is not None and int(existing["id"]) != old_id:
                new_id = int(existing["id"])
                record_rows = self._conn.execute(
                    "SELECT record_id FROM record_tags WHERE tag_id = ?",
                    (old_id,),
                ).fetchall()
                for record_row in record_rows:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO record_tags (record_id, tag_id) VALUES (?, ?)",
                        (int(record_row["record_id"]), new_id),
                    )
                self._conn.execute("DELETE FROM record_tags WHERE tag_id = ?", (old_id,))
                self._conn.execute("DELETE FROM tags WHERE id = ?", (old_id,))
            else:
                self._conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_tag, old_id))
            self._refresh_tag_metrics()
            self._prune_orphan_tags()

    def delete_tag(self, name: str) -> None:
        target = normalize_tag_name(name)
        if not target:
            return
        with self._conn:
            row: sqlite3.Row | None = self._conn.execute(
                "SELECT id FROM tags WHERE lower(name) = lower(?) LIMIT 1",
                (target,),
            ).fetchone()
            if row is None:
                return
            self._conn.execute("DELETE FROM tags WHERE id = ?", (int(row["id"]),))
            self._refresh_tag_metrics()

    def set_tag_color(self, name: str, color: str) -> None:
        target = normalize_tag_name(name)
        normalized_color = str(color or "").strip()
        if not target or not normalized_color:
            return
        with self._conn:
            row = self._conn.execute(
                "SELECT id FROM tags WHERE lower(name) = lower(?) LIMIT 1",
                (target,),
            ).fetchone()
            if row is None:
                tag_id = self._ensure_tag_id(target)
            else:
                tag_id = int(row["id"])
            self._conn.execute(
                "UPDATE tags SET color = ? WHERE id = ?",
                (normalized_color, int(tag_id)),
            )

    @contextmanager
    def transaction(self):
        # Public transaction helper mainly for tests and one-off maintenance scripts.
        # Prefer repository-level methods for production code.
        with self._conn:
            yield

    @staticmethod
    def _date_as_text(value: dt_date | str) -> str:
        if isinstance(value, dt_date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _record_type(record: Record) -> str:
        if isinstance(record, MandatoryExpenseRecord):
            return "mandatory_expense"
        if isinstance(record, IncomeRecord):
            return "income"
        return "expense"

    @staticmethod
    def _require_lastrowid(lastrowid: int | None, table: str) -> int:
        if lastrowid is None:
            raise RuntimeError(f"Failed to obtain lastrowid for {table} insert")
        return int(lastrowid)

    @staticmethod
    def _wallet_balance_columns(balance: object) -> tuple[float, int]:
        return (to_money_float(balance), to_minor_units(balance))

    @staticmethod
    def _money_columns(
        amount_original: object,
        rate_at_operation: object,
        amount_kzt: object,
    ) -> tuple[float, int, float, str, float, int]:
        return (
            to_money_float(amount_original),
            to_minor_units(amount_original),
            to_rate_float(rate_at_operation),
            rate_to_text(rate_at_operation),
            to_money_float(amount_kzt),
            to_minor_units(amount_kzt),
        )

    def _validate_transfer_integrity(
        self, records: list[Record], transfers: list[Transfer]
    ) -> None:
        transfer_ids = {transfer.id for transfer in transfers}
        grouped: dict[int, list[Record]] = {}
        for record in records:
            if record.transfer_id is None:
                continue
            if record.transfer_id not in transfer_ids:
                raise ValueError(f"Dangling transfer link in record #{record.id}")
            grouped.setdefault(record.transfer_id, []).append(record)
        for transfer in transfers:
            linked = grouped.get(transfer.id, [])
            if len(linked) != 2:
                raise ValueError(
                    f"Transfer integrity violated for #{transfer.id}: {len(linked)} records"
                )
            if {record.type for record in linked} != {"income", "expense"}:
                raise ValueError(
                    f"Transfer integrity violated for #{transfer.id}: invalid record types"
                )

    @staticmethod
    def _validate_debt_integrity(
        records: list[Record],
        debts: list[Debt],
        payments: list[DebtPayment],
    ) -> None:
        debt_ids = {int(debt.id) for debt in debts}
        record_ids = {int(record.id) for record in records}
        for record in records:
            if record.related_debt_id is not None and int(record.related_debt_id) not in debt_ids:
                raise ValueError(
                    f"Record #{record.id} references missing debt #{record.related_debt_id}"
                )
        for payment in payments:
            if int(payment.debt_id) not in debt_ids:
                raise ValueError(
                    f"Debt payment #{payment.id} references missing debt #{payment.debt_id}"
                )
            if payment.record_id is not None and int(payment.record_id) not in record_ids:
                raise ValueError(
                    f"Debt payment #{payment.id} references missing record #{payment.record_id}"
                )

    @staticmethod
    def _payment_expected_record_type(payment: DebtPayment) -> str | None:
        if payment.is_write_off:
            return None
        if payment.operation_type is DebtOperationType.DEBT_REPAY:
            return "expense"
        if payment.operation_type is DebtOperationType.LOAN_COLLECT:
            return "income"
        return None

    def _restore_debt_payment_record_ids(
        self,
        records: list[Record],
        payments: list[DebtPayment],
    ) -> list[DebtPayment]:
        if not payments:
            return []

        record_ids = {int(record.id) for record in records}
        reserved_record_ids = {
            int(payment.record_id)
            for payment in payments
            if payment.record_id is not None and int(payment.record_id) in record_ids
        }
        candidate_groups: dict[tuple[int, str, int, str], list[int]] = {}
        for record in sorted(records, key=lambda item: int(item.id)):
            if record.related_debt_id is None:
                continue
            record_type = self._record_type(record)
            if record_type == "mandatory_expense":
                continue
            key = (
                int(record.related_debt_id),
                self._date_as_text(record.date),
                to_minor_units(record.amount_kzt or 0.0),
                record_type,
            )
            candidate_groups.setdefault(key, []).append(int(record.id))

        normalized: list[DebtPayment] = []
        for payment in payments:
            current_record_id = int(payment.record_id) if payment.record_id is not None else None
            if current_record_id in record_ids:
                normalized.append(payment)
                continue

            expected_record_type = self._payment_expected_record_type(payment)
            restored_record_id = None
            if expected_record_type is not None:
                key = (
                    int(payment.debt_id),
                    str(payment.payment_date),
                    int(payment.principal_paid_minor),
                    expected_record_type,
                )
                for candidate_id in candidate_groups.get(key, []):
                    if candidate_id in reserved_record_ids:
                        continue
                    restored_record_id = candidate_id
                    reserved_record_ids.add(candidate_id)
                    break
            normalized.append(replace(payment, record_id=restored_record_id))
        return normalized

    def _reset_autoincrement(self, table: str) -> None:
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

    def _reset_autoincrement_many(self, tables: tuple[str, ...]) -> None:
        for table in tables:
            self._reset_autoincrement(table)

    def _ids_are_normalized_from_one(self, table: str) -> bool:
        rows = self._conn.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()
        return all(int(row[0]) == index for index, row in enumerate(rows, start=1))

    def _normalize_existing_ids_from_one_if_needed(self) -> None:
        tables = ("wallets", "records", "transfers", "mandatory_expenses", "debts", "debt_payments")
        if (
            all(self._ids_are_normalized_from_one(table) for table in tables)
            and self._tag_ids_are_normalized_from_one()
        ):
            return
        self._renormalize_current_ids()

    def _tag_ids_are_normalized_from_one(self) -> bool:
        rows = self._conn.execute("SELECT id FROM tags ORDER BY id").fetchall()
        return all(int(row[0]) == index for index, row in enumerate(rows, start=1))

    def _renormalize_current_ids(self) -> None:
        wallets = self._storage.get_wallets()
        records = self.load_all()
        transfers = self._storage.get_transfers()
        mandatory_expenses = self._storage.get_mandatory_expenses()
        debts = self.load_debts()
        debt_payments = self.load_debt_payments()
        self.replace_all_data(
            wallets=wallets,
            records=records,
            mandatory_expenses=mandatory_expenses,
            transfers=transfers,
            debts=debts,
            debt_payments=debt_payments,
        )
        self._normalize_tag_ids()

    @staticmethod
    def _select_record_columns() -> str:
        return """
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
            amount_kzt,
            amount_kzt_minor,
            category,
            description,
            period
        """

    def _records_base_rows(self) -> list:
        return self._conn.execute(
            f"""
            SELECT {self._select_record_columns()}
            FROM records
            ORDER BY id
            """
        ).fetchall()

    def _record_tags_map(
        self, record_ids: list[int] | tuple[int, ...]
    ) -> dict[int, tuple[str, ...]]:
        if not record_ids:
            return {}
        placeholders = ", ".join("?" for _ in record_ids)
        rows = self._conn.execute(
            f"""
            SELECT rt.record_id, t.name
            FROM record_tags AS rt
            JOIN tags AS t
              ON t.id = rt.tag_id
            WHERE rt.record_id IN ({placeholders})
            ORDER BY rt.record_id, t.name COLLATE NOCASE, t.name
            """,
            tuple(int(record_id) for record_id in record_ids),
        ).fetchall()
        grouped: dict[int, list[str]] = {}
        for row in rows:
            grouped.setdefault(int(row["record_id"]), []).append(str(row["name"]))
        return {
            record_id: normalize_tag_names(tuple(names))
            for record_id, names in grouped.items()
            if names
        }

    def _replace_record_tags_many(
        self,
        record_tags: dict[int, tuple[str, ...]],
        *,
        clear_missing: bool = False,
    ) -> None:
        if clear_missing:
            if record_tags:
                placeholders = ", ".join("?" for _ in record_tags)
                self._conn.execute(
                    f"DELETE FROM record_tags WHERE record_id NOT IN ({placeholders})",
                    tuple(int(record_id) for record_id in record_tags),
                )
            else:
                self._conn.execute("DELETE FROM record_tags")
        for record_id, names in record_tags.items():
            self._conn.execute("DELETE FROM record_tags WHERE record_id = ?", (int(record_id),))
            normalized = normalize_tag_names(tuple(names))
            for tag_name in normalized:
                tag_id = self._ensure_tag_id(tag_name)
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO record_tags (record_id, tag_id)
                    VALUES (?, ?)
                    """,
                    (int(record_id), int(tag_id)),
                )
        self._refresh_tag_metrics()
        self._prune_orphan_tags()

    def _ensure_tag_id(self, name: str) -> int:
        normalized = normalize_tag_name(name)
        if not normalized:
            raise ValueError("Tag name must not be empty")
        row = self._conn.execute(
            "SELECT id, name FROM tags WHERE lower(name) = lower(?) LIMIT 1",
            (normalized,),
        ).fetchone()
        if row is not None:
            tag_id = int(row["id"])
            stored_name = str(row["name"])
            if stored_name != normalized:
                self._conn.execute(
                    "UPDATE tags SET name = ? WHERE id = ?",
                    (normalized, tag_id),
                )
            return tag_id
        cursor = self._conn.execute(
            "INSERT INTO tags (name, color, usage_count, last_used_at) VALUES (?, ?, 0, '')",
            (normalized, color_for_tag(normalized)),
        )
        return self._require_lastrowid(cursor.lastrowid, "tags")

    def _prune_orphan_tags(self) -> None:
        self._conn.execute(
            """
            DELETE FROM tags
            WHERE id NOT IN (SELECT DISTINCT tag_id FROM record_tags)
            """
        )
        self._normalize_tag_ids()

    def _normalize_tag_ids(self) -> None:
        rows = self._conn.execute("SELECT id FROM tags ORDER BY id").fetchall()
        remap: list[tuple[int, int]] = []
        for next_id, row in enumerate(rows, start=1):
            current_id = int(row["id"])
            if current_id != next_id:
                remap.append((current_id, next_id))
        if not remap:
            self._reset_autoincrement("tags")
            return

        for current_id, next_id in remap:
            self._conn.execute(
                "UPDATE tags SET id = ? WHERE id = ?",
                (-int(next_id), int(current_id)),
            )
        for _current_id, next_id in remap:
            self._conn.execute(
                "UPDATE tags SET id = ? WHERE id = ?",
                (int(next_id), -int(next_id)),
            )
        self._reset_autoincrement("tags")

    def _refresh_tag_metrics(self) -> None:
        self._conn.execute(
            """
            UPDATE tags
            SET usage_count = COALESCE((
                    SELECT COUNT(*)
                    FROM record_tags AS rt
                    WHERE rt.tag_id = tags.id
                ), 0),
                last_used_at = COALESCE((
                    SELECT MAX(r.date)
                    FROM record_tags AS rt
                    JOIN records AS r
                      ON r.id = rt.record_id
                    WHERE rt.tag_id = tags.id
                ), '')
            WHERE 1 = 1
            """
        )
        rows = self._conn.execute(
            "SELECT id, name, color FROM tags WHERE length(trim(COALESCE(color, ''))) = 0"
        ).fetchall()
        for row in rows:
            self._conn.execute(
                "UPDATE tags SET color = ? WHERE id = ?",
                (color_for_tag(str(row["name"] or "")), int(row["id"])),
            )

    def _record_from_row(self, row, *, tags: tuple[str, ...] = ()) -> Record:
        payload = {
            "id": int(row["id"]),
            "date": str(row["date"]),
            "wallet_id": int(row["wallet_id"]),
            "transfer_id": int(row["transfer_id"]) if row["transfer_id"] is not None else None,
            "related_debt_id": (
                int(row["related_debt_id"]) if row["related_debt_id"] is not None else None
            ),
            "amount_original": self._storage._money_from_row(
                row, "amount_original", "amount_original_minor"
            ),
            "currency": str(row["currency"]).upper(),
            "rate_at_operation": self._storage._rate_from_row(row),
            "amount_kzt": self._storage._money_from_row(row, "amount_kzt", "amount_kzt_minor"),
            "category": str(row["category"]),
            "description": str(row["description"] or ""),
            "tags": tags,
        }
        if str(row["type"]) == "income":
            return IncomeRecord(**payload)
        if str(row["type"]) == "mandatory_expense":
            return MandatoryExpenseRecord(
                **payload,
                period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
            )
        return ExpenseRecord(**payload)

    @staticmethod
    def _debt_from_row(row) -> Debt:
        return Debt(
            id=int(row["id"]),
            contact_name=str(row["contact_name"]),
            kind=DebtKind(str(row["kind"])),
            total_amount_minor=int(row["total_amount_minor"]),
            remaining_amount_minor=int(row["remaining_amount_minor"]),
            currency=str(row["currency"]).upper(),
            interest_rate=float(row["interest_rate"]),
            status=DebtStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            closed_at=str(row["closed_at"]) if row["closed_at"] is not None else None,
        )

    @staticmethod
    def _debt_payment_from_row(row) -> DebtPayment:
        return DebtPayment(
            id=int(row["id"]),
            debt_id=int(row["debt_id"]),
            record_id=int(row["record_id"]) if row["record_id"] is not None else None,
            operation_type=DebtOperationType(str(row["operation_type"])),
            principal_paid_minor=int(row["principal_paid_minor"]),
            is_write_off=bool(row["is_write_off"]),
            payment_date=str(row["payment_date"]),
        )

    @staticmethod
    def _asset_from_row(row) -> Asset:
        return Asset(
            id=int(row["id"]),
            name=str(row["name"]),
            category=AssetCategory(str(row["category"])),
            currency=str(row["currency"]).upper(),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            description=str(row["description"] or ""),
        )

    @staticmethod
    def _asset_snapshot_from_row(row) -> AssetSnapshot:
        return AssetSnapshot(
            id=int(row["id"]),
            asset_id=int(row["asset_id"]),
            snapshot_date=str(row["snapshot_date"]),
            value_minor=int(row["value_minor"]),
            currency=str(row["currency"]).upper(),
            note=str(row["note"] or ""),
        )

    @staticmethod
    def _goal_from_row(row) -> Goal:
        return Goal(
            id=int(row["id"]),
            title=str(row["title"]),
            target_amount_minor=int(row["target_amount_minor"]),
            currency=str(row["currency"]).upper(),
            created_at=str(row["created_at"]),
            is_completed=bool(row["is_completed"]),
            target_date=str(row["target_date"]) if row["target_date"] is not None else None,
            description=str(row["description"] or ""),
        )

    def _mandatory_from_row(self, row) -> MandatoryExpenseRecord:
        return MandatoryExpenseRecord(
            id=int(row["id"]),
            wallet_id=int(row["wallet_id"]),
            amount_original=self._storage._money_from_row(
                row, "amount_original", "amount_original_minor"
            ),
            currency=str(row["currency"]).upper(),
            rate_at_operation=self._storage._rate_from_row(row),
            amount_kzt=self._storage._money_from_row(row, "amount_kzt", "amount_kzt_minor"),
            category=str(row["category"]),
            description=str(row["description"] or ""),
            period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
            date=str(row["date"]) if row["date"] else "",
            auto_pay=bool(row["auto_pay"]),
        )

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
            amount_kzt,
            amount_kzt_minor,
        ) = self._money_columns(
            transfer.amount_original,
            transfer.rate_at_operation,
            transfer.amount_kzt,
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
                amount_kzt,
                amount_kzt_minor,
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
                amount_kzt,
                amount_kzt_minor,
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
            amount_kzt,
            amount_kzt_minor,
        ) = self._money_columns(
            transfer.amount_original,
            transfer.rate_at_operation,
            transfer.amount_kzt,
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
                amount_kzt = ?,
                amount_kzt_minor = ?,
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
                amount_kzt,
                amount_kzt_minor,
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

    def _insert_asset_row(self, asset: Asset) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO assets (
                name,
                category,
                currency,
                is_active,
                created_at,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(asset.name),
                str(asset.category.value),
                str(asset.currency).upper(),
                int(bool(asset.is_active)),
                str(asset.created_at),
                str(asset.description or ""),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "assets")

    def _update_asset_row(self, asset_id: int, asset: Asset) -> None:
        self._conn.execute(
            """
            UPDATE assets
            SET
                name = ?,
                category = ?,
                currency = ?,
                is_active = ?,
                created_at = ?,
                description = ?
            WHERE id = ?
            """,
            (
                str(asset.name),
                str(asset.category.value),
                str(asset.currency).upper(),
                int(bool(asset.is_active)),
                str(asset.created_at),
                str(asset.description or ""),
                int(asset_id),
            ),
        )

    def _insert_asset_snapshot_row(
        self,
        snapshot: AssetSnapshot,
        *,
        asset_id: int | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO asset_snapshots (
                asset_id,
                snapshot_date,
                value_minor,
                currency,
                note
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(asset_id if asset_id is not None else snapshot.asset_id),
                str(snapshot.snapshot_date),
                int(snapshot.value_minor),
                str(snapshot.currency).upper(),
                str(snapshot.note or ""),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "asset_snapshots")

    def _update_asset_snapshot_row(
        self,
        snapshot_id: int,
        snapshot: AssetSnapshot,
        *,
        asset_id: int | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE asset_snapshots
            SET
                asset_id = ?,
                snapshot_date = ?,
                value_minor = ?,
                currency = ?,
                note = ?
            WHERE id = ?
            """,
            (
                int(asset_id if asset_id is not None else snapshot.asset_id),
                str(snapshot.snapshot_date),
                int(snapshot.value_minor),
                str(snapshot.currency).upper(),
                str(snapshot.note or ""),
                int(snapshot_id),
            ),
        )

    def _insert_goal_row(self, goal: Goal) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO goals (
                title,
                target_amount_minor,
                currency,
                target_date,
                is_completed,
                created_at,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(goal.title),
                int(goal.target_amount_minor),
                str(goal.currency).upper(),
                str(goal.target_date) if goal.target_date else None,
                int(bool(goal.is_completed)),
                str(goal.created_at),
                str(goal.description or ""),
            ),
        )
        return self._require_lastrowid(cursor.lastrowid, "goals")

    def _update_goal_row(self, goal_id: int, goal: Goal) -> None:
        self._conn.execute(
            """
            UPDATE goals
            SET
                title = ?,
                target_amount_minor = ?,
                currency = ?,
                target_date = ?,
                is_completed = ?,
                created_at = ?,
                description = ?
            WHERE id = ?
            """,
            (
                str(goal.title),
                int(goal.target_amount_minor),
                str(goal.currency).upper(),
                str(goal.target_date) if goal.target_date else None,
                int(bool(goal.is_completed)),
                str(goal.created_at),
                str(goal.description or ""),
                int(goal_id),
            ),
        )

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
            amount_kzt,
            amount_kzt_minor,
        ) = self._money_columns(
            record.amount_original or 0.0,
            record.rate_at_operation,
            record.amount_kzt or 0.0,
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
                amount_kzt,
                amount_kzt_minor,
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
                amount_kzt,
                amount_kzt_minor,
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
            amount_kzt,
            amount_kzt_minor,
        ) = self._money_columns(
            record.amount_original or 0.0,
            record.rate_at_operation,
            record.amount_kzt or 0.0,
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
                amount_kzt = ?,
                amount_kzt_minor = ?,
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
                amount_kzt,
                amount_kzt_minor,
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
            amount_kzt,
            amount_kzt_minor,
        ) = self._money_columns(
            expense.amount_original or 0.0,
            expense.rate_at_operation,
            expense.amount_kzt or 0.0,
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
                amount_kzt,
                amount_kzt_minor,
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
                amount_kzt,
                amount_kzt_minor,
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
            currency="KZT",
            initial_balance=to_money_float(balance),
            system=True,
            allow_negative=False,
            is_active=True,
        )
        self._insert_wallet_row(wallet)

    def load_active_wallets(self) -> list[Wallet]:
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
            WHERE is_active = 1
            ORDER BY id
            """
        ).fetchall()
        return [
            Wallet(
                id=int(row["id"]),
                name=str(row["name"]),
                currency=str(row["currency"]),
                initial_balance=self._storage._money_from_row(
                    row, "initial_balance", "initial_balance_minor"
                ),
                system=bool(row["system"]),
                allow_negative=bool(row["allow_negative"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def create_wallet(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        allow_negative: bool = False,
        system: bool = False,
    ) -> Wallet:
        with self._conn:
            draft = Wallet(
                id=SYSTEM_WALLET_ID,
                name=str(name or "Wallet"),
                currency=str(currency or "KZT").upper(),
                initial_balance=to_money_float(initial_balance),
                system=bool(system),
                allow_negative=bool(allow_negative),
                is_active=True,
            )
            wallet_id = self._insert_wallet_row(draft)
            return Wallet(
                id=wallet_id,
                name=draft.name,
                currency=draft.currency,
                initial_balance=draft.initial_balance,
                system=draft.system,
                allow_negative=draft.allow_negative,
                is_active=draft.is_active,
            )

    def save_asset(self, asset: Asset) -> None:
        with self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM assets WHERE id = ?", (int(asset.id),)
            ).fetchone()
            if row is not None:
                self._update_asset_row(int(asset.id), asset)
            else:
                self._insert_asset_row(asset)

    def load_assets(self, *, active_only: bool = False) -> list[Asset]:
        params: tuple[object, ...] = ()
        sql = """
            SELECT
                id,
                name,
                category,
                currency,
                is_active,
                created_at,
                description
            FROM assets
        """
        if active_only:
            sql += "\nWHERE is_active = 1"
        sql += "\nORDER BY id"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._asset_from_row(row) for row in rows]

    def get_total_assets_kzt(
        self, currency: CurrencyService, *, active_only: bool = True
    ) -> float | None:
        from services.asset_service import AssetService

        return AssetService(self, currency).get_total_assets_kzt(active_only=active_only)

    def get_asset_by_id(self, asset_id: int) -> Asset:
        row = self._conn.execute(
            """
            SELECT
                id,
                name,
                category,
                currency,
                is_active,
                created_at,
                description
            FROM assets
            WHERE id = ?
            """,
            (int(asset_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Asset not found: {asset_id}")
        return self._asset_from_row(row)

    def deactivate_asset(self, asset_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE assets SET is_active = 0 WHERE id = ?",
                (int(asset_id),),
            )
        return int(cursor.rowcount or 0) > 0

    def save_asset_snapshot(self, snapshot: AssetSnapshot, *, commit: bool = True) -> None:
        def _save() -> None:
            row = self._conn.execute(
                "SELECT 1 FROM asset_snapshots WHERE id = ?",
                (int(snapshot.id),),
            ).fetchone()
            if row is not None:
                self._update_asset_snapshot_row(int(snapshot.id), snapshot)
                return
            existing = self._conn.execute(
                """
                SELECT id
                FROM asset_snapshots
                WHERE asset_id = ? AND snapshot_date = ?
                """,
                (int(snapshot.asset_id), str(snapshot.snapshot_date)),
            ).fetchone()
            if existing is not None:
                self._update_asset_snapshot_row(int(existing["id"]), snapshot)
            else:
                self._insert_asset_snapshot_row(snapshot)

        if commit:
            with self._conn:
                _save()
            return
        _save()

    def load_asset_snapshots(self, asset_id: int | None = None) -> list[AssetSnapshot]:
        if asset_id is None:
            rows = self._conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    snapshot_date,
                    value_minor,
                    currency,
                    note,
                    created_at
                FROM asset_snapshots
                ORDER BY asset_id, snapshot_date, id
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT
                    id,
                    asset_id,
                    snapshot_date,
                    value_minor,
                    currency,
                    note,
                    created_at
                FROM asset_snapshots
                WHERE asset_id = ?
                ORDER BY snapshot_date, id
                """,
                (int(asset_id),),
            ).fetchall()
        return [self._asset_snapshot_from_row(row) for row in rows]

    def get_asset_snapshot_by_id(self, snapshot_id: int) -> AssetSnapshot:
        row = self._conn.execute(
            """
            SELECT
                id,
                asset_id,
                snapshot_date,
                value_minor,
                currency,
                note,
                created_at
            FROM asset_snapshots
            WHERE id = ?
            """,
            (int(snapshot_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Asset snapshot not found: {snapshot_id}")
        return self._asset_snapshot_from_row(row)

    def delete_asset_snapshot(self, snapshot_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM asset_snapshots WHERE id = ?",
                (int(snapshot_id),),
            )
        return int(cursor.rowcount or 0) > 0

    def get_latest_asset_snapshots(self, *, active_only: bool = True) -> list[AssetSnapshot]:
        sql = """
            SELECT
                s.id,
                s.asset_id,
                s.snapshot_date,
                s.value_minor,
                s.currency,
                s.note,
                s.created_at
            FROM asset_snapshots AS s
            JOIN assets AS a
                ON a.id = s.asset_id
            JOIN (
                SELECT
                    asset_id,
                    MAX(snapshot_date) AS latest_snapshot_date
                FROM asset_snapshots
                GROUP BY asset_id
            ) AS latest
                ON latest.asset_id = s.asset_id
               AND latest.latest_snapshot_date = s.snapshot_date
            WHERE s.id = (
                SELECT MAX(s2.id)
                FROM asset_snapshots AS s2
                WHERE s2.asset_id = s.asset_id
                  AND s2.snapshot_date = s.snapshot_date
            )
        """
        if active_only:
            sql += "\nAND a.is_active = 1"
        sql += "\nORDER BY s.asset_id"
        rows = self._conn.execute(sql).fetchall()
        return [self._asset_snapshot_from_row(row) for row in rows]

    def save_goal(self, goal: Goal) -> None:
        with self._conn:
            row = self._conn.execute("SELECT 1 FROM goals WHERE id = ?", (int(goal.id),)).fetchone()
            if row is not None:
                self._update_goal_row(int(goal.id), goal)
            else:
                self._insert_goal_row(goal)

    def load_goals(self) -> list[Goal]:
        rows = self._conn.execute(
            """
            SELECT
                id,
                title,
                target_amount_minor,
                currency,
                target_date,
                is_completed,
                created_at,
                description
            FROM goals
            ORDER BY id
            """
        ).fetchall()
        return [self._goal_from_row(row) for row in rows]

    def get_goal_by_id(self, goal_id: int) -> Goal:
        row = self._conn.execute(
            """
            SELECT
                id,
                title,
                target_amount_minor,
                currency,
                target_date,
                is_completed,
                created_at,
                description
            FROM goals
            WHERE id = ?
            """,
            (int(goal_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Goal not found: {goal_id}")
        return self._goal_from_row(row)

    def delete_goal(self, goal_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM goals WHERE id = ?", (int(goal_id),))
        return int(cursor.rowcount or 0) > 0

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

    def save_wallet(self, wallet: Wallet) -> None:
        with self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM wallets WHERE id = ?",
                (int(wallet.id),),
            ).fetchone()
            if row is not None:
                self._update_wallet_row(int(wallet.id), wallet)
            else:
                self._insert_wallet_row(wallet)

    def soft_delete_wallet(self, wallet_id: int) -> bool:
        wallet_id = int(wallet_id)
        with self._conn:
            row = self._conn.execute(
                "SELECT system FROM wallets WHERE id = ?",
                (wallet_id,),
            ).fetchone()
            if row is None:
                return False
            if bool(row[0]):
                return False
            self._conn.execute("UPDATE wallets SET is_active = 0 WHERE id = ?", (wallet_id,))
            return True

    def load_wallets(self) -> list[Wallet]:
        return self._storage.get_wallets()

    def get_system_wallet(self) -> Wallet:
        for wallet in self.load_wallets():
            if wallet.system or wallet.id == SYSTEM_WALLET_ID:
                return wallet
        return Wallet(
            id=SYSTEM_WALLET_ID,
            name="Main wallet",
            currency="KZT",
            initial_balance=0.0,
            system=True,
            allow_negative=False,
            is_active=True,
        )

    def save_transfer(self, transfer: Transfer) -> None:
        with self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM transfers WHERE id = ?",
                (int(transfer.id),),
            ).fetchone()
            if row is not None:
                self._update_transfer_row(int(transfer.id), transfer)
            else:
                self._insert_transfer_row(transfer)

    def load_transfers(self) -> list[Transfer]:
        return self._storage.get_transfers()

    def replace_records_and_transfers(
        self, records: list[Record], transfers: list[Transfer]
    ) -> None:
        self._validate_transfer_integrity(records, transfers)

        with self._conn:
            payment_record_links = self._load_debt_payment_record_links()
            self._conn.execute("DELETE FROM records")
            self._conn.execute("DELETE FROM transfers")
            self._reset_autoincrement_many(("records", "transfers"))

            transfer_id_map: dict[int, int] = {}
            for transfer in sorted(transfers, key=lambda item: item.id):
                new_transfer_id = self._insert_transfer_row(transfer)
                transfer_id_map[int(transfer.id)] = new_transfer_id

            record_id_map: dict[int, int] = {}
            for record in sorted(records, key=lambda item: item.id):
                transfer_id = None
                if record.transfer_id is not None:
                    original_transfer_id = int(record.transfer_id)
                    if original_transfer_id not in transfer_id_map:
                        raise ValueError(
                            f"Record #{record.id} references missing transfer "
                            f"#{original_transfer_id}"
                        )
                    transfer_id = int(transfer_id_map[original_transfer_id])
                new_record_id = self._insert_record_row(record, transfer_id=transfer_id)
                record_id_map[int(record.id)] = int(new_record_id)
            self._replace_record_tags_many(
                {int(record_id_map[int(record.id)]): tuple(record.tags) for record in records},
                clear_missing=True,
            )
            self._remap_debt_payment_record_ids(record_id_map, payment_record_links)

    def save(self, record: Record) -> None:
        with self._conn:
            transfer_id = int(record.transfer_id) if record.transfer_id is not None else None
            record_id = self._insert_record_row(record, transfer_id=transfer_id)
            self._replace_record_tags_many({int(record_id): tuple(record.tags)})

    def load_all(self) -> list[Record]:
        rows = self._records_base_rows()
        tags_map = self._record_tags_map([int(row["id"]) for row in rows])
        return [self._record_from_row(row, tags=tags_map.get(int(row["id"]), ())) for row in rows]

    def list_all(self) -> list[Record]:
        return self.load_all()

    def get_by_id(self, record_id: int) -> Record:
        record_id = int(record_id)
        row = self._conn.execute(
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
                amount_kzt,
                amount_kzt_minor,
                category,
                description,
                period
            FROM records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        if row is not None:
            tags = self._record_tags_map([record_id]).get(record_id, ())
            return self._record_from_row(row, tags=tags)
        raise ValueError(f"Record not found: {record_id}")

    def get_records_by_tag(self, name: str) -> list[Record]:
        tag_name = normalize_tag_name(name)
        if not tag_name:
            return []
        rows = self._conn.execute(
            f"""
            SELECT {self._select_record_columns()}
            FROM records
            WHERE EXISTS (
                SELECT 1
                FROM record_tags AS rt
                JOIN tags AS t
                  ON t.id = rt.tag_id
                WHERE rt.record_id = records.id
                  AND lower(t.name) = lower(?)
            )
            ORDER BY id
            """,
            (tag_name,),
        ).fetchall()
        tags_map = self._record_tags_map([int(row["id"]) for row in rows])
        return [self._record_from_row(row, tags=tags_map.get(int(row["id"]), ())) for row in rows]

    def get_transfer_id_by_record_index(self, index: int) -> int | None:
        if int(index) < 0:
            return None
        row = self._conn.execute(
            """
            SELECT transfer_id
            FROM records
            ORDER BY id
            LIMIT 1 OFFSET ?
            """,
            (int(index),),
        ).fetchone()
        if row is None or row["transfer_id"] is None:
            return None
        return int(row["transfer_id"])

    def replace(self, record: Record) -> None:
        record_id = int(getattr(record, "id", 0) or 0)
        if record_id <= 0:
            raise ValueError("Record id must be positive")
        if not self._conn.execute("SELECT 1 FROM records WHERE id = ?", (record_id,)).fetchone():
            raise ValueError(f"Record not found: {record_id}")
        with self._conn:
            transfer_id = int(record.transfer_id) if record.transfer_id is not None else None
            related_debt_id = (
                int(record.related_debt_id) if record.related_debt_id is not None else None
            )
            self._update_record_row(
                record_id,
                record,
                transfer_id=transfer_id,
                related_debt_id=related_debt_id,
            )
            self._replace_record_tags_many({record_id: tuple(record.tags)})

    def delete_by_index(self, index: int) -> bool:
        if int(index) < 0:
            return False
        row = self._conn.execute(
            """
            SELECT id
            FROM records
            ORDER BY id
            LIMIT 1 OFFSET ?
            """,
            (int(index),),
        ).fetchone()
        if row is None:
            return False
        with self._conn:
            self._conn.execute("DELETE FROM records WHERE id = ?", (int(row["id"]),))
        self._renormalize_current_ids()
        return True

    def delete_all(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM records")
            self._reset_autoincrement("records")
            self._prune_orphan_tags()

    def save_initial_balance(self, balance: float) -> None:
        with self._conn:
            self._upsert_system_wallet_balance(to_money_float(balance))

    def load_initial_balance(self) -> float:
        return float(self.get_system_wallet().initial_balance)

    def save_mandatory_expense(self, expense: MandatoryExpenseRecord) -> None:
        with self._conn:
            if not self.has_system_wallet_row():
                self._upsert_system_wallet_balance(0.0)
            wallet_id = int(expense.wallet_id)
            wallet_exists = self._conn.execute(
                "SELECT 1 FROM wallets WHERE id = ?",
                (wallet_id,),
            ).fetchone()
            if wallet_exists is None:
                wallet_id = int(self.get_system_wallet().id)
            self._insert_mandatory_row(expense, wallet_id=wallet_id)

    def load_mandatory_expenses(self) -> list[MandatoryExpenseRecord]:
        return self._storage.get_mandatory_expenses()

    def get_mandatory_expense_by_id(self, expense_id: int) -> MandatoryExpenseRecord:
        row = self._conn.execute(
            """
            SELECT
                id,
                wallet_id,
                amount_original,
                amount_original_minor,
                currency,
                rate_at_operation,
                rate_at_operation_text,
                amount_kzt,
                amount_kzt_minor,
                category,
                description,
                period,
                date,
                auto_pay
            FROM mandatory_expenses
            WHERE id = ?
            """,
            (int(expense_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Mandatory expense не найден: {expense_id}")
        return self._mandatory_from_row(row)

    def update_mandatory_expense(self, expense: MandatoryExpenseRecord) -> None:
        expense_id = int(getattr(expense, "id", 0) or 0)
        if expense_id <= 0:
            raise ValueError("id обязательного расхода должен быть положительным")
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_kzt,
            amount_kzt_minor,
        ) = self._money_columns(
            expense.amount_original or 0.0,
            expense.rate_at_operation,
            expense.amount_kzt or 0.0,
        )
        with self._conn:
            self._conn.execute(
                """
                UPDATE mandatory_expenses
                SET wallet_id         = ?,
                    amount_original   = ?,
                    amount_original_minor = ?,
                    currency          = ?,
                    rate_at_operation = ?,
                    rate_at_operation_text = ?,
                    amount_kzt        = ?,
                    amount_kzt_minor  = ?,
                    category          = ?,
                    description       = ?,
                    period            = ?,
                    date              = ?,
                    auto_pay          = ?
                WHERE id = ?
                """,
                (
                    int(expense.wallet_id),
                    amount_original,
                    amount_original_minor,
                    str(expense.currency).upper(),
                    rate_at_operation,
                    rate_at_operation_text,
                    amount_kzt,
                    amount_kzt_minor,
                    str(expense.category),
                    str(expense.description or ""),
                    str(expense.period),
                    str(expense.date) if expense.date else None,
                    int(bool(expense.auto_pay)),
                    expense_id,
                ),
            )

    def delete_mandatory_expense_by_index(self, index: int) -> bool:
        if int(index) < 0:
            return False
        row = self._conn.execute(
            """
            SELECT id
            FROM mandatory_expenses
            ORDER BY id
            LIMIT 1 OFFSET ?
            """,
            (int(index),),
        ).fetchone()
        if row is None:
            return False
        with self._conn:
            self._conn.execute("DELETE FROM mandatory_expenses WHERE id = ?", (int(row["id"]),))
        self._renormalize_current_ids()
        return True

    def delete_all_mandatory_expenses(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM mandatory_expenses")
            self._reset_autoincrement("mandatory_expenses")

    def replace_records(self, records: list[Record], initial_balance: float) -> None:
        with self._conn:
            payment_record_links = self._load_debt_payment_record_links()
            self._upsert_system_wallet_balance(to_money_float(initial_balance))
            self._conn.execute("DELETE FROM records")
            self._reset_autoincrement("records")
            record_id_map: dict[int, int] = {}
            for record in sorted(records, key=lambda item: item.id):
                transfer_id = int(record.transfer_id) if record.transfer_id is not None else None
                related_debt_id = (
                    int(record.related_debt_id) if record.related_debt_id is not None else None
                )
                new_record_id = self._insert_record_row(
                    record,
                    transfer_id=transfer_id,
                    related_debt_id=related_debt_id,
                )
                record_id_map[int(record.id)] = int(new_record_id)
            self._replace_record_tags_many(
                {int(record_id_map[int(record.id)]): tuple(record.tags) for record in records},
                clear_missing=True,
            )
            self._remap_debt_payment_record_ids(record_id_map, payment_record_links)

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

    def replace_mandatory_expenses(self, expenses: list[MandatoryExpenseRecord]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM mandatory_expenses")
            self._reset_autoincrement("mandatory_expenses")
            for expense in sorted(expenses, key=lambda item: item.id):
                self._insert_mandatory_row(expense, wallet_id=int(expense.wallet_id))

    def replace_all_data(
        self,
        *,
        initial_balance: float = 0.0,
        wallets: list[Wallet] | None = None,
        records: list[Record],
        mandatory_expenses: list[MandatoryExpenseRecord],
        tags: list[Tag] | None = None,
        transfers: list[Transfer] | None = None,
        debts: list[Debt] | None = None,
        debt_payments: list[DebtPayment] | None = None,
    ) -> None:
        (
            normalized_wallets,
            normalized_transfers,
            normalized_debts,
            normalized_debt_payments,
        ) = self._normalize_replace_all_data_inputs(
            initial_balance=initial_balance,
            wallets=wallets,
            transfers=transfers,
            debts=debts,
            debt_payments=debt_payments,
            records=records,
        )
        self._validate_transfer_integrity(records, normalized_transfers)
        self._validate_debt_integrity(records, normalized_debts, normalized_debt_payments)

        with self._conn:
            self._truncate_replace_all_tables()
            wallet_id_map = self._replace_all_wallets(normalized_wallets)
            transfer_id_map = self._replace_all_transfers(normalized_transfers, wallet_id_map)
            debt_id_map = self._replace_all_debts(normalized_debts)
            record_id_map = self._replace_all_records(
                records, wallet_id_map, transfer_id_map, debt_id_map, list(tags or [])
            )
            self._replace_all_mandatory_expenses(mandatory_expenses, wallet_id_map)
            self._replace_all_debt_payments(normalized_debt_payments, debt_id_map, record_id_map)

    def _normalize_replace_all_data_inputs(
        self,
        *,
        initial_balance: float,
        wallets: list[Wallet] | None,
        transfers: list[Transfer] | None,
        debts: list[Debt] | None,
        debt_payments: list[DebtPayment] | None,
        records: list[Record],
    ) -> tuple[list[Wallet], list[Transfer], list[Debt], list[DebtPayment]]:
        normalized_wallets = list(wallets or [])
        if not normalized_wallets:
            normalized_wallets = [
                Wallet(
                    id=SYSTEM_WALLET_ID,
                    name="Main wallet",
                    currency="KZT",
                    initial_balance=to_money_float(initial_balance),
                    system=True,
                    allow_negative=False,
                    is_active=True,
                )
            ]
        normalized_transfers = list(transfers or [])
        normalized_debts = list(debts or [])
        normalized_debt_payments = list(debt_payments or [])
        normalized_debt_payments = self._restore_debt_payment_record_ids(
            records,
            normalized_debt_payments,
        )
        return (
            normalized_wallets,
            normalized_transfers,
            normalized_debts,
            normalized_debt_payments,
        )

    def _truncate_replace_all_tables(self) -> None:
        self._conn.execute("DELETE FROM record_tags")
        self._conn.execute("DELETE FROM tags")
        self._conn.execute("DELETE FROM debt_payments")
        self._conn.execute("DELETE FROM debts")
        self._conn.execute("DELETE FROM records")
        self._conn.execute("DELETE FROM mandatory_expenses")
        self._conn.execute("DELETE FROM transfers")
        self._conn.execute("DELETE FROM wallets")
        self._reset_autoincrement_many(
            (
                "tags",
                "debt_payments",
                "debts",
                "records",
                "mandatory_expenses",
                "transfers",
                "wallets",
            )
        )

    def _replace_all_wallets(self, wallets: list[Wallet]) -> dict[int, int]:
        wallet_id_map: dict[int, int] = {}
        for wallet in sorted(wallets, key=lambda item: item.id):
            new_wallet_id = self._insert_wallet_row(wallet)
            wallet_id_map[int(wallet.id)] = new_wallet_id
        return wallet_id_map

    def _replace_all_transfers(
        self,
        transfers: list[Transfer],
        wallet_id_map: dict[int, int],
    ) -> dict[int, int]:
        transfer_id_map: dict[int, int] = {}
        for transfer in sorted(transfers, key=lambda item: item.id):
            from_wallet_id = wallet_id_map.get(int(transfer.from_wallet_id))
            to_wallet_id = wallet_id_map.get(int(transfer.to_wallet_id))
            if from_wallet_id is None or to_wallet_id is None:
                raise ValueError(f"Transfer #{transfer.id} references missing wallet")
            new_transfer_id = self._insert_transfer_row(
                transfer,
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
            )
            transfer_id_map[int(transfer.id)] = new_transfer_id
        return transfer_id_map

    def _replace_all_debts(self, debts: list[Debt]) -> dict[int, int]:
        debt_id_map: dict[int, int] = {}
        for debt in sorted(debts, key=lambda item: item.id):
            debt_id_map[int(debt.id)] = self._insert_debt_row(debt)
        return debt_id_map

    def _replace_all_records(
        self,
        records: list[Record],
        wallet_id_map: dict[int, int],
        transfer_id_map: dict[int, int],
        debt_id_map: dict[int, int],
        tags: list[Tag],
    ) -> dict[int, int]:
        record_id_map: dict[int, int] = {}
        for record in sorted(records, key=lambda item: item.id):
            wallet_id = wallet_id_map.get(int(record.wallet_id))
            if wallet_id is None:
                raise ValueError(f"Record #{record.id} references missing wallet")
            transfer_id = None
            if record.transfer_id is not None:
                transfer_id = transfer_id_map.get(int(record.transfer_id))
                if transfer_id is None:
                    raise ValueError(
                        f"Record #{record.id} references missing transfer #{record.transfer_id}"
                    )
            related_debt_id = None
            if record.related_debt_id is not None:
                related_debt_id = debt_id_map.get(int(record.related_debt_id))
                if related_debt_id is None:
                    raise ValueError(
                        f"Record #{record.id} references missing debt #{record.related_debt_id}"
                    )
            new_record_id = self._insert_record_row(
                record,
                wallet_id=wallet_id,
                transfer_id=transfer_id,
                related_debt_id=related_debt_id,
            )
            record_id_map[int(record.id)] = new_record_id
        self._replace_record_tags_many(
            {int(record_id_map[int(record.id)]): tuple(record.tags) for record in records},
            clear_missing=True,
        )
        self._restore_tag_metadata(tags)
        return record_id_map

    def _restore_tag_metadata(self, tags: list[Tag]) -> None:
        inserted_missing = False
        for tag in tags:
            normalized_name = normalize_tag_name(tag.name)
            if not normalized_name:
                continue
            row = self._conn.execute(
                "SELECT id FROM tags WHERE lower(name) = lower(?) LIMIT 1",
                (normalized_name,),
            ).fetchone()
            if row is None:
                cursor = self._conn.execute(
                    """
                    INSERT INTO tags (name, color, usage_count, last_used_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        normalized_name,
                        str(tag.color or "") or color_for_tag(normalized_name),
                        int(tag.usage_count or 0),
                        str(tag.last_used_at or ""),
                    ),
                )
                row_id = self._require_lastrowid(cursor.lastrowid, "tags")
                row = {"id": row_id}
                inserted_missing = True
            self._conn.execute(
                """
                UPDATE tags
                SET name = ?, color = ?, usage_count = ?, last_used_at = ?
                WHERE id = ?
                """,
                (
                    normalized_name,
                    str(tag.color or "") or color_for_tag(normalized_name),
                    int(tag.usage_count or 0),
                    str(tag.last_used_at or ""),
                    int(row["id"]),
                ),
            )
        if inserted_missing:
            self._normalize_tag_ids()

    def _replace_all_mandatory_expenses(
        self,
        mandatory_expenses: list[MandatoryExpenseRecord],
        wallet_id_map: dict[int, int],
    ) -> None:
        for expense in sorted(mandatory_expenses, key=lambda item: item.id):
            wallet_id = wallet_id_map.get(int(expense.wallet_id))
            if wallet_id is None:
                raise ValueError(f"Mandatory expense #{expense.id} references missing wallet")
            self._insert_mandatory_row(expense, wallet_id=wallet_id)

    def _replace_all_debt_payments(
        self,
        debt_payments: list[DebtPayment],
        debt_id_map: dict[int, int],
        record_id_map: dict[int, int],
    ) -> None:
        for payment in sorted(debt_payments, key=lambda item: item.id):
            mapped_debt_id = debt_id_map.get(int(payment.debt_id))
            if mapped_debt_id is None:
                raise ValueError(
                    f"Debt payment #{payment.id} references missing debt #{payment.debt_id}"
                )
            mapped_record_id = None
            if payment.record_id is not None:
                mapped_record_id = record_id_map.get(int(payment.record_id))
                if mapped_record_id is None:
                    raise ValueError(
                        f"Debt payment #{payment.id} references missing record #{payment.record_id}"
                    )
            self._insert_debt_payment_row(
                payment,
                debt_id=mapped_debt_id,
                record_id=mapped_record_id,
            )
