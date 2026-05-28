from __future__ import annotations

import sqlite3
from typing import Any, TypedDict, cast

from bridge.ledgera_bridge import RustRepositoryReadCore, get_repository_read_core
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import to_money_float
from utils.records.tags import normalize_tag_name

SYSTEM_WALLET_ID = 1


class _RustRecordRow(TypedDict):
    id: int
    type: str
    date: str
    wallet_id: int
    transfer_id: int | None
    related_debt_id: int | None
    amount_original: float
    currency: str
    rate_at_operation: float
    amount_base: float
    category: str
    description: str
    period: str | None
    tags: list[str]


class _RustTransferRow(TypedDict):
    id: int
    from_wallet_id: int
    to_wallet_id: int
    date: str
    amount_original: float
    currency: str
    rate_at_operation: float
    amount_base: float
    description: str


class _RustWalletRow(TypedDict):
    id: int
    name: str
    currency: str
    initial_balance: float
    system: bool
    allow_negative: bool
    is_active: bool


class _RustMandatoryExpenseRow(TypedDict):
    id: int
    wallet_id: int
    amount_original: float
    currency: str
    rate_at_operation: float
    amount_base: float
    category: str
    description: str
    period: str
    date: str
    auto_pay: bool


_RUST_RECORD_CORE = get_repository_read_core()


def _record_core_has(name: str) -> bool:
    return _RUST_RECORD_CORE is not None and callable(getattr(_RUST_RECORD_CORE, name, None))


class SQLiteRecordsWalletsMixin:
    _conn: Any
    _storage: Any

    def _default_base_currency(self) -> str: ...

    def _record_from_row(self, row: sqlite3.Row, *, tags: tuple[str, ...] = ()) -> Record: ...

    def _mandatory_from_row(self, row: sqlite3.Row) -> MandatoryExpenseRecord: ...

    def _records_base_rows(self) -> list[sqlite3.Row]: ...

    def _record_tags_map(self, record_ids: list[int]) -> dict[int, tuple[str, ...]]: ...

    def _replace_record_tags_many(
        self,
        record_tags: dict[int, tuple[str, ...]],
        *,
        clear_missing: bool = False,
    ) -> None: ...

    def _validate_transfer_integrity(
        self, records: list[Record], transfers: list[Transfer]
    ) -> None: ...

    def _load_debt_payment_record_links(self) -> dict[int, int]: ...

    def _remap_debt_payment_record_ids(
        self,
        record_id_map: dict[int, int],
        payment_record_links: dict[int, int],
    ) -> None: ...

    def _insert_wallet_row(self, wallet: Wallet) -> int: ...

    def _update_wallet_row(self, wallet_id: int, wallet: Wallet) -> None: ...

    def _insert_transfer_row(
        self,
        transfer: Transfer,
        *,
        from_wallet_id: int | None = None,
        to_wallet_id: int | None = None,
    ) -> int: ...

    def _update_transfer_row(
        self,
        transfer_id: int,
        transfer: Transfer,
        *,
        from_wallet_id: int | None = None,
        to_wallet_id: int | None = None,
    ) -> None: ...

    def _insert_record_row(
        self,
        record: Record,
        *,
        wallet_id: int | None = None,
        transfer_id: int | None = None,
        related_debt_id: int | None = None,
    ) -> int: ...

    def _update_record_row(
        self,
        record_id: int,
        record: Record,
        *,
        wallet_id: int | None = None,
        transfer_id: int | None = None,
        related_debt_id: int | None = None,
    ) -> None: ...

    @staticmethod
    def _transfer_from_rust_row(row: _RustTransferRow) -> Transfer:
        return Transfer(
            id=int(row["id"]),
            from_wallet_id=int(row["from_wallet_id"]),
            to_wallet_id=int(row["to_wallet_id"]),
            date=str(row["date"]),
            amount_original=float(row["amount_original"]),
            currency=str(row["currency"]),
            rate_at_operation=float(row["rate_at_operation"]),
            amount_base=float(row["amount_base"]),
            description=str(row["description"] or ""),
        )

    @staticmethod
    def _wallet_from_rust_row(row: _RustWalletRow) -> Wallet:
        return Wallet(
            id=int(row["id"]),
            name=str(row["name"]),
            currency=str(row["currency"]),
            initial_balance=float(row["initial_balance"]),
            system=bool(row["system"]),
            allow_negative=bool(row["allow_negative"]),
            is_active=bool(row["is_active"]),
        )

    def _insert_mandatory_row(self, expense: MandatoryExpenseRecord, *, wallet_id: int) -> int: ...

    def _upsert_system_wallet_balance(self, balance: float) -> None: ...

    @staticmethod
    def _money_columns(
        amount_original: object,
        rate_at_operation: object,
        amount_base: object,
    ) -> tuple[float, int, float, str, float, int]: ...

    def _reset_autoincrement(self, table: str) -> None: ...

    def _reset_autoincrement_many(self, tables: tuple[str, ...]) -> None: ...

    def _prune_orphan_tags(self) -> None: ...

    @staticmethod
    def _select_record_columns() -> str: ...

    def _renormalize_current_ids(self) -> None: ...

    def has_system_wallet_row(self) -> bool: ...

    @staticmethod
    def _record_from_rust_row(row: _RustRecordRow) -> Record:
        record_type = str(row["type"])
        payload = {
            "id": int(row["id"]),
            "date": str(row["date"]),
            "wallet_id": int(row["wallet_id"]),
            "transfer_id": int(row["transfer_id"]) if row["transfer_id"] is not None else None,
            "related_debt_id": (
                int(row["related_debt_id"]) if row["related_debt_id"] is not None else None
            ),
            "amount_original": float(row["amount_original"]),
            "currency": str(row["currency"]),
            "rate_at_operation": float(row["rate_at_operation"]),
            "amount_base": float(row["amount_base"]),
            "category": str(row["category"]),
            "description": str(row["description"] or ""),
            "tags": tuple(str(tag) for tag in cast(list[object], row["tags"])),
        }
        if record_type == "income":
            return IncomeRecord(**payload)
        if record_type == "mandatory_expense":
            return MandatoryExpenseRecord(
                **payload,
                period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
            )
        return ExpenseRecord(**payload)

    @staticmethod
    def _mandatory_from_rust_row(row: _RustMandatoryExpenseRow) -> MandatoryExpenseRecord:
        return MandatoryExpenseRecord(
            id=int(row["id"]),
            wallet_id=int(row["wallet_id"]),
            amount_original=float(row["amount_original"]),
            currency=str(row["currency"]),
            rate_at_operation=float(row["rate_at_operation"]),
            amount_base=float(row["amount_base"]),
            category=str(row["category"]),
            description=str(row["description"] or ""),
            period=str(row["period"] or "monthly"),  # type: ignore[arg-type]
            date=str(row["date"] or ""),
            auto_pay=bool(row["auto_pay"]),
        )

    def _can_use_rust_record_core(self, name: str) -> bool:
        db_path = getattr(self, "db_path", None)
        if not isinstance(db_path, str) or not db_path:
            return False
        if getattr(self._conn, "in_transaction", False):
            return False
        return _record_core_has(name)

    def load_active_wallets(self) -> list[Wallet]:
        if self._can_use_rust_record_core("wallet_list_rows"):
            return [wallet for wallet in self.load_wallets() if wallet.is_active]
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
                currency=str(currency or self._default_base_currency()).upper(),
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
        db_path = str(getattr(self, "db_path", ""))
        if self._can_use_rust_record_core("wallet_list_rows"):
            return [
                self._wallet_from_rust_row(cast(_RustWalletRow, raw_row))
                for raw_row in cast(RustRepositoryReadCore, _RUST_RECORD_CORE).wallet_list_rows(
                    db_path
                )
            ]
        return self._storage.get_wallets()

    def get_system_wallet(self) -> Wallet:
        for wallet in self.load_wallets():
            if wallet.system or wallet.id == SYSTEM_WALLET_ID:
                return wallet
        return Wallet(
            id=SYSTEM_WALLET_ID,
            name="Main wallet",
            currency=self._default_base_currency(),
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
        db_path = str(getattr(self, "db_path", ""))
        if self._can_use_rust_record_core("transfer_list_rows"):
            return [
                self._transfer_from_rust_row(cast(_RustTransferRow, raw_row))
                for raw_row in cast(RustRepositoryReadCore, _RUST_RECORD_CORE).transfer_list_rows(
                    db_path
                )
            ]
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
        db_path = str(getattr(self, "db_path", ""))
        if self._can_use_rust_record_core("record_list_rows"):
            return [
                self._record_from_rust_row(cast(_RustRecordRow, raw_row))
                for raw_row in cast(RustRepositoryReadCore, _RUST_RECORD_CORE).record_list_rows(
                    db_path
                )
            ]
        rows = self._records_base_rows()
        tags_map = self._record_tags_map([int(row["id"]) for row in rows])
        return [self._record_from_row(row, tags=tags_map.get(int(row["id"]), ())) for row in rows]

    def list_all(self) -> list[Record]:
        return self.load_all()

    def get_by_id(self, record_id: int) -> Record:
        record_id = int(record_id)
        db_path = str(getattr(self, "db_path", ""))
        if self._can_use_rust_record_core("record_get_row"):
            row = cast(RustRepositoryReadCore, _RUST_RECORD_CORE).record_get_row(db_path, record_id)
            if row is not None:
                return self._record_from_rust_row(cast(_RustRecordRow, row))
            raise ValueError(f"Record not found: {record_id}")
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
                amount_base,
                amount_base_minor,
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
        db_path = str(getattr(self, "db_path", ""))
        if self._can_use_rust_record_core("record_rows_by_tag"):
            return [
                self._record_from_rust_row(cast(_RustRecordRow, raw_row))
                for raw_row in cast(RustRepositoryReadCore, _RUST_RECORD_CORE).record_rows_by_tag(
                    db_path, tag_name
                )
            ]
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
        db_path = getattr(self, "db_path", None)
        if self._can_use_rust_record_core("transfer_id_by_record_index"):
            return cast(RustRepositoryReadCore, _RUST_RECORD_CORE).transfer_id_by_record_index(
                str(db_path), int(index)
            )
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
        db_path = getattr(self, "db_path", None)
        if self._can_use_rust_record_core("mandatory_expense_rows"):
            return [
                self._mandatory_from_rust_row(cast(_RustMandatoryExpenseRow, raw_row))
                for raw_row in cast(
                    RustRepositoryReadCore, _RUST_RECORD_CORE
                ).mandatory_expense_rows(str(db_path))
            ]
        return self._storage.get_mandatory_expenses()

    def get_mandatory_expense_by_id(self, expense_id: int) -> MandatoryExpenseRecord:
        db_path = getattr(self, "db_path", None)
        if self._can_use_rust_record_core("mandatory_expense_row"):
            row = cast(RustRepositoryReadCore, _RUST_RECORD_CORE).mandatory_expense_row(
                str(db_path), int(expense_id)
            )
            if row is not None:
                return self._mandatory_from_rust_row(cast(_RustMandatoryExpenseRow, row))
            raise ValueError(f"Mandatory expense не найден: {expense_id}")
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
                amount_base,
                amount_base_minor,
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
            amount_base,
            amount_base_minor,
        ) = self._money_columns(
            expense.amount_original or 0.0,
            expense.rate_at_operation,
            expense.amount_base or 0.0,
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
                    amount_base        = ?,
                    amount_base_minor  = ?,
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
                    amount_base,
                    amount_base_minor,
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

    def replace_mandatory_expenses(self, expenses: list[MandatoryExpenseRecord]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM mandatory_expenses")
            self._reset_autoincrement("mandatory_expenses")
            for expense in sorted(expenses, key=lambda item: item.id):
                self._insert_mandatory_row(expense, wallet_id=int(expense.wallet_id))
