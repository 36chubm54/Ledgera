from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import date as dt_date
from typing import TYPE_CHECKING

from app.data.repository import RecordRepository
from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.goal import Goal
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from infrastructure.sqlite.assets_goals import SQLiteAssetsGoalsMixin
from infrastructure.sqlite.bulk_replace import execute_replace_all_data
from infrastructure.sqlite.debts import SQLiteDebtsMixin
from infrastructure.sqlite.meta_tags import SQLiteMetaTagsMixin
from infrastructure.sqlite.records_wallets import SQLiteRecordsWalletsMixin
from infrastructure.sqlite.row_mutations import SQLiteRowMutationsMixin
from storage.sqlite_storage import SQLiteStorage
from utils.finance.money import rate_to_text, to_minor_units, to_money_float, to_rate_float
from utils.records.tags import color_for_tag, normalize_tag_name, normalize_tag_names

if TYPE_CHECKING:
    pass

SYSTEM_WALLET_ID = 1


class SQLiteRecordRepository(
    SQLiteMetaTagsMixin,
    SQLiteRowMutationsMixin,
    SQLiteRecordsWalletsMixin,
    SQLiteDebtsMixin,
    SQLiteAssetsGoalsMixin,
    RecordRepository,
):
    """RecordRepository implementation backed by SQLite."""

    def __init__(self, db_path: str = "finance.db", schema_path: str | None = None) -> None:
        self._storage = SQLiteStorage(db_path)
        self._storage.initialize_schema(schema_path)
        self._conn = self._storage._conn
        self._normalize_existing_ids_from_one_if_needed()

    def close(self) -> None:
        self._storage.close()

    def create_sqlite_snapshot(self) -> sqlite3.Connection:
        snapshot = sqlite3.connect(":memory:")
        self._conn.backup(snapshot)
        return snapshot

    def restore_sqlite_snapshot(self, snapshot: sqlite3.Connection) -> None:
        self._conn.rollback()
        snapshot.backup(self._conn._conn)
        self._conn.commit()

    @property
    def db_path(self) -> str:
        return str(self._storage._db_path)

    def set_sqlite_sequence(self, table: str, seq: int | None = None) -> None:
        self._storage.set_sqlite_sequence(table, seq)

    def supports_budget_repository(self) -> bool:
        return True

    def supports_distribution_repository(self) -> bool:
        return True

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

    def _default_base_currency(self) -> str:
        schema_currency = str(self.get_schema_meta("base_currency") or "").strip().upper()
        if schema_currency:
            return schema_currency
        row = self._conn.execute(
            """
            SELECT currency
            FROM wallets
            WHERE (system = 1 OR id = ?)
              AND trim(coalesce(currency, '')) <> ''
            ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (SYSTEM_WALLET_ID, SYSTEM_WALLET_ID),
        ).fetchone()
        if row is not None:
            currency = str(row["currency"] or "").strip().upper()
            if currency:
                return currency
        return "KZT"

    @staticmethod
    def _money_columns(
        amount_original: object,
        rate_at_operation: object,
        amount_base: object,
    ) -> tuple[float, int, float, str, float, int]:
        return (
            to_money_float(amount_original),
            to_minor_units(amount_original),
            to_rate_float(rate_at_operation),
            rate_to_text(rate_at_operation),
            to_money_float(amount_base),
            to_minor_units(amount_base),
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
                to_minor_units(record.amount_base or 0.0),
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
            amount_base,
            amount_base_minor,
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
            "amount_base": self._storage._money_from_row(row, "amount_base", "amount_base_minor"),
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
            amount_base=self._storage._money_from_row(row, "amount_base", "amount_base_minor"),
            category=str(row["category"]),
            description=str(row["description"] or ""),
            period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
            date=str(row["date"]) if row["date"] else "",
            auto_pay=bool(row["auto_pay"]),
        )

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
        execute_replace_all_data(
            self,
            initial_balance=initial_balance,
            wallets=wallets,
            records=records,
            mandatory_expenses=mandatory_expenses,
            tags=tags,
            transfers=transfers,
            debts=debts,
            debt_payments=debt_payments,
        )
