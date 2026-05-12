from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage
from utils.backup_utils import unwrap_backup_payload
from utils.money import minor_to_money, rate_to_text, to_minor_units, to_money_float, to_rate_float
from utils.tag_utils import color_for_tag, normalize_tag_name, normalize_tag_names

PROJECT_ROOT = Path(__file__).resolve().parent
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _resolve_schema_path(schema_path: str) -> str:
    candidate = Path(schema_path)
    if candidate.is_absolute():
        return str(candidate)
    return str((Path(__file__).resolve().parent / candidate).resolve())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate financial data from JSON storage to SQLite storage."
    )
    parser.add_argument(
        "--json-path",
        default=str(PROJECT_ROOT / "data.json"),
        help="Path to source JSON file (default: <project>/data.json)",
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(PROJECT_ROOT / "finance.db"),
        help="Path to target SQLite database (default: <project>/finance.db)",
    )
    parser.add_argument(
        "--schema-path",
        default=str(PROJECT_ROOT / "db" / "schema.sql"),
        help="Path to SQLite schema.sql (default: <project>/db/schema.sql)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate source and target connection without inserting data",
    )
    return parser.parse_args()


def _require_existing_wallet(wallets: list[Wallet], wallet_id: int, owner: str) -> None:
    if wallet_id <= 0:
        raise ValueError(f"{owner}: wallet_id must be positive, got {wallet_id}")
    wallet_ids = {wallet.id for wallet in wallets}
    if wallet_id not in wallet_ids:
        raise ValueError(f"{owner}: wallet_id={wallet_id} does not exist")


def _validate_source_integrity(
    wallets: list[Wallet],
    records: list[Record],
    transfers: list,
    mandatory_expenses: list[MandatoryExpenseRecord],
    budgets: list[Budget],
    debts: list[Debt],
    debt_payments: list[DebtPayment],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    distribution_items: list[DistributionItem],
    distribution_subitems: list[DistributionSubitem],
    distribution_snapshots: list[FrozenDistributionRow],
) -> None:
    wallet_ids = {wallet.id for wallet in wallets}
    if not wallet_ids:
        raise ValueError("Source JSON has no wallets")

    transfer_ids = {transfer.id for transfer in transfers}
    linked_records_by_transfer: dict[int, list[Record]] = {}

    for transfer in transfers:
        if transfer.id <= 0:
            raise ValueError(f"Transfer id must be positive, got {transfer.id}")
        if transfer.from_wallet_id not in wallet_ids or transfer.to_wallet_id not in wallet_ids:
            raise ValueError(
                f"Transfer #{transfer.id} has missing wallet links: "
                f"from={transfer.from_wallet_id} to={transfer.to_wallet_id}"
            )

    debt_ids = {int(debt.id) for debt in debts}
    record_ids = {int(record.id) for record in records}
    asset_ids = {int(asset.id) for asset in assets}

    for record in records:
        _require_existing_wallet(wallets, int(record.wallet_id), f"Record #{record.id}")
        if record.transfer_id is not None:
            if record.transfer_id not in transfer_ids:
                raise ValueError(
                    f"Record #{record.id} references missing transfer_id={record.transfer_id}"
                )
            linked_records_by_transfer.setdefault(record.transfer_id, []).append(record)
        if record.related_debt_id is not None and int(record.related_debt_id) not in debt_ids:
            raise ValueError(
                f"Record #{record.id} references missing related_debt_id={record.related_debt_id}"
            )

    for transfer_id, linked_records in linked_records_by_transfer.items():
        if len(linked_records) != 2:
            raise ValueError(
                f"Transfer #{transfer_id} must have exactly 2 records, got {len(linked_records)}"
            )
        linked_types = {record.type for record in linked_records}
        if linked_types != {"income", "expense"}:
            raise ValueError(
                f"Transfer #{transfer_id} must have one income and one expense, got {linked_types}"
            )

    for transfer in transfers:
        linked_records = linked_records_by_transfer.get(transfer.id, [])
        if len(linked_records) != 2:
            raise ValueError(
                f"Transfer #{transfer.id} has invalid linked record count: {len(linked_records)}"
            )

    for expense in mandatory_expenses:
        _require_existing_wallet(wallets, int(expense.wallet_id), f"MandatoryExpense #{expense.id}")

    payment_ids: set[int] = set()
    for payment in debt_payments:
        payment_id = int(payment.id)
        if payment_id in payment_ids:
            raise ValueError(f"Duplicate debt payment id: {payment_id}")
        payment_ids.add(payment_id)
        if int(payment.debt_id) not in debt_ids:
            raise ValueError(
                f"DebtPayment #{payment_id} references missing debt_id={payment.debt_id}"
            )
        if payment.record_id is not None and int(payment.record_id) not in record_ids:
            raise ValueError(
                f"DebtPayment #{payment_id} references missing record_id={payment.record_id}"
            )

    for snapshot in asset_snapshots:
        if int(snapshot.asset_id) not in asset_ids:
            raise ValueError(
                f"AssetSnapshot #{snapshot.id} references missing asset_id={snapshot.asset_id}"
            )

    goal_ids: set[int] = set()
    for goal in goals:
        goal_id = int(goal.id)
        if goal_id in goal_ids:
            raise ValueError(f"Duplicate goal id: {goal_id}")
        goal_ids.add(goal_id)

    seen_budget_ids: set[int] = set()
    for budget in budgets:
        budget_id = int(budget.id)
        if budget_id <= 0:
            raise ValueError(f"Budget id must be positive, got {budget.id}")
        if budget_id in seen_budget_ids:
            raise ValueError(f"Duplicate budget id: {budget_id}")
        if not str(budget.category).strip():
            raise ValueError(f"Budget #{budget_id} has empty category")
        if not str(budget.start_date).strip() or not str(budget.end_date).strip():
            raise ValueError(f"Budget #{budget_id} is missing start_date/end_date")
        if str(budget.start_date) > str(budget.end_date):
            raise ValueError(
                f"Budget #{budget_id} has invalid period: {budget.start_date} > {budget.end_date}"
            )
        if int(budget.limit_base_minor) <= 0:
            raise ValueError(f"Budget #{budget_id} must have positive limit_base_minor")
        seen_budget_ids.add(budget_id)

    item_ids = {int(item.id) for item in distribution_items}
    for subitem in distribution_subitems:
        if int(subitem.item_id) not in item_ids:
            raise ValueError(
                f"Distribution subitem #{subitem.id} references missing item_id={subitem.item_id}"
            )

    seen_snapshot_months: set[str] = set()
    for snapshot in distribution_snapshots:
        month = str(snapshot.month).strip()
        if not _MONTH_RE.fullmatch(month):
            raise ValueError(f"Distribution snapshot month must be YYYY-MM, got {snapshot.month!r}")
        if month in seen_snapshot_months:
            raise ValueError(f"Duplicate distribution snapshot month: {month}")
        seen_snapshot_months.add(month)


def _check_target_is_empty(sqlite_storage: SQLiteStorage) -> None:
    tables = (
        "wallets",
        "transfers",
        "records",
        "mandatory_expenses",
        "budgets",
        "distribution_items",
        "distribution_subitems",
        "distribution_snapshots",
        "distribution_snapshot_values",
        "debts",
        "debt_payments",
    )
    for table in tables:
        row = sqlite_storage.query_one(f"SELECT COUNT(*) FROM {table}")
        count = int(row[0]) if row else 0
        if count > 0:
            raise RuntimeError(
                f"Target SQLite is not empty: table '{table}' already contains {count} rows"
            )


def _has_any_data(sqlite_storage: SQLiteStorage) -> bool:
    for table in (
        "wallets",
        "transfers",
        "records",
        "mandatory_expenses",
        "budgets",
        "distribution_items",
        "distribution_subitems",
        "distribution_snapshots",
        "distribution_snapshot_values",
        "debts",
        "debt_payments",
    ):
        row = sqlite_storage.query_one(f"SELECT COUNT(*) FROM {table}")
        count = int(row[0]) if row else 0
        if count > 0:
            return True
    return False


def _all_positive_unique_ids(items: list, id_getter) -> bool:
    ids = [int(id_getter(item)) for item in items]
    return all(value > 0 for value in ids) and len(ids) == len(set(ids))


def _materialize_tags(tags: list[Tag], records: list[Record]) -> list[Tag]:
    usage_by_name: dict[str, int] = {}
    last_used_by_name: dict[str, str] = {}
    for record in records:
        record_date = (
            record.date.isoformat()
            if hasattr(record.date, "isoformat") and not isinstance(record.date, str)
            else str(record.date or "")
        )
        for tag_name in normalize_tag_names(tuple(getattr(record, "tags", ()) or ())):
            key = tag_name.casefold()
            usage_by_name[key] = usage_by_name.get(key, 0) + 1
            if record_date and record_date > last_used_by_name.get(key, ""):
                last_used_by_name[key] = record_date

    tags_by_name: dict[str, Tag] = {}
    for tag in tags:
        normalized_name = normalize_tag_name(tag.name)
        if not normalized_name:
            continue
        key = normalized_name.casefold()
        tags_by_name[key] = Tag(
            id=int(tag.id),
            name=normalized_name,
            color=str(tag.color or color_for_tag(normalized_name)),
            usage_count=(
                int(tag.usage_count)
                if int(getattr(tag, "usage_count", 0) or 0) > 0
                else usage_by_name.get(key, 0)
            ),
            last_used_at=str(tag.last_used_at or last_used_by_name.get(key, "")),
        )

    for record in records:
        for tag_name in normalize_tag_names(tuple(getattr(record, "tags", ()) or ())):
            key = tag_name.casefold()
            if key in tags_by_name:
                continue
            tags_by_name[key] = Tag(
                id=0,
                name=tag_name,
                color=color_for_tag(tag_name),
                usage_count=usage_by_name.get(key, 0),
                last_used_at=last_used_by_name.get(key, ""),
            )

    return sorted(
        tags_by_name.values(),
        key=lambda item: (item.id <= 0, item.id, item.name.casefold(), item.name),
    )


def _expected_record_tag_count(records: list[Record]) -> int:
    return sum(
        len(normalize_tag_names(tuple(getattr(record, "tags", ()) or ()))) for record in records
    )


def _set_sqlite_sequence(sqlite_storage: SQLiteStorage, table: str) -> None:
    sqlite_storage.set_sqlite_sequence(table)


def _wallet_balance_payload(balance: object) -> tuple[float, int]:
    return (to_money_float(balance), to_minor_units(balance))


def _money_payload(
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


def _insert_wallets(sqlite_storage: SQLiteStorage, wallets: list[Wallet]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(wallets, lambda wallet: wallet.id)
    for wallet in wallets:
        initial_balance, initial_balance_minor = _wallet_balance_payload(wallet.initial_balance)
        if preserve_ids:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO wallets (
                    id, name, currency, initial_balance, initial_balance_minor,
                    system, allow_negative, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(wallet.id),
                    wallet.name,
                    wallet.currency.upper(),
                    initial_balance,
                    initial_balance_minor,
                    int(bool(wallet.system)),
                    int(bool(wallet.allow_negative)),
                    int(bool(wallet.is_active)),
                ),
            )
            mapping[int(wallet.id)] = int(wallet.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO wallets (
                    name, currency, initial_balance, initial_balance_minor,
                    system, allow_negative, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wallet.name,
                    wallet.currency.upper(),
                    initial_balance,
                    initial_balance_minor,
                    int(bool(wallet.system)),
                    int(bool(wallet.allow_negative)),
                    int(bool(wallet.is_active)),
                ),
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert wallet: no row ID returned")
            mapping[int(wallet.id)] = int(lastrowid)
    if preserve_ids:
        _set_sqlite_sequence(sqlite_storage, "wallets")
    return mapping


def _insert_transfers(
    sqlite_storage: SQLiteStorage, transfers: list, wallet_map: dict[int, int]
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(transfers, lambda transfer: transfer.id)
    for transfer in transfers:
        from_wallet_id = wallet_map[int(transfer.from_wallet_id)]
        to_wallet_id = wallet_map[int(transfer.to_wallet_id)]
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = _money_payload(
            transfer.amount_original,
            transfer.rate_at_operation,
            transfer.amount_base,
        )
        if preserve_ids:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO transfers (
                    id, from_wallet_id, to_wallet_id, date,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(transfer.id),
                    from_wallet_id,
                    to_wallet_id,
                    (
                        transfer.date.isoformat()
                        if hasattr(transfer.date, "isoformat")
                        else str(transfer.date)
                    ),
                    amount_original,
                    amount_original_minor,
                    transfer.currency.upper(),
                    rate_at_operation,
                    rate_at_operation_text,
                    amount_base,
                    amount_base_minor,
                    transfer.description or "",
                ),
            )
            mapping[int(transfer.id)] = int(transfer.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO transfers (
                    from_wallet_id, to_wallet_id, date,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    from_wallet_id,
                    to_wallet_id,
                    (
                        transfer.date.isoformat()
                        if hasattr(transfer.date, "isoformat")
                        else str(transfer.date)
                    ),
                    amount_original,
                    amount_original_minor,
                    transfer.currency.upper(),
                    rate_at_operation,
                    rate_at_operation_text,
                    amount_base,
                    amount_base_minor,
                    transfer.description or "",
                ),
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert transfer: no row ID returned")
            mapping[int(transfer.id)] = int(lastrowid)
    if preserve_ids:
        _set_sqlite_sequence(sqlite_storage, "transfers")
    return mapping


def _record_row_payload(
    record: Record, wallet_map: dict[int, int], transfer_map: dict[int, int]
) -> tuple:
    transfer_id = None
    if record.transfer_id is not None:
        transfer_id = transfer_map[int(record.transfer_id)]
    period = record.period if isinstance(record, MandatoryExpenseRecord) else None
    (
        amount_original,
        amount_original_minor,
        rate_at_operation,
        rate_at_operation_text,
        amount_base,
        amount_base_minor,
    ) = _money_payload(
        record.amount_original or 0.0,
        record.rate_at_operation,
        record.amount_base or 0.0,
    )
    return (
        (
            record.date.isoformat()
            if hasattr(record.date, "isoformat") and not isinstance(record.date, str)
            else str(record.date)
        ),
        wallet_map[int(record.wallet_id)],
        transfer_id,
        int(record.related_debt_id) if record.related_debt_id is not None else None,
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
        "mandatory_expense" if isinstance(record, MandatoryExpenseRecord) else str(record.type),
    )


def _insert_records(
    sqlite_storage: SQLiteStorage,
    records: list[Record],
    wallet_map: dict[int, int],
    transfer_map: dict[int, int],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(records, lambda record: record.id)
    for record in records:
        payload = _record_row_payload(record, wallet_map, transfer_map)
        if preserve_ids:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO records (
                    id, type, date, wallet_id, transfer_id, related_debt_id,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor,
                    category, description, period
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(record.id),
                    payload[14],
                    payload[0],
                    payload[1],
                    payload[2],
                    payload[3],
                    payload[4],
                    payload[5],
                    payload[6],
                    payload[7],
                    payload[8],
                    payload[9],
                    payload[10],
                    payload[11],
                    payload[12],
                    payload[13],
                ),
            )
            mapping[int(record.id)] = int(record.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO records (
                    type, date, wallet_id, transfer_id, related_debt_id,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor,
                    category, description, period
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload[14],
                    payload[0],
                    payload[1],
                    payload[2],
                    payload[3],
                    payload[4],
                    payload[5],
                    payload[6],
                    payload[7],
                    payload[8],
                    payload[9],
                    payload[10],
                    payload[11],
                    payload[12],
                    payload[13],
                ),
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert record: no row ID returned")
            mapping[int(record.id)] = int(lastrowid)
    if preserve_ids:
        _set_sqlite_sequence(sqlite_storage, "records")
    return mapping


def _insert_tags(
    sqlite_storage: SQLiteStorage,
    tags: list[Tag],
    records: list[Record],
    record_map: dict[int, int],
) -> dict[str, int]:
    mapping: dict[str, int] = {}
    materialized_tags = _materialize_tags(tags, records)
    explicit_ids = [int(tag.id) for tag in materialized_tags if int(tag.id) > 0]
    preserve_tag_ids = len(explicit_ids) == len(set(explicit_ids))

    for tag in materialized_tags:
        payload = (
            str(tag.name),
            str(tag.color or color_for_tag(tag.name)),
            int(tag.usage_count),
            str(tag.last_used_at or ""),
        )
        if preserve_tag_ids and int(tag.id) > 0:
            sqlite_storage.execute(
                """
                INSERT INTO tags (id, name, color, usage_count, last_used_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(tag.id), *payload),
            )
            mapping[str(tag.name).casefold()] = int(tag.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO tags (name, color, usage_count, last_used_at)
                VALUES (?, ?, ?, ?)
                """,
                payload,
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert tag: no row ID returned")
            mapping[str(tag.name).casefold()] = int(lastrowid)

    for record in records:
        sqlite_record_id = record_map[int(record.id)]
        for tag_name in normalize_tag_names(tuple(getattr(record, "tags", ()) or ())):
            sqlite_tag_id = mapping[tag_name.casefold()]
            sqlite_storage.execute(
                "INSERT OR IGNORE INTO record_tags (record_id, tag_id) VALUES (?, ?)",
                (sqlite_record_id, sqlite_tag_id),
            )

    if preserve_tag_ids and explicit_ids:
        _set_sqlite_sequence(sqlite_storage, "tags")
    return mapping


def _insert_mandatory_expenses(
    sqlite_storage: SQLiteStorage,
    expenses: list[MandatoryExpenseRecord],
    wallet_map: dict[int, int],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(expenses, lambda expense: expense.id)
    for expense in expenses:
        (
            amount_original,
            amount_original_minor,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
        ) = _money_payload(
            expense.amount_original or 0.0,
            expense.rate_at_operation,
            expense.amount_base or 0.0,
        )
        if preserve_ids:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO mandatory_expenses (
                    id, wallet_id,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor,
                    category, description, period, date, auto_pay
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(expense.id),
                    wallet_map[int(expense.wallet_id)],
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
            mapping[int(expense.id)] = int(expense.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO mandatory_expenses (
                    wallet_id,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor,
                    category, description, period, date, auto_pay
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wallet_map[int(expense.wallet_id)],
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
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert mandatory expense: no row ID returned")
            mapping[int(expense.id)] = int(lastrowid)
    if preserve_ids:
        _set_sqlite_sequence(sqlite_storage, "mandatory_expenses")
    return mapping


def _insert_budgets(sqlite_storage: SQLiteStorage, budgets: list[Budget]) -> None:
    preserve_ids = _all_positive_unique_ids(budgets, lambda budget: budget.id)
    for budget in budgets:
        payload = (
            str(budget.category),
            str(budget.scope_type),
            str(budget.scope_value),
            str(budget.start_date),
            str(budget.end_date),
            to_money_float(budget.limit_base),
            int(budget.limit_base_minor),
            int(bool(budget.include_mandatory)),
        )
        if preserve_ids:
            sqlite_storage.execute(
                """
                INSERT INTO budgets (
                    id, category, scope_type, scope_value, start_date, end_date,
                    limit_base, limit_base_minor, include_mandatory
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(budget.id), *payload),
            )
        else:
            sqlite_storage.execute(
                """
                INSERT INTO budgets (
                    category, scope_type, scope_value, start_date, end_date,
                    limit_base, limit_base_minor, include_mandatory
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
    if preserve_ids and budgets:
        _set_sqlite_sequence(sqlite_storage, "budgets")


def _insert_debts(sqlite_storage: SQLiteStorage, debts: list[Debt]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(debts, lambda debt: debt.id)
    for debt in debts:
        payload = (
            str(debt.contact_name),
            str(debt.kind.value),
            int(debt.total_amount_minor),
            int(debt.remaining_amount_minor),
            str(debt.currency).upper(),
            float(debt.interest_rate),
            str(debt.status.value),
            str(debt.created_at),
            str(debt.closed_at) if debt.closed_at else None,
        )
        if preserve_ids:
            sqlite_storage.execute(
                """
                INSERT INTO debts (
                    id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                    currency, interest_rate, status, created_at, closed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(debt.id), *payload),
            )
            mapping[int(debt.id)] = int(debt.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO debts (
                    contact_name, kind, total_amount_minor, remaining_amount_minor,
                    currency, interest_rate, status, created_at, closed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert debt: no row ID returned")
            mapping[int(debt.id)] = int(lastrowid)
    if preserve_ids and debts:
        _set_sqlite_sequence(sqlite_storage, "debts")
    return mapping


def _insert_debt_payments(
    sqlite_storage: SQLiteStorage,
    debt_payments: list[DebtPayment],
    debt_map: dict[int, int],
    record_map: dict[int, int],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(debt_payments, lambda payment: payment.id)
    for payment in debt_payments:
        payload = (
            debt_map[int(payment.debt_id)],
            record_map[int(payment.record_id)] if payment.record_id is not None else None,
            str(payment.operation_type.value),
            int(payment.principal_paid_minor),
            int(bool(payment.is_write_off)),
            str(payment.payment_date),
        )
        if preserve_ids:
            sqlite_storage.execute(
                """
                INSERT INTO debt_payments (
                    id, debt_id, record_id, operation_type,
                    principal_paid_minor, is_write_off, payment_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (int(payment.id), *payload),
            )
            mapping[int(payment.id)] = int(payment.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO debt_payments (
                    debt_id, record_id, operation_type,
                    principal_paid_minor, is_write_off, payment_date
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert debt payment: no row ID returned")
            mapping[int(payment.id)] = int(lastrowid)
    if preserve_ids and debt_payments:
        _set_sqlite_sequence(sqlite_storage, "debt_payments")
    return mapping


def _insert_assets(sqlite_storage: SQLiteStorage, assets: list[Asset]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(assets, lambda asset: asset.id)
    for asset in assets:
        payload = (
            str(asset.name),
            str(asset.category.value),
            str(asset.currency).upper(),
            int(bool(asset.is_active)),
            str(asset.created_at),
            str(asset.description or ""),
        )
        if preserve_ids:
            sqlite_storage.execute(
                """
                INSERT INTO assets (
                    id, name, category, currency, is_active, created_at, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (int(asset.id), *payload),
            )
            mapping[int(asset.id)] = int(asset.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO assets (
                    name, category, currency, is_active, created_at, description
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert asset: no row ID returned")
            mapping[int(asset.id)] = int(lastrowid)
    if preserve_ids and assets:
        _set_sqlite_sequence(sqlite_storage, "assets")
    return mapping


def _insert_asset_snapshots(
    sqlite_storage: SQLiteStorage,
    asset_snapshots: list[AssetSnapshot],
    asset_map: dict[int, int],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(asset_snapshots, lambda snapshot: snapshot.id)
    for snapshot in asset_snapshots:
        payload = (
            asset_map[int(snapshot.asset_id)],
            str(snapshot.snapshot_date),
            int(snapshot.value_minor),
            str(snapshot.currency).upper(),
            str(snapshot.note or ""),
        )
        if preserve_ids:
            sqlite_storage.execute(
                """
                INSERT INTO asset_snapshots (
                    id, asset_id, snapshot_date, value_minor, currency, note
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(snapshot.id), *payload),
            )
            mapping[int(snapshot.id)] = int(snapshot.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO asset_snapshots (
                    asset_id, snapshot_date, value_minor, currency, note
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                payload,
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert asset snapshot: no row ID returned")
            mapping[int(snapshot.id)] = int(lastrowid)
    if preserve_ids and asset_snapshots:
        _set_sqlite_sequence(sqlite_storage, "asset_snapshots")
    return mapping


def _insert_goals(sqlite_storage: SQLiteStorage, goals: list[Goal]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    preserve_ids = _all_positive_unique_ids(goals, lambda goal: goal.id)
    for goal in goals:
        payload = (
            str(goal.title),
            int(goal.target_amount_minor),
            str(goal.currency).upper(),
            str(goal.target_date) if goal.target_date else None,
            int(bool(goal.is_completed)),
            str(goal.created_at),
            str(goal.description or ""),
        )
        if preserve_ids:
            sqlite_storage.execute(
                """
                INSERT INTO goals (
                    id, title, target_amount_minor, currency, target_date,
                    is_completed, created_at, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(goal.id), *payload),
            )
            mapping[int(goal.id)] = int(goal.id)
        else:
            cursor = sqlite_storage.execute(
                """
                INSERT INTO goals (
                    title, target_amount_minor, currency, target_date,
                    is_completed, created_at, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("Failed to insert goal: no row ID returned")
            mapping[int(goal.id)] = int(lastrowid)
    if preserve_ids and goals:
        _set_sqlite_sequence(sqlite_storage, "goals")
    return mapping


def _counts_from_sqlite(sqlite_storage: SQLiteStorage) -> dict[str, int]:
    def _get_counts(table_name: str) -> int:
        row = sqlite_storage.query_one(f"SELECT COUNT(*) FROM {table_name}")
        return int(row[0]) if row else 0

    return {
        "wallets": _get_counts("wallets"),
        "transfers": _get_counts("transfers"),
        "records": _get_counts("records"),
        "mandatory_expenses": _get_counts("mandatory_expenses"),
        "budgets": _get_counts("budgets"),
        "debts": _get_counts("debts"),
        "debt_payments": _get_counts("debt_payments"),
        "assets": _get_counts("assets"),
        "asset_snapshots": _get_counts("asset_snapshots"),
        "goals": _get_counts("goals"),
        "distribution_items": _get_counts("distribution_items"),
        "distribution_subitems": _get_counts("distribution_subitems"),
        "distribution_snapshots": _get_counts("distribution_snapshots"),
        "tags": _get_counts("tags"),
        "record_tags": _get_counts("record_tags"),
    }


def _wallet_balances_minor_from_json(
    wallets: list[Wallet], records: list[Record]
) -> dict[int, int]:
    result = {wallet.id: to_minor_units(wallet.initial_balance) for wallet in wallets}
    for record in records:
        result[int(record.wallet_id)] = result.get(int(record.wallet_id), 0) + to_minor_units(
            record.signed_amount_base()
        )
    return result


def _wallet_balances_minor_from_sqlite(sqlite_storage: SQLiteStorage) -> dict[int, int]:
    rows = sqlite_storage.query_all(
        """
        SELECT
            w.id AS wallet_id,
            COALESCE(
                w.initial_balance_minor,
                CAST(ROUND(w.initial_balance * 100.0) AS INTEGER),
                0
            )
            + COALESCE(
                SUM(
                    CASE
                        WHEN r.type = 'income' THEN
                            COALESCE(
                                r.amount_base_minor,
                                CAST(ROUND(r.amount_base * 100.0) AS INTEGER),
                                0
                            )
                        ELSE -ABS(
                            COALESCE(
                                r.amount_base_minor,
                                CAST(ROUND(r.amount_base * 100.0) AS INTEGER),
                                0
                            )
                        )
                    END
                ),
                0
            ) AS balance
        FROM wallets AS w
        LEFT JOIN records AS r ON r.wallet_id = w.id
        GROUP BY w.id, w.initial_balance, w.initial_balance_minor
        ORDER BY w.id
        """
    )
    return {int(row[0]): int(row[1]) for row in rows}


def _wallet_signatures_from_json(
    wallets: list[Wallet],
    *,
    wallet_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (
            wallet_map[int(wallet.id)],
            str(wallet.name),
            str(wallet.currency).upper(),
            int(to_minor_units(wallet.initial_balance or 0.0)),
            bool(wallet.system),
            bool(wallet.allow_negative),
            bool(wallet.is_active),
        )
        for wallet in wallets
    )


def _wallet_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, name, currency, initial_balance_minor, system, allow_negative, is_active
        FROM wallets
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            str(row[1]),
            str(row[2]).upper(),
            int(row[3]),
            bool(row[4]),
            bool(row[5]),
            bool(row[6]),
        )
        for row in rows
    ]


def _transfer_signatures_from_json(
    transfers: list[Transfer],
    *,
    wallet_map: dict[int, int],
    transfer_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (
            transfer_map[int(transfer.id)],
            wallet_map[int(transfer.from_wallet_id)],
            wallet_map[int(transfer.to_wallet_id)],
            str(transfer.date),
            int(to_minor_units(transfer.amount_original or 0.0)),
            str(transfer.currency).upper(),
            rate_to_text(transfer.rate_at_operation),
            int(to_minor_units(transfer.amount_base or 0.0)),
            str(transfer.description or ""),
        )
        for transfer in transfers
    )


def _transfer_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, from_wallet_id, to_wallet_id, date,
               amount_original_minor, currency, rate_at_operation_text,
               amount_base_minor, description
        FROM transfers
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            int(row[1]),
            int(row[2]),
            str(row[3]),
            int(row[4]),
            str(row[5]).upper(),
            str(row[6]),
            int(row[7]),
            str(row[8] or ""),
        )
        for row in rows
    ]


def _record_signatures_from_json(
    records: list[Record],
    *,
    wallet_map: dict[int, int],
    transfer_map: dict[int, int],
    debt_map: dict[int, int],
    record_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (
            record_map[int(record.id)],
            str(record.type),
            str(record.date),
            wallet_map[int(record.wallet_id)],
            transfer_map[int(record.transfer_id)] if record.transfer_id is not None else None,
            debt_map[int(record.related_debt_id)] if record.related_debt_id is not None else None,
            int(to_minor_units(record.amount_original or 0.0)),
            str(record.currency).upper(),
            rate_to_text(record.rate_at_operation),
            int(to_minor_units(record.amount_base or 0.0)),
            str(record.category),
            str(record.description or ""),
            (
                str(record.period)
                if isinstance(record, MandatoryExpenseRecord) and record.period is not None
                else None
            ),
        )
        for record in records
    )


def _record_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, type, date, wallet_id, transfer_id, related_debt_id,
               amount_original_minor, currency, rate_at_operation_text,
               amount_base_minor, category, description, period
        FROM records
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            str(row[1]),
            str(row[2]),
            int(row[3]),
            int(row[4]) if row[4] is not None else None,
            int(row[5]) if row[5] is not None else None,
            int(row[6]),
            str(row[7]).upper(),
            str(row[8]),
            int(row[9]),
            str(row[10]),
            str(row[11] or ""),
            str(row[12]) if row[12] is not None else None,
        )
        for row in rows
    ]


def _tag_signatures_from_json(tags: list[Tag], records: list[Record]) -> list[tuple]:
    return sorted(
        (
            str(tag.name),
            str(tag.color or color_for_tag(tag.name)),
            int(tag.usage_count),
            str(tag.last_used_at or ""),
        )
        for tag in _materialize_tags(tags, records)
    )


def _tag_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT name, color, usage_count, last_used_at
        FROM tags
        ORDER BY lower(name), name
        """
    )
    return [(str(row[0]), str(row[1] or ""), int(row[2]), str(row[3] or "")) for row in rows]


def _record_tag_signatures_from_json(
    records: list[Record],
    *,
    record_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (record_map[int(record.id)], tag_name)
        for record in records
        for tag_name in normalize_tag_names(tuple(getattr(record, "tags", ()) or ()))
    )


def _record_tag_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT rt.record_id, t.name
        FROM record_tags AS rt
        JOIN tags AS t ON t.id = rt.tag_id
        ORDER BY rt.record_id, lower(t.name), t.name
        """
    )
    return [(int(row[0]), str(row[1])) for row in rows]


def _mandatory_signatures_from_json(
    mandatory_expenses: list[MandatoryExpenseRecord],
    *,
    wallet_map: dict[int, int],
    mandatory_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (
            mandatory_map[int(expense.id)],
            str(expense.date),
            wallet_map[int(expense.wallet_id)],
            int(to_minor_units(expense.amount_original or 0.0)),
            str(expense.currency).upper(),
            rate_to_text(expense.rate_at_operation),
            int(to_minor_units(expense.amount_base or 0.0)),
            str(expense.category),
            str(expense.description or ""),
            str(expense.period),
            bool(expense.auto_pay),
        )
        for expense in mandatory_expenses
    )


def _mandatory_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, date, wallet_id, amount_original_minor, currency, rate_at_operation_text,
               amount_base_minor, category, description, period, auto_pay
        FROM mandatory_expenses
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            str(row[1] or ""),
            int(row[2]),
            int(row[3]),
            str(row[4]).upper(),
            str(row[5]),
            int(row[6]),
            str(row[7]),
            str(row[8] or ""),
            str(row[9]),
            bool(row[10]),
        )
        for row in rows
    ]


def validate_migration(
    sqlite_storage: SQLiteStorage,
    wallets: list[Wallet],
    records: list[Record],
    tags: list[Tag],
    transfers: list,
    mandatory_expenses: list[MandatoryExpenseRecord],
    budgets: list[Budget],
    debts: list[Debt],
    debt_payments: list[DebtPayment],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    distribution_items: list[DistributionItem],
    distribution_subitems: list[DistributionSubitem],
    distribution_snapshots: list[FrozenDistributionRow],
    wallet_map: dict[int, int],
    record_map: dict[int, int],
    transfer_map: dict[int, int],
    mandatory_map: dict[int, int],
    debt_map: dict[int, int],
    debt_payment_map: dict[int, int],
    asset_map: dict[int, int],
    asset_snapshot_map: dict[int, int],
    goal_map: dict[int, int],
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    expected_counts = {
        "wallets": len(wallets),
        "transfers": len(transfers),
        "records": len(records),
        "mandatory_expenses": len(mandatory_expenses),
        "budgets": len(budgets),
        "debts": len(debts),
        "debt_payments": len(debt_payments),
        "assets": len(assets),
        "asset_snapshots": len(asset_snapshots),
        "goals": len(goals),
        "distribution_items": len(distribution_items),
        "distribution_subitems": len(distribution_subitems),
        "distribution_snapshots": len(distribution_snapshots),
        "tags": len(_materialize_tags(tags, records)),
        "record_tags": _expected_record_tag_count(records),
    }
    actual_counts = _counts_from_sqlite(sqlite_storage)

    for name, expected in expected_counts.items():
        actual = actual_counts[name]
        if expected != actual:
            errors.append(f"Count mismatch for {name}: json={expected}, sqlite={actual}")

    json_balances = _wallet_balances_minor_from_json(wallets, records)
    sqlite_balances = _wallet_balances_minor_from_sqlite(sqlite_storage)
    for old_wallet_id, json_balance in sorted(json_balances.items()):
        sqlite_wallet_id = wallet_map.get(old_wallet_id)
        if sqlite_wallet_id is None:
            errors.append(f"Wallet id mapping missing for source wallet #{old_wallet_id}")
            continue
        sqlite_balance = sqlite_balances.get(sqlite_wallet_id)
        if sqlite_balance is None:
            errors.append(
                f"Wallet #{old_wallet_id} -> #{sqlite_wallet_id} is absent in SQLite balance set"
            )
            continue
        if json_balance != sqlite_balance:
            errors.append(
                f"Wallet balance mismatch for wallet #{old_wallet_id} -> #{sqlite_wallet_id}: "
                f"json={minor_to_money(json_balance)}, sqlite={minor_to_money(sqlite_balance)}"
            )

    net_worth_json = sum(json_balances.values())
    net_worth_sqlite = sum(sqlite_balances.values())
    if net_worth_json != net_worth_sqlite:
        errors.append(
            f"Net worth mismatch: json={minor_to_money(net_worth_json)}, "
            f"sqlite={minor_to_money(net_worth_sqlite)}"
        )

    if len(record_map) != len(records):
        errors.append("Record id mapping is incomplete")
    if len(transfer_map) != len(transfers):
        errors.append("Transfer id mapping is incomplete")
    if len(mandatory_map) != len(mandatory_expenses):
        errors.append("Mandatory expense id mapping is incomplete")
    if len(debt_map) != len(debts):
        errors.append("Debt id mapping is incomplete")
    if len(debt_payment_map) != len(debt_payments):
        errors.append("Debt payment id mapping is incomplete")
    if len(asset_map) != len(assets):
        errors.append("Asset id mapping is incomplete")
    if len(asset_snapshot_map) != len(asset_snapshots):
        errors.append("Asset snapshot id mapping is incomplete")
    if len(goal_map) != len(goals):
        errors.append("Goal id mapping is incomplete")
    if _wallet_signatures_from_json(
        wallets, wallet_map=wallet_map
    ) != _wallet_signatures_from_sqlite(sqlite_storage):
        errors.append("Wallet payload mismatch")
    if _transfer_signatures_from_json(
        transfers,
        wallet_map=wallet_map,
        transfer_map=transfer_map,
    ) != _transfer_signatures_from_sqlite(sqlite_storage):
        errors.append("Transfer payload mismatch")
    if _record_signatures_from_json(
        records,
        wallet_map=wallet_map,
        transfer_map=transfer_map,
        debt_map=debt_map,
        record_map=record_map,
    ) != _record_signatures_from_sqlite(sqlite_storage):
        errors.append("Record payload mismatch")
    if _tag_signatures_from_json(tags, records) != _tag_signatures_from_sqlite(sqlite_storage):
        errors.append("Tag payload mismatch")
    if _record_tag_signatures_from_json(
        records,
        record_map=record_map,
    ) != _record_tag_signatures_from_sqlite(sqlite_storage):
        errors.append("Record tag payload mismatch")
    if _mandatory_signatures_from_json(
        mandatory_expenses,
        wallet_map=wallet_map,
        mandatory_map=mandatory_map,
    ) != _mandatory_signatures_from_sqlite(sqlite_storage):
        errors.append("Mandatory expense payload mismatch")
    if _asset_signatures_from_json(assets) != _asset_signatures_from_sqlite(sqlite_storage):
        errors.append("Asset payload mismatch")
    if _asset_snapshot_signatures_from_json(
        asset_snapshots,
        asset_map=asset_map,
    ) != _asset_snapshot_signatures_from_sqlite(sqlite_storage):
        errors.append("Asset snapshot payload mismatch")
    if _goal_signatures_from_json(goals) != _goal_signatures_from_sqlite(sqlite_storage):
        errors.append("Goal payload mismatch")
    if _budget_signatures_from_json(budgets) != _budget_signatures_from_sqlite(sqlite_storage):
        errors.append("Budget payload mismatch")
    if _debt_signatures_from_json(debts) != _debt_signatures_from_sqlite(sqlite_storage):
        errors.append("Debt payload mismatch")
    if _debt_payment_signatures_from_json(
        debt_payments,
        debt_map=debt_map,
        record_map=record_map,
    ) != _debt_payment_signatures_from_sqlite(sqlite_storage):
        errors.append("Debt payment payload mismatch")
    if _distribution_structure_signatures_from_json(
        distribution_items,
        distribution_subitems,
    ) != _distribution_structure_signatures_from_sqlite(sqlite_storage):
        errors.append("Distribution structure payload mismatch")
    if _distribution_snapshot_signatures_from_json(
        distribution_snapshots
    ) != _distribution_snapshot_signatures_from_sqlite(sqlite_storage):
        errors.append("Distribution snapshot payload mismatch")

    return (len(errors) == 0, errors)


def _validate_existing_target_equivalence(
    sqlite_storage: SQLiteStorage,
    wallets: list[Wallet],
    records: list[Record],
    tags: list[Tag],
    transfers: list,
    mandatory_expenses: list[MandatoryExpenseRecord],
    budgets: list[Budget],
    debts: list[Debt],
    debt_payments: list[DebtPayment],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    distribution_items: list[DistributionItem],
    distribution_subitems: list[DistributionSubitem],
    distribution_snapshots: list[FrozenDistributionRow],
) -> tuple[bool, list[str]]:
    identity_map = {int(wallet.id): int(wallet.id) for wallet in wallets}
    return validate_migration(
        sqlite_storage=sqlite_storage,
        wallets=wallets,
        records=records,
        tags=tags,
        transfers=transfers,
        mandatory_expenses=mandatory_expenses,
        budgets=budgets,
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems=distribution_subitems,
        distribution_snapshots=distribution_snapshots,
        wallet_map=identity_map,
        record_map={int(record.id): int(record.id) for record in records},
        transfer_map={int(transfer.id): int(transfer.id) for transfer in transfers},
        mandatory_map={int(expense.id): int(expense.id) for expense in mandatory_expenses},
        debt_map={int(debt.id): int(debt.id) for debt in debts},
        debt_payment_map={int(payment.id): int(payment.id) for payment in debt_payments},
        asset_map={int(asset.id): int(asset.id) for asset in assets},
        asset_snapshot_map={int(snapshot.id): int(snapshot.id) for snapshot in asset_snapshots},
        goal_map={int(goal.id): int(goal.id) for goal in goals},
    )


def _budget_signatures_from_json(budgets: list[Budget]) -> list[tuple]:
    return sorted(
        (
            int(budget.id),
            str(budget.category),
            str(budget.scope_type),
            str(budget.scope_value),
            str(budget.start_date),
            str(budget.end_date),
            float(budget.limit_base),
            int(budget.limit_base_minor),
            bool(budget.include_mandatory),
        )
        for budget in budgets
    )


def _budget_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, category, scope_type, scope_value,
               start_date, end_date, limit_base, limit_base_minor, include_mandatory
        FROM budgets
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            float(row[6]),
            int(row[7]),
            bool(row[8]),
        )
        for row in rows
    ]


def _asset_signatures_from_json(assets: list[Asset]) -> list[tuple]:
    return sorted(
        (
            int(asset.id),
            str(asset.name),
            str(asset.category.value),
            str(asset.currency).upper(),
            bool(asset.is_active),
            str(asset.created_at),
            str(asset.description or ""),
        )
        for asset in assets
    )


def _asset_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, name, category, currency, is_active, created_at, description
        FROM assets
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]).upper(),
            bool(row[4]),
            str(row[5]),
            str(row[6] or ""),
        )
        for row in rows
    ]


def _asset_snapshot_signatures_from_json(
    snapshots: list[AssetSnapshot],
    *,
    asset_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (
            int(snapshot.id),
            asset_map[int(snapshot.asset_id)],
            str(snapshot.snapshot_date),
            int(snapshot.value_minor),
            str(snapshot.currency).upper(),
            str(snapshot.note or ""),
        )
        for snapshot in snapshots
    )


def _asset_snapshot_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, asset_id, snapshot_date, value_minor, currency, note
        FROM asset_snapshots
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            int(row[1]),
            str(row[2]),
            int(row[3]),
            str(row[4]).upper(),
            str(row[5] or ""),
        )
        for row in rows
    ]


def _goal_signatures_from_json(goals: list[Goal]) -> list[tuple]:
    return sorted(
        (
            int(goal.id),
            str(goal.title),
            int(goal.target_amount_minor),
            str(goal.currency).upper(),
            str(goal.target_date) if goal.target_date else None,
            bool(goal.is_completed),
            str(goal.created_at),
            str(goal.description or ""),
        )
        for goal in goals
    )


def _goal_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id,
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
    )
    return [
        (
            int(row[0]),
            str(row[1]),
            int(row[2]),
            str(row[3]).upper(),
            str(row[4]) if row[4] is not None else None,
            bool(row[5]),
            str(row[6]),
            str(row[7] or ""),
        )
        for row in rows
    ]


def _debt_signatures_from_json(debts: list[Debt]) -> list[tuple]:
    return sorted(
        (
            int(debt.id),
            str(debt.contact_name),
            str(debt.kind.value),
            int(debt.total_amount_minor),
            int(debt.remaining_amount_minor),
            str(debt.currency).upper(),
            float(debt.interest_rate),
            str(debt.status.value),
            str(debt.created_at),
            str(debt.closed_at) if debt.closed_at else None,
        )
        for debt in debts
    )


def _debt_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, contact_name, kind, total_amount_minor, remaining_amount_minor,
               currency, interest_rate, status, created_at, closed_at
        FROM debts
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            str(row[1]),
            str(row[2]),
            int(row[3]),
            int(row[4]),
            str(row[5]).upper(),
            float(row[6]),
            str(row[7]),
            str(row[8]),
            str(row[9]) if row[9] is not None else None,
        )
        for row in rows
    ]


def _debt_payment_signatures_from_json(
    debt_payments: list[DebtPayment],
    *,
    debt_map: dict[int, int],
    record_map: dict[int, int],
) -> list[tuple]:
    return sorted(
        (
            int(payment.id),
            debt_map[int(payment.debt_id)],
            record_map[int(payment.record_id)] if payment.record_id is not None else None,
            str(payment.operation_type.value),
            int(payment.principal_paid_minor),
            bool(payment.is_write_off),
            str(payment.payment_date),
        )
        for payment in debt_payments
    )


def _debt_payment_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    rows = sqlite_storage.query_all(
        """
        SELECT id, debt_id, record_id, operation_type,
               principal_paid_minor, is_write_off, payment_date
        FROM debt_payments
        ORDER BY id
        """
    )
    return [
        (
            int(row[0]),
            int(row[1]),
            int(row[2]) if row[2] is not None else None,
            str(row[3]),
            int(row[4]),
            bool(row[5]),
            str(row[6]),
        )
        for row in rows
    ]


def _distribution_snapshot_signatures_from_json(
    snapshots: list[FrozenDistributionRow],
) -> list[tuple]:
    return sorted(
        (
            str(snapshot.month),
            bool(snapshot.is_negative),
            bool(snapshot.auto_fixed),
            tuple(str(column) for column in snapshot.column_order),
            tuple(sorted((str(k), str(v)) for k, v in snapshot.headings_by_column.items())),
            tuple(sorted((str(k), str(v)) for k, v in snapshot.values_by_column.items())),
        )
        for snapshot in snapshots
    )


def _distribution_snapshot_signatures_from_sqlite(sqlite_storage: SQLiteStorage) -> list[tuple]:
    snapshot_rows = sqlite_storage.query_all(
        """
        SELECT month, is_negative, auto_fixed
        FROM distribution_snapshots
        ORDER BY month ASC
        """
    )
    if not snapshot_rows:
        return []
    value_rows = sqlite_storage.query_all(
        """
        SELECT snapshot_month, column_key, column_label, column_order, value_text
        FROM distribution_snapshot_values
        ORDER BY snapshot_month ASC, column_order ASC
        """
    )
    column_order_by_month: dict[str, list[str]] = {}
    headings_by_month: dict[str, dict[str, str]] = {}
    values_by_month: dict[str, dict[str, str]] = {}
    for snapshot_month, column_key, column_label, _column_order, value_text in value_rows:
        month = str(snapshot_month)
        column_key_text = str(column_key)
        column_order_by_month.setdefault(month, []).append(column_key_text)
        headings_by_month.setdefault(month, {})[column_key_text] = str(column_label)
        values_by_month.setdefault(month, {})[column_key_text] = str(value_text)
    signatures: list[tuple] = []
    for month, is_negative, auto_fixed in snapshot_rows:
        month_text = str(month)
        signatures.append(
            (
                month_text,
                bool(is_negative),
                bool(auto_fixed),
                tuple(column_order_by_month.get(month_text, [])),
                tuple(sorted(headings_by_month.get(month_text, {}).items())),
                tuple(sorted(values_by_month.get(month_text, {}).items())),
            )
        )
    return signatures


def _distribution_structure_signatures_from_json(
    items: list[DistributionItem],
    subitems: list[DistributionSubitem],
) -> tuple[list[tuple], list[tuple]]:
    item_signatures = sorted(
        (
            int(item.id),
            str(item.name),
            str(item.group_name or ""),
            int(item.sort_order),
            float(item.pct),
            int(item.pct_minor),
            bool(item.is_active),
        )
        for item in items
    )
    subitem_signatures = sorted(
        (
            int(subitem.id),
            int(subitem.item_id),
            str(subitem.name),
            int(subitem.sort_order),
            float(subitem.pct),
            int(subitem.pct_minor),
            bool(subitem.is_active),
        )
        for subitem in subitems
    )
    return item_signatures, subitem_signatures


def _distribution_structure_signatures_from_sqlite(
    sqlite_storage: SQLiteStorage,
) -> tuple[list[tuple], list[tuple]]:
    item_rows = sqlite_storage.query_all(
        """
        SELECT id, name, group_name, sort_order, pct, pct_minor, is_active
        FROM distribution_items
        ORDER BY id
        """
    )
    subitem_rows = sqlite_storage.query_all(
        """
        SELECT id, item_id, name, sort_order, pct, pct_minor, is_active
        FROM distribution_subitems
        ORDER BY id
        """
    )
    return (
        [
            (
                int(row[0]),
                str(row[1]),
                str(row[2] or ""),
                int(row[3]),
                float(row[4]),
                int(row[5]),
                bool(row[6]),
            )
            for row in item_rows
        ],
        [
            (
                int(row[0]),
                int(row[1]),
                str(row[2]),
                int(row[3]),
                float(row[4]),
                int(row[5]),
                bool(row[6]),
            )
            for row in subitem_rows
        ],
    )


def _insert_distribution_structure(
    sqlite_storage: SQLiteStorage,
    items: list[DistributionItem],
    subitems: list[DistributionSubitem],
) -> None:
    for item in sorted(items, key=lambda value: int(value.id)):
        sqlite_storage.execute(
            """
            INSERT INTO distribution_items (
                id, name, group_name, sort_order, pct, pct_minor, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(item.id),
                str(item.name),
                str(item.group_name or ""),
                int(item.sort_order),
                float(item.pct),
                int(item.pct_minor),
                int(bool(item.is_active)),
            ),
        )
    for subitem in sorted(subitems, key=lambda value: int(value.id)):
        sqlite_storage.execute(
            """
            INSERT INTO distribution_subitems (
                id, item_id, name, sort_order, pct, pct_minor, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(subitem.id),
                int(subitem.item_id),
                str(subitem.name),
                int(subitem.sort_order),
                float(subitem.pct),
                int(subitem.pct_minor),
                int(bool(subitem.is_active)),
            ),
        )
    if items:
        _set_sqlite_sequence(sqlite_storage, "distribution_items")
    if subitems:
        _set_sqlite_sequence(sqlite_storage, "distribution_subitems")


def _insert_distribution_snapshots(
    sqlite_storage: SQLiteStorage,
    snapshots: list[FrozenDistributionRow],
) -> None:
    for snapshot in sorted(snapshots, key=lambda item: item.month):
        sqlite_storage.execute(
            """
            INSERT INTO distribution_snapshots (month, is_negative, auto_fixed)
            VALUES (?, ?, ?)
            """,
            (
                str(snapshot.month),
                int(bool(snapshot.is_negative)),
                int(bool(snapshot.auto_fixed)),
            ),
        )
        for column_order, column_key in enumerate(snapshot.column_order):
            sqlite_storage.execute(
                """
                INSERT INTO distribution_snapshot_values (
                    snapshot_month, column_key, column_label, column_order, value_text
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(snapshot.month),
                    str(column_key),
                    str(snapshot.headings_by_column.get(column_key, column_key)),
                    int(column_order),
                    str(snapshot.values_by_column.get(column_key, "-")),
                ),
            )


def _load_distribution_snapshots_from_json(path: str) -> list[FrozenDistributionRow]:
    with open(path, encoding="utf-8") as fp:
        payload = json.load(fp)
    payload = unwrap_backup_payload(payload, force=True)
    raw_snapshots = payload.get("distribution_snapshots", [])
    if not isinstance(raw_snapshots, list):
        return []
    snapshots: list[FrozenDistributionRow] = []
    for item in raw_snapshots:
        if not isinstance(item, dict):
            continue
        month = str(item.get("month", "") or "").strip()
        if not month:
            continue
        column_order_raw = item.get("column_order", [])
        headings_raw = item.get("headings_by_column", {})
        values_raw = item.get("values_by_column", {})
        if not isinstance(column_order_raw, list):
            column_order_raw = []
        if not isinstance(headings_raw, dict):
            headings_raw = {}
        if not isinstance(values_raw, dict):
            values_raw = {}
        snapshots.append(
            FrozenDistributionRow(
                month=month,
                column_order=tuple(str(column) for column in column_order_raw),
                headings_by_column={str(k): str(v) for k, v in headings_raw.items()},
                values_by_column={str(k): str(v) for k, v in values_raw.items()},
                is_negative=bool(item.get("is_negative", False)),
                auto_fixed=bool(item.get("auto_fixed", False)),
            )
        )
    return snapshots


def _load_budgets_from_json(path: str) -> list[Budget]:
    with open(path, encoding="utf-8") as fp:
        payload = json.load(fp)
    payload = unwrap_backup_payload(payload, force=True)
    raw_budgets = payload.get("budgets", [])
    if not isinstance(raw_budgets, list):
        raw_budgets = []
    budgets: list[Budget] = []
    seen_ids: set[int] = set()
    for item in raw_budgets:
        if not isinstance(item, dict):
            raise ValueError("Invalid budget payload: expected object")
        budget_id = int(item.get("id", 0) or 0)
        if budget_id <= 0:
            raise ValueError(f"Invalid budget id: {item.get('id')!r}")
        if budget_id in seen_ids:
            raise ValueError(f"Duplicate budget id: {budget_id}")
        category = str(item.get("category", "") or "").strip()
        scope_type = str(item.get("scope_type", "category") or "category").strip().lower()
        scope_value = str(item.get("scope_value", category) or category).strip()
        start_date = str(item.get("start_date", "") or "").strip()
        end_date = str(item.get("end_date", "") or "").strip()
        if not category:
            raise ValueError(f"Budget #{budget_id} has empty category")
        if scope_type not in {"category", "tag"}:
            raise ValueError(f"Budget #{budget_id} has invalid scope_type")
        if not scope_value:
            raise ValueError(f"Budget #{budget_id} has empty scope_value")
        if not start_date or not end_date:
            raise ValueError(f"Budget #{budget_id} is missing start_date/end_date")
        limit_base = to_money_float(item.get("limit_base", item.get("limit_kzt", 0.0)) or 0.0)
        limit_base_minor = int(
            item.get("limit_base_minor", item.get("limit_kzt_minor", 0)) or 0
        )
        budgets.append(
            Budget(
                id=budget_id,
                category=category,
                start_date=start_date,
                end_date=end_date,
                limit_base=limit_base,
                limit_base_minor=limit_base_minor,
                include_mandatory=bool(item.get("include_mandatory", False)),
                scope_type=scope_type,
                scope_value=scope_value,
            )
        )
        seen_ids.add(budget_id)
    return budgets


def _load_distribution_structure_from_json(
    path: str,
) -> tuple[list[DistributionItem], list[DistributionSubitem]]:
    with open(path, encoding="utf-8") as fp:
        payload = json.load(fp)
    payload = unwrap_backup_payload(payload, force=True)
    raw_items = payload.get("distribution_items", [])
    raw_subitems = payload.get("distribution_subitems", [])
    if not isinstance(raw_items, list):
        raw_items = []
    if not isinstance(raw_subitems, list):
        raw_subitems = []
    items: list[DistributionItem] = []
    seen_item_ids: set[int] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("Invalid distribution item payload: expected object")
        item_id = int(item.get("id", 0) or 0)
        if item_id <= 0:
            raise ValueError(f"Invalid distribution item id: {item.get('id')!r}")
        if item_id in seen_item_ids:
            raise ValueError(f"Duplicate distribution item id: {item_id}")
        name = str(item.get("name", "") or "").strip()
        if not name:
            raise ValueError(f"Distribution item #{item_id} has empty name")
        seen_item_ids.add(item_id)
        items.append(
            DistributionItem(
                id=item_id,
                name=name,
                group_name=str(item.get("group_name", "") or ""),
                sort_order=int(item.get("sort_order", 0) or 0),
                pct=float(item.get("pct", 0.0) or 0.0),
                pct_minor=int(item.get("pct_minor", 0) or 0),
                is_active=bool(item.get("is_active", True)),
            )
        )
    item_ids = {int(item.id) for item in items}
    subitems: list[DistributionSubitem] = []
    seen_subitem_ids: set[int] = set()
    for subitem in raw_subitems:
        if not isinstance(subitem, dict):
            raise ValueError("Invalid distribution subitem payload: expected object")
        subitem_id = int(subitem.get("id", 0) or 0)
        item_id = int(subitem.get("item_id", 0) or 0)
        if subitem_id <= 0:
            raise ValueError(f"Invalid distribution subitem id: {subitem.get('id')!r}")
        if subitem_id in seen_subitem_ids:
            raise ValueError(f"Duplicate distribution subitem id: {subitem_id}")
        if item_id <= 0 or item_id not in item_ids:
            raise ValueError(
                f"Distribution subitem #{subitem_id} references missing item_id={item_id}"
            )
        name = str(subitem.get("name", "") or "").strip()
        if not name:
            raise ValueError(f"Distribution subitem #{subitem_id} has empty name")
        seen_subitem_ids.add(subitem_id)
        subitems.append(
            DistributionSubitem(
                id=subitem_id,
                item_id=item_id,
                name=name,
                sort_order=int(subitem.get("sort_order", 0) or 0),
                pct=float(subitem.get("pct", 0.0) or 0.0),
                pct_minor=int(subitem.get("pct_minor", 0) or 0),
                is_active=bool(subitem.get("is_active", True)),
            )
        )
    return items, subitems


def _load_assets_and_goals_from_json(
    path: str,
) -> tuple[list[Asset], list[AssetSnapshot], list[Goal]]:
    with open(path, encoding="utf-8") as fp:
        payload = json.load(fp)
    payload = unwrap_backup_payload(payload, force=True)

    raw_assets = payload.get("assets", [])
    raw_asset_snapshots = payload.get("asset_snapshots", [])
    raw_goals = payload.get("goals", [])
    if not isinstance(raw_assets, list):
        raw_assets = []
    if not isinstance(raw_asset_snapshots, list):
        raw_asset_snapshots = []
    if not isinstance(raw_goals, list):
        raw_goals = []

    assets: list[Asset] = []
    seen_asset_ids: set[int] = set()
    for item in raw_assets:
        if not isinstance(item, dict):
            raise ValueError("Invalid asset payload: expected object")
        asset_id = int(item.get("id", 0) or 0)
        if asset_id <= 0:
            raise ValueError(f"Invalid asset id: {item.get('id')!r}")
        if asset_id in seen_asset_ids:
            raise ValueError(f"Duplicate asset id: {asset_id}")
        assets.append(
            Asset(
                id=asset_id,
                name=str(item.get("name", "") or "").strip(),
                category=AssetCategory(str(item.get("category", "other") or "other")),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                is_active=bool(item.get("is_active", True)),
                created_at=str(item.get("created_at", "") or ""),
                description=str(item.get("description", "") or ""),
            )
        )
        seen_asset_ids.add(asset_id)

    asset_ids = {int(asset.id) for asset in assets}
    asset_snapshots: list[AssetSnapshot] = []
    seen_snapshot_ids: set[int] = set()
    for item in raw_asset_snapshots:
        if not isinstance(item, dict):
            raise ValueError("Invalid asset snapshot payload: expected object")
        snapshot_id = int(item.get("id", 0) or 0)
        if snapshot_id <= 0:
            raise ValueError(f"Invalid asset snapshot id: {item.get('id')!r}")
        if snapshot_id in seen_snapshot_ids:
            raise ValueError(f"Duplicate asset snapshot id: {snapshot_id}")
        snapshot = AssetSnapshot(
            id=snapshot_id,
            asset_id=int(item.get("asset_id", 0) or 0),
            snapshot_date=str(item.get("snapshot_date", "") or ""),
            value_minor=int(item.get("value_minor", 0) or 0),
            currency=str(item.get("currency", "KZT") or "KZT").upper(),
            note=str(item.get("note", "") or ""),
        )
        if int(snapshot.asset_id) not in asset_ids:
            raise ValueError(
                f"Asset snapshot #{snapshot.id} references missing asset_id={snapshot.asset_id}"
            )
        asset_snapshots.append(snapshot)
        seen_snapshot_ids.add(snapshot_id)

    goals: list[Goal] = []
    seen_goal_ids: set[int] = set()
    for item in raw_goals:
        if not isinstance(item, dict):
            raise ValueError("Invalid goal payload: expected object")
        goal_id = int(item.get("id", 0) or 0)
        if goal_id <= 0:
            raise ValueError(f"Invalid goal id: {item.get('id')!r}")
        if goal_id in seen_goal_ids:
            raise ValueError(f"Duplicate goal id: {goal_id}")
        goals.append(
            Goal(
                id=goal_id,
                title=str(item.get("title", "") or "").strip(),
                target_amount_minor=int(item.get("target_amount_minor", 0) or 0),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                created_at=str(item.get("created_at", "") or ""),
                is_completed=bool(item.get("is_completed", False)),
                target_date=str(item.get("target_date"))
                if item.get("target_date") not in (None, "")
                else None,
                description=str(item.get("description", "") or ""),
            )
        )
        seen_goal_ids.add(goal_id)
    return assets, asset_snapshots, goals


def _load_source_dataset(
    json_path: str,
) -> tuple[
    list[Wallet],
    list[Record],
    list[Tag],
    list,
    list[MandatoryExpenseRecord],
    list[Budget],
    list[Debt],
    list[DebtPayment],
    list[Asset],
    list[AssetSnapshot],
    list[Goal],
    list[DistributionItem],
    list[DistributionSubitem],
    list[FrozenDistributionRow],
]:
    with open(json_path, encoding="utf-8") as fp:
        raw_payload = json.load(fp)
    payload = unwrap_backup_payload(raw_payload, force=True)
    raw_tags = payload.get("tags", [])
    raw_record_tags = payload.get("record_tags", [])
    parsed_tags: list[Tag] = []
    if isinstance(raw_tags, list) and isinstance(raw_record_tags, list):
        tags_by_id: dict[int, str] = {}
        for item in raw_tags:
            if not isinstance(item, dict):
                continue
            tag_id = int(item.get("id", 0) or 0)
            tag_name = normalize_tag_name(item.get("name"))
            if tag_id > 0 and tag_name:
                tags_by_id[tag_id] = tag_name
                parsed_tags.append(
                    Tag(
                        id=tag_id,
                        name=tag_name,
                        color=str(item.get("color", "") or ""),
                        usage_count=max(0, int(item.get("usage_count", 0) or 0)),
                        last_used_at=str(item.get("last_used_at", "") or ""),
                    )
                )
        record_tag_names: dict[int, list[str]] = {}
        for item in raw_record_tags:
            if not isinstance(item, dict):
                continue
            record_id = int(item.get("record_id", 0) or 0)
            tag_id = int(item.get("tag_id", 0) or 0)
            inline_name = normalize_tag_name(item.get("name"))
            tag_name = inline_name or tags_by_id.get(tag_id, "")
            if record_id > 0 and tag_name:
                record_tag_names.setdefault(record_id, []).append(tag_name)
        if isinstance(payload.get("records"), list):
            for item in payload["records"]:
                if not isinstance(item, dict):
                    continue
                record_id = int(item.get("id", 0) or 0)
                merged = tuple(item.get("tags", []) or ()) + tuple(
                    record_tag_names.get(record_id, [])
                )
                item["tags"] = list(normalize_tag_names(merged))

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
        delete=False,
    ) as temp_file:
        json.dump(payload, temp_file, ensure_ascii=False, indent=2)
        temp_path = temp_file.name
    try:
        json_storage = JsonStorage(file_path=temp_path)
        wallets = json_storage.get_wallets()
        transfers = json_storage.get_transfers()
        records = json_storage.get_records()
        mandatory_expenses = json_storage.get_mandatory_expenses()
        debts = json_storage._repo.load_debts()
        debt_payments = json_storage._repo.load_debt_payments()
    finally:
        os.unlink(temp_path)

    budgets = _load_budgets_from_json(json_path)
    assets, asset_snapshots, goals = _load_assets_and_goals_from_json(json_path)
    distribution_items, distribution_subitems = _load_distribution_structure_from_json(json_path)
    distribution_snapshots = _load_distribution_snapshots_from_json(json_path)
    return (
        wallets,
        records,
        parsed_tags,
        transfers,
        mandatory_expenses,
        budgets,
        debts,
        debt_payments,
        assets,
        asset_snapshots,
        goals,
        distribution_items,
        distribution_subitems,
        distribution_snapshots,
    )


def run_dry_run(args: argparse.Namespace) -> int:
    print("== DRY RUN: JSON -> SQLite migration check ==")
    sqlite_storage = SQLiteStorage(db_path=args.sqlite_path)
    try:
        schema_path = _resolve_schema_path(args.schema_path)
        if not Path(schema_path).exists():
            raise FileNotFoundError(f"schema.sql not found: {schema_path}")
        sqlite_storage.connection_is_available()
        print(f"[ok] SQLite connection is available: {args.sqlite_path}")
        print(f"[ok] Schema path resolved: {schema_path}")

        (
            wallets,
            records,
            tags,
            transfers,
            mandatory_expenses,
            budgets,
            debts,
            debt_payments,
            assets,
            asset_snapshots,
            goals,
            distribution_items,
            distribution_subitems,
            distribution_snapshots,
        ) = _load_source_dataset(args.json_path)

        _validate_source_integrity(
            wallets,
            records,
            transfers,
            mandatory_expenses,
            budgets,
            debts,
            debt_payments,
            assets,
            asset_snapshots,
            goals,
            distribution_items,
            distribution_subitems,
            distribution_snapshots,
        )

        print(f"[ok] JSON source loaded: {args.json_path}")
        print(f"  wallets: {len(wallets)}")
        print(f"  transfers: {len(transfers)}")
        print(f"  records: {len(records)}")
        print(f"  tags: {len(_materialize_tags(tags, records))}")
        print(f"  mandatory_expenses: {len(mandatory_expenses)}")
        print(f"  budgets: {len(budgets)}")
        print(f"  debts: {len(debts)}")
        print(f"  debt_payments: {len(debt_payments)}")
        print(f"  assets: {len(assets)}")
        print(f"  asset_snapshots: {len(asset_snapshots)}")
        print(f"  goals: {len(goals)}")
        print(f"  distribution_items: {len(distribution_items)}")
        print(f"  distribution_subitems: {len(distribution_subitems)}")
        print(f"  distribution_snapshots: {len(distribution_snapshots)}")
        print("[ok] Integrity checks passed")
        print("[dry-run] No INSERT and no explicit COMMIT executed")
        return 0
    except Exception as exc:
        print(f"[error] Dry-run failed: {exc}")
        return 1
    finally:
        sqlite_storage.close()


def run_migration(args: argparse.Namespace) -> int:
    print("== MIGRATION: JSON -> SQLite ==")
    sqlite_storage = SQLiteStorage(db_path=args.sqlite_path)

    try:
        schema_path = _resolve_schema_path(args.schema_path)
        if not Path(schema_path).exists():
            raise FileNotFoundError(f"schema.sql not found: {schema_path}")

        (
            wallets,
            records,
            tags,
            transfers,
            mandatory_expenses,
            budgets,
            debts,
            debt_payments,
            assets,
            asset_snapshots,
            goals,
            distribution_items,
            distribution_subitems,
            distribution_snapshots,
        ) = _load_source_dataset(args.json_path)

        _validate_source_integrity(
            wallets,
            records,
            transfers,
            mandatory_expenses,
            budgets,
            debts,
            debt_payments,
            assets,
            asset_snapshots,
            goals,
            distribution_items,
            distribution_subitems,
            distribution_snapshots,
        )
        print("[ok] Source data integrity passed")

        sqlite_storage.initialize_schema(schema_path)
        if _has_any_data(sqlite_storage):
            valid_existing, existing_errors = _validate_existing_target_equivalence(
                sqlite_storage,
                wallets=wallets,
                records=records,
                tags=tags,
                transfers=transfers,
                mandatory_expenses=mandatory_expenses,
                budgets=budgets,
                debts=debts,
                debt_payments=debt_payments,
                assets=assets,
                asset_snapshots=asset_snapshots,
                goals=goals,
                distribution_items=distribution_items,
                distribution_subitems=distribution_subitems,
                distribution_snapshots=distribution_snapshots,
            )
            if valid_existing:
                print("[ok] Target SQLite already contains equivalent data, migration skipped")
                return 0
            details = "; ".join(existing_errors[:3]) if existing_errors else "dataset mismatch"
            raise RuntimeError(
                f"Target SQLite is not empty and differs from source JSON: {details}"
            )

        sqlite_storage.begin()
        print("[tx] Transaction started")

        print("[1/7] Migrating wallets...")
        wallet_map = _insert_wallets(sqlite_storage, wallets)
        print("[2/7] Migrating transfers...")
        transfer_map = _insert_transfers(sqlite_storage, transfers, wallet_map)
        print("[3/9] Migrating debts...")
        debt_map = _insert_debts(sqlite_storage, debts)
        print("[4/9] Migrating records...")
        record_map = _insert_records(sqlite_storage, records, wallet_map, transfer_map)
        print("[5/13] Migrating tags...")
        _insert_tags(sqlite_storage, tags, records, record_map)
        print("[6/13] Migrating mandatory_expenses...")
        mandatory_map = _insert_mandatory_expenses(sqlite_storage, mandatory_expenses, wallet_map)
        print("[7/13] Migrating budgets...")
        _insert_budgets(sqlite_storage, budgets)
        print("[8/13] Migrating debt_payments...")
        debt_payment_map = _insert_debt_payments(
            sqlite_storage,
            debt_payments,
            debt_map,
            record_map,
        )
        print("[9/13] Migrating assets...")
        asset_map = _insert_assets(sqlite_storage, assets)
        print("[10/13] Migrating asset_snapshots...")
        asset_snapshot_map = _insert_asset_snapshots(sqlite_storage, asset_snapshots, asset_map)
        print("[11/13] Migrating goals...")
        goal_map = _insert_goals(sqlite_storage, goals)
        print("[12/13] Migrating distribution structure...")
        _insert_distribution_structure(sqlite_storage, distribution_items, distribution_subitems)
        print("[13/13] Migrating distribution_snapshots...")
        _insert_distribution_snapshots(sqlite_storage, distribution_snapshots)

        valid, errors = validate_migration(
            sqlite_storage=sqlite_storage,
            wallets=wallets,
            records=records,
            tags=tags,
            transfers=transfers,
            mandatory_expenses=mandatory_expenses,
            budgets=budgets,
            debts=debts,
            debt_payments=debt_payments,
            assets=assets,
            asset_snapshots=asset_snapshots,
            goals=goals,
            distribution_items=distribution_items,
            distribution_subitems=distribution_subitems,
            distribution_snapshots=distribution_snapshots,
            wallet_map=wallet_map,
            record_map=record_map,
            transfer_map=transfer_map,
            mandatory_map=mandatory_map,
            debt_map=debt_map,
            debt_payment_map=debt_payment_map,
            asset_map=asset_map,
            asset_snapshot_map=asset_snapshot_map,
            goal_map=goal_map,
        )
        if not valid:
            print("[error] Validation failed, rollback started")
            for line in errors:
                print(f"  - {line}")
            sqlite_storage.rollback()
            print("[tx] Rollback complete")
            return 1

        sqlite_storage.commit()
        print("[tx] Commit complete")
        print("[ok] Migration finished successfully")
        return 0
    except Exception as exc:
        try:
            sqlite_storage.rollback()
            print("[tx] Rollback complete")
        except Exception:
            print("[warn] Rollback failed")
        print(f"[error] Migration failed: {exc}")
        return 1
    finally:
        sqlite_storage.close()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        return run_dry_run(args)
    return run_migration(args)


if __name__ == "__main__":
    sys.exit(main())
