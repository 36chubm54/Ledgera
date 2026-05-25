from __future__ import annotations

from collections.abc import Sequence
from datetime import date as dt_date
from typing import Any

from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import to_money_float, to_rate_float
from utils.import_core import record_type_name
from utils.records.tags import color_for_tag, normalize_tag_name, normalize_tag_names


def record_to_payload(record: Record, *, system_wallet_id: int) -> dict[str, Any]:
    item = {
        "id": int(record.id),
        "date": record.date.isoformat() if isinstance(record.date, dt_date) else record.date,
        "type": record_type_name(record),
        "wallet_id": int(getattr(record, "wallet_id", system_wallet_id)),
        "transfer_id": getattr(record, "transfer_id", None),
        "related_debt_id": getattr(record, "related_debt_id", None),
        "category": record.category,
        "amount_original": record.amount_original,
        "currency": record.currency,
        "rate_at_operation": record.rate_at_operation,
        "amount_base": record.amount_base,
        "description": str(getattr(record, "description", "") or ""),
        "tags": list(normalize_tag_names(tuple(getattr(record, "tags", ()) or ()))),
        "period": "",
    }
    if isinstance(record, MandatoryExpenseRecord):
        item["period"] = record.period
    return item


def wallet_to_payload(wallet: Wallet) -> dict[str, Any]:
    return {
        "id": int(wallet.id),
        "name": str(wallet.name),
        "currency": str(wallet.currency or "KZT").upper(),
        "initial_balance": to_money_float(wallet.initial_balance),
        "system": bool(wallet.system),
        "allow_negative": bool(wallet.allow_negative),
        "is_active": bool(wallet.is_active),
    }


def transfer_to_payload(transfer: Transfer) -> dict[str, Any]:
    return {
        "id": int(transfer.id),
        "from_wallet_id": int(transfer.from_wallet_id),
        "to_wallet_id": int(transfer.to_wallet_id),
        "date": transfer.date.isoformat() if isinstance(transfer.date, dt_date) else transfer.date,
        "amount_original": to_money_float(transfer.amount_original),
        "currency": str(transfer.currency).upper(),
        "rate_at_operation": to_rate_float(transfer.rate_at_operation),
        "amount_base": to_money_float(transfer.amount_base),
        "description": str(transfer.description or ""),
    }


def budget_to_payload(budget: Budget) -> dict[str, Any]:
    return {
        "id": int(budget.id),
        "category": str(budget.category),
        "scope_type": str(budget.scope_type),
        "scope_value": str(budget.scope_value),
        "start_date": str(budget.start_date),
        "end_date": str(budget.end_date),
        "limit_base": to_money_float(budget.limit_base),
        "limit_base_minor": int(budget.limit_base_minor),
        "include_mandatory": bool(budget.include_mandatory),
    }


def distribution_snapshot_to_payload(snapshot: FrozenDistributionRow) -> dict[str, Any]:
    return {
        "month": str(snapshot.month),
        "is_negative": bool(snapshot.is_negative),
        "auto_fixed": bool(snapshot.auto_fixed),
        "column_order": list(snapshot.column_order),
        "headings_by_column": dict(snapshot.headings_by_column),
        "values_by_column": dict(snapshot.values_by_column),
    }


def distribution_item_to_payload(item: DistributionItem) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "name": str(item.name),
        "group_name": str(item.group_name or ""),
        "sort_order": int(item.sort_order),
        "pct": float(item.pct),
        "pct_minor": int(item.pct_minor),
        "is_active": bool(item.is_active),
    }


def distribution_subitem_to_payload(subitem: DistributionSubitem) -> dict[str, Any]:
    return {
        "id": int(subitem.id),
        "item_id": int(subitem.item_id),
        "name": str(subitem.name),
        "sort_order": int(subitem.sort_order),
        "pct": float(subitem.pct),
        "pct_minor": int(subitem.pct_minor),
        "is_active": bool(subitem.is_active),
    }


def debt_to_payload(debt: Debt) -> dict[str, Any]:
    return {
        "id": int(debt.id),
        "contact_name": str(debt.contact_name),
        "kind": debt.kind.value,
        "total_amount_minor": int(debt.total_amount_minor),
        "remaining_amount_minor": int(debt.remaining_amount_minor),
        "currency": str(debt.currency).upper(),
        "interest_rate": float(debt.interest_rate),
        "status": debt.status.value,
        "created_at": str(debt.created_at),
        "closed_at": str(debt.closed_at) if debt.closed_at else None,
    }


def debt_payment_to_payload(payment: DebtPayment) -> dict[str, Any]:
    return {
        "id": int(payment.id),
        "debt_id": int(payment.debt_id),
        "record_id": int(payment.record_id) if payment.record_id is not None else None,
        "operation_type": payment.operation_type.value,
        "principal_paid_minor": int(payment.principal_paid_minor),
        "is_write_off": bool(payment.is_write_off),
        "payment_date": str(payment.payment_date),
    }


def asset_to_payload(asset: Asset) -> dict[str, Any]:
    return {
        "id": int(asset.id),
        "name": str(asset.name),
        "category": str(asset.category.value),
        "currency": str(asset.currency).upper(),
        "is_active": bool(asset.is_active),
        "created_at": str(asset.created_at),
        "description": str(asset.description or ""),
    }


def asset_snapshot_to_payload(snapshot: AssetSnapshot) -> dict[str, Any]:
    return {
        "id": int(snapshot.id),
        "asset_id": int(snapshot.asset_id),
        "snapshot_date": str(snapshot.snapshot_date),
        "value_minor": int(snapshot.value_minor),
        "currency": str(snapshot.currency).upper(),
        "note": str(snapshot.note or ""),
    }


def goal_to_payload(goal: Goal) -> dict[str, Any]:
    return {
        "id": int(goal.id),
        "title": str(goal.title),
        "target_amount_minor": int(goal.target_amount_minor),
        "currency": str(goal.currency).upper(),
        "target_date": str(goal.target_date) if goal.target_date else None,
        "is_completed": bool(goal.is_completed),
        "created_at": str(goal.created_at),
        "description": str(goal.description or ""),
    }


def tag_to_payload(tag: Tag) -> dict[str, Any]:
    return {
        "id": int(tag.id),
        "name": str(tag.name),
        "color": str(tag.color or ""),
        "usage_count": int(tag.usage_count or 0),
        "last_used_at": str(tag.last_used_at or ""),
    }


def record_tag_to_payload(record_id: int, tag_id: int) -> dict[str, Any]:
    return {
        "record_id": int(record_id),
        "tag_id": int(tag_id),
    }


def build_backup_data_payload(
    *,
    wallets: Sequence[Wallet] | None,
    records: Sequence[Record],
    tags: Sequence[Tag],
    mandatory_expenses: Sequence[MandatoryExpenseRecord],
    budgets: Sequence[Budget],
    debts: Sequence[Debt],
    debt_payments: Sequence[DebtPayment],
    assets: Sequence[Asset],
    asset_snapshots: Sequence[AssetSnapshot],
    goals: Sequence[Goal],
    distribution_items: Sequence[DistributionItem],
    distribution_subitems: Sequence[DistributionSubitem],
    distribution_snapshots: Sequence[FrozenDistributionRow],
    transfers: Sequence[Transfer],
    initial_balance: float,
    system_wallet_id: int,
) -> dict[str, Any]:
    normalized_wallets = list(wallets or [])
    if not normalized_wallets:
        normalized_wallets = [
            Wallet(
                id=system_wallet_id,
                name="Main wallet",
                currency="KZT",
                initial_balance=float(initial_balance),
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ]

    tags_by_name: dict[str, Tag] = {}
    record_tag_rows: list[dict[str, Any]] = []
    next_tag_id = 1

    for tag in tags:
        normalized_name = normalize_tag_name(tag.name)
        if not normalized_name:
            continue
        persisted = Tag(
            id=int(tag.id),
            name=normalized_name,
            color=str(tag.color or ""),
            usage_count=int(getattr(tag, "usage_count", 0) or 0),
            last_used_at=str(getattr(tag, "last_used_at", "") or ""),
        )
        tags_by_name[normalized_name.casefold()] = persisted
        next_tag_id = max(next_tag_id, persisted.id + 1)

    for record in records:
        record_id = int(record.id)
        for tag_name in normalize_tag_names(tuple(getattr(record, "tags", ()) or ())):
            existing = tags_by_name.get(tag_name.casefold())
            if existing is None:
                existing = Tag(id=next_tag_id, name=tag_name, color=color_for_tag(tag_name))
                tags_by_name[tag_name.casefold()] = existing
                next_tag_id += 1
            record_tag_rows.append(record_tag_to_payload(record_id, existing.id))

    return {
        "wallets": [wallet_to_payload(wallet) for wallet in normalized_wallets],
        "records": [
            record_to_payload(record, system_wallet_id=system_wallet_id) for record in records
        ],
        "mandatory_expenses": [
            record_to_payload(expense, system_wallet_id=system_wallet_id)
            for expense in mandatory_expenses
        ],
        "tags": [
            tag_to_payload(tag) for tag in sorted(tags_by_name.values(), key=lambda item: item.id)
        ],
        "record_tags": record_tag_rows,
        "budgets": [budget_to_payload(budget) for budget in budgets],
        "debts": [debt_to_payload(debt) for debt in debts],
        "debt_payments": [debt_payment_to_payload(payment) for payment in debt_payments],
        "assets": [asset_to_payload(asset) for asset in assets],
        "asset_snapshots": [asset_snapshot_to_payload(snapshot) for snapshot in asset_snapshots],
        "goals": [goal_to_payload(goal) for goal in goals],
        "distribution_items": [distribution_item_to_payload(item) for item in distribution_items],
        "distribution_subitems": [
            distribution_subitem_to_payload(subitem) for subitem in distribution_subitems
        ],
        "distribution_snapshots": [
            distribution_snapshot_to_payload(snapshot) for snapshot in distribution_snapshots
        ],
        "transfers": [transfer_to_payload(transfer) for transfer in transfers],
    }


def wrap_backup_payload(
    *,
    data_payload: dict[str, Any],
    readonly: bool,
    storage_mode: str,
    app_version: str,
    compute_checksum: Any,
    now_utc_iso8601: Any,
) -> dict[str, Any]:
    if not readonly:
        return data_payload
    return {
        "meta": {
            "created_at": now_utc_iso8601(),
            "app_version": app_version,
            "storage": str(storage_mode or "unknown"),
            "readonly": True,
            "checksum": compute_checksum(data_payload),
        },
        "data": data_payload,
    }
