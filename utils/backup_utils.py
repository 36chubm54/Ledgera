import hashlib
import json
import logging
import os
import tempfile
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as dt_date
from typing import Any

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.import_core import ImportSummary, parse_import_row, record_type_name
from utils.money import to_money_float, to_rate_float
from utils.tag_utils import color_for_tag, normalize_tag_name, normalize_tag_names
from version import __version__

logger = logging.getLogger(__name__)
SYSTEM_WALLET_ID = 1


@dataclass(frozen=True)
class ImportedBackupData:
    wallets: list[Wallet]
    records: list[Record]
    mandatory_expenses: list[MandatoryExpenseRecord]
    transfers: list[Transfer]
    summary: ImportSummary
    debts: list[Debt]
    debt_payments: list[DebtPayment]
    assets: list[Asset]
    asset_snapshots: list[AssetSnapshot]
    goals: list[Goal]

    def __iter__(self):
        yield self.wallets
        yield self.records
        yield self.mandatory_expenses
        yield self.transfers
        yield self.summary

    def __len__(self) -> int:
        return 5

    def __getitem__(self, index: int):
        legacy = (
            self.wallets,
            self.records,
            self.mandatory_expenses,
            self.transfers,
            self.summary,
        )
        return legacy[index]


class BackupFormatError(ValueError):
    """Raised when backup JSON has invalid structure."""


class BackupIntegrityError(ValueError):
    """Raised when snapshot checksum does not match payload."""


class BackupReadonlyError(PermissionError):
    """Raised when readonly snapshot import is attempted without force."""


def _record_to_payload(record: Record) -> dict:
    item = {
        "id": int(record.id),
        "date": record.date.isoformat() if isinstance(record.date, dt_date) else record.date,
        "type": record_type_name(record),
        "wallet_id": int(getattr(record, "wallet_id", SYSTEM_WALLET_ID)),
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


def _wallet_to_payload(wallet: Wallet) -> dict:
    return {
        "id": int(wallet.id),
        "name": str(wallet.name),
        "currency": str(wallet.currency or "KZT").upper(),
        "initial_balance": to_money_float(wallet.initial_balance),
        "system": bool(wallet.system),
        "allow_negative": bool(wallet.allow_negative),
        "is_active": bool(wallet.is_active),
    }


def _transfer_to_payload(transfer: Transfer) -> dict:
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


def _budget_to_payload(budget: Budget) -> dict[str, Any]:
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


def _distribution_snapshot_to_payload(snapshot: FrozenDistributionRow) -> dict[str, Any]:
    return {
        "month": str(snapshot.month),
        "is_negative": bool(snapshot.is_negative),
        "auto_fixed": bool(snapshot.auto_fixed),
        "column_order": list(snapshot.column_order),
        "headings_by_column": dict(snapshot.headings_by_column),
        "values_by_column": dict(snapshot.values_by_column),
    }


def _distribution_item_to_payload(item: DistributionItem) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "name": str(item.name),
        "group_name": str(item.group_name or ""),
        "sort_order": int(item.sort_order),
        "pct": float(item.pct),
        "pct_minor": int(item.pct_minor),
        "is_active": bool(item.is_active),
    }


def _distribution_subitem_to_payload(subitem: DistributionSubitem) -> dict[str, Any]:
    return {
        "id": int(subitem.id),
        "item_id": int(subitem.item_id),
        "name": str(subitem.name),
        "sort_order": int(subitem.sort_order),
        "pct": float(subitem.pct),
        "pct_minor": int(subitem.pct_minor),
        "is_active": bool(subitem.is_active),
    }


def _debt_to_payload(debt: Debt) -> dict[str, Any]:
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


def _debt_payment_to_payload(payment: DebtPayment) -> dict[str, Any]:
    return {
        "id": int(payment.id),
        "debt_id": int(payment.debt_id),
        "record_id": int(payment.record_id) if payment.record_id is not None else None,
        "operation_type": payment.operation_type.value,
        "principal_paid_minor": int(payment.principal_paid_minor),
        "is_write_off": bool(payment.is_write_off),
        "payment_date": str(payment.payment_date),
    }


def _asset_to_payload(asset: Asset) -> dict[str, Any]:
    return {
        "id": int(asset.id),
        "name": str(asset.name),
        "category": str(asset.category.value),
        "currency": str(asset.currency).upper(),
        "is_active": bool(asset.is_active),
        "created_at": str(asset.created_at),
        "description": str(asset.description or ""),
    }


def _asset_snapshot_to_payload(snapshot: AssetSnapshot) -> dict[str, Any]:
    return {
        "id": int(snapshot.id),
        "asset_id": int(snapshot.asset_id),
        "snapshot_date": str(snapshot.snapshot_date),
        "value_minor": int(snapshot.value_minor),
        "currency": str(snapshot.currency).upper(),
        "note": str(snapshot.note or ""),
    }


def _goal_to_payload(goal: Goal) -> dict[str, Any]:
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


def _tag_to_payload(tag: Tag) -> dict[str, Any]:
    return {
        "id": int(tag.id),
        "name": str(tag.name),
        "color": str(tag.color or ""),
        "usage_count": int(tag.usage_count or 0),
        "last_used_at": str(tag.last_used_at or ""),
    }


def _record_tag_to_payload(record_id: int, tag_id: int) -> dict[str, Any]:
    return {
        "record_id": int(record_id),
        "tag_id": int(tag_id),
    }


def _as_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def compute_checksum(data: dict) -> str:
    if not isinstance(data, dict):
        raise BackupFormatError("Checksum payload must be object")
    serialized = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _now_utc_iso8601() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unwrap_backup_payload(payload: Any, *, force: bool = False) -> dict[str, Any]:
    if isinstance(payload, list):
        return {"records": payload}
    if not isinstance(payload, dict):
        raise BackupFormatError("Invalid backup JSON structure: root must be object")

    has_meta = "meta" in payload
    has_data = "data" in payload
    if not has_meta and not has_data:
        return payload
    if has_meta != has_data:
        raise BackupFormatError("Snapshot backup must include both 'meta' and 'data'")

    meta = payload.get("meta")
    data = payload.get("data")
    if not isinstance(meta, dict):
        raise BackupFormatError("Snapshot backup: 'meta' must be object")
    if not isinstance(data, dict):
        raise BackupFormatError("Snapshot backup: 'data' must be object")

    checksum = meta.get("checksum")
    if not isinstance(checksum, str) or not checksum.strip():
        raise BackupFormatError("Snapshot backup: missing meta.checksum")
    actual_checksum = compute_checksum(data)
    if checksum != actual_checksum:
        raise BackupIntegrityError("Snapshot checksum mismatch")

    readonly = bool(meta.get("readonly", False))
    if readonly and not force:
        raise BackupReadonlyError("Readonly snapshot cannot be imported without force=True")

    return data


def unwrap_backup_payload(payload: Any, *, force: bool = False) -> dict[str, Any]:
    return _unwrap_backup_payload(payload, force=force)


def _validate_transfer_integrity(records: list[Record], transfers: list[Transfer]) -> list[str]:
    errors: list[str] = []
    by_transfer: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is None:
            continue
        by_transfer.setdefault(record.transfer_id, []).append(record)

    transfer_ids = {transfer.id for transfer in transfers}

    for transfer_id in sorted(by_transfer):
        if transfer_id not in transfer_ids:
            errors.append(f"Dangling transfer-linked records for missing transfer #{transfer_id}")

    for transfer in transfers:
        linked = by_transfer.get(transfer.id, [])
        if len(linked) != 2:
            errors.append(
                f"Transfer integrity violated for #{transfer.id}: "
                f"expected 2 linked records, got {len(linked)}"
            )
            continue
        types = {record.type for record in linked}
        if types != {"expense", "income"}:
            errors.append(
                f"Transfer integrity violated for #{transfer.id}: "
                "requires one expense and one income"
            )
            continue
        expense_record = next(
            (record for record in linked if isinstance(record, ExpenseRecord)), None
        )
        income_record = next(
            (record for record in linked if isinstance(record, IncomeRecord)), None
        )
        if expense_record is None or income_record is None:
            errors.append(
                f"Transfer integrity violated for #{transfer.id}: "
                "cannot resolve income/expense pair"
            )
            continue
        if expense_record.wallet_id != transfer.from_wallet_id:
            errors.append(f"Transfer #{transfer.id}: from_wallet_id mismatch")
        if income_record.wallet_id != transfer.to_wallet_id:
            errors.append(f"Transfer #{transfer.id}: to_wallet_id mismatch")

    return errors


def _derive_transfers_from_linked_records(
    records: list[Record],
) -> tuple[list[Transfer], list[str]]:
    transfers: list[Transfer] = []
    errors: list[str] = []
    grouped: dict[int, list[Record]] = {}
    for record in records:
        if record.transfer_id is not None:
            grouped.setdefault(record.transfer_id, []).append(record)

    for transfer_id in sorted(grouped):
        linked = grouped[transfer_id]
        if len(linked) != 2:
            errors.append(
                f"Transfer integrity violated for #{transfer_id}: "
                f"expected 2 linked records, got {len(linked)}"
            )
            continue
        expense_record = next(
            (record for record in linked if isinstance(record, ExpenseRecord)), None
        )
        income_record = next(
            (record for record in linked if isinstance(record, IncomeRecord)), None
        )
        if expense_record is None or income_record is None:
            errors.append(
                f"Transfer integrity violated for #{transfer_id}: "
                "requires one expense and one income"
            )
            continue
        try:
            transfers.append(
                Transfer(
                    id=transfer_id,
                    from_wallet_id=expense_record.wallet_id,
                    to_wallet_id=income_record.wallet_id,
                    date=expense_record.date,
                    amount_original=to_money_float(expense_record.amount_original or 0.0),
                    currency=str(expense_record.currency or "KZT").upper(),
                    rate_at_operation=to_rate_float(expense_record.rate_at_operation),
                    amount_base=to_money_float(expense_record.amount_base or 0.0),
                    description=str(expense_record.description or ""),
                )
            )
        except (TypeError, ValueError, KeyError) as exc:
            errors.append(f"Transfer #{transfer_id}: invalid linked records ({exc})")

    return transfers, errors


def export_full_backup_to_json(
    filepath: str,
    *,
    wallets: Sequence[Wallet] | None = None,
    records: Sequence[Record],
    tags: Sequence[Tag] = (),
    mandatory_expenses: Sequence[MandatoryExpenseRecord],
    budgets: Sequence[Budget] = (),
    debts: Sequence[Debt] = (),
    debt_payments: Sequence[DebtPayment] = (),
    assets: Sequence[Asset] = (),
    asset_snapshots: Sequence[AssetSnapshot] = (),
    goals: Sequence[Goal] = (),
    distribution_items: Sequence[DistributionItem] = (),
    distribution_subitems: Sequence[DistributionSubitem] = (),
    distribution_snapshots: Sequence[FrozenDistributionRow] = (),
    transfers: Sequence[Transfer] = (),
    initial_balance: float = 0.0,
    readonly: bool = True,
    storage_mode: str = "unknown",
) -> None:
    normalized_wallets = list(wallets or [])
    if not normalized_wallets:
        normalized_wallets = [
            Wallet(
                id=SYSTEM_WALLET_ID,
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
            record_tag_rows.append(_record_tag_to_payload(record_id, existing.id))
    data_payload = {
        "wallets": [_wallet_to_payload(wallet) for wallet in normalized_wallets],
        "records": [_record_to_payload(record) for record in records],
        "mandatory_expenses": [_record_to_payload(expense) for expense in mandatory_expenses],
        "tags": [
            _tag_to_payload(tag) for tag in sorted(tags_by_name.values(), key=lambda item: item.id)
        ],
        "record_tags": record_tag_rows,
        "budgets": [_budget_to_payload(budget) for budget in budgets],
        "debts": [_debt_to_payload(debt) for debt in debts],
        "debt_payments": [_debt_payment_to_payload(payment) for payment in debt_payments],
        "assets": [_asset_to_payload(asset) for asset in assets],
        "asset_snapshots": [_asset_snapshot_to_payload(snapshot) for snapshot in asset_snapshots],
        "goals": [_goal_to_payload(goal) for goal in goals],
        "distribution_items": [_distribution_item_to_payload(item) for item in distribution_items],
        "distribution_subitems": [
            _distribution_subitem_to_payload(subitem) for subitem in distribution_subitems
        ],
        "distribution_snapshots": [
            _distribution_snapshot_to_payload(snapshot) for snapshot in distribution_snapshots
        ],
        "transfers": [_transfer_to_payload(transfer) for transfer in transfers],
    }
    payload: dict[str, Any]
    if readonly:
        payload = {
            "meta": {
                "created_at": _now_utc_iso8601(),
                "app_version": __version__,
                "storage": str(storage_mode or "unknown"),
                "readonly": True,
                "checksum": compute_checksum(data_payload),
            },
            "data": data_payload,
        }
    else:
        payload = data_payload

    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix="backup-",
        suffix=".json",
        dir=directory or None,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp_path, filepath)
    except (OSError, TypeError, ValueError):
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def import_full_backup_from_json(
    filepath: str,
    *,
    force: bool = False,
) -> ImportedBackupData:
    """Legacy-compatible backup JSON parser.

    Prefer ImportService.import_file(...) for application imports that should
    validate and commit data transactionally. This helper stays available for
    tests, migration tooling, and low-level snapshot inspection.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"JSON file not found: {filepath}")

    try:
        with open(filepath, encoding="utf-8") as fp:
            raw_payload = json.load(fp)
    except json.JSONDecodeError as exc:
        raise BackupFormatError(f"Invalid backup JSON: {exc}") from exc

    source_payload = _unwrap_backup_payload(raw_payload, force=force)

    migrated_legacy = not all(key in source_payload for key in ("wallets", "records", "transfers"))

    raw_records = source_payload.get("records", [])
    raw_mandatory = source_payload.get("mandatory_expenses", [])
    raw_wallets = source_payload.get("wallets", [])
    raw_transfers = source_payload.get("transfers", [])
    raw_debts = source_payload.get("debts", [])
    raw_debt_payments = source_payload.get("debt_payments", [])
    raw_assets = source_payload.get("assets", [])
    raw_asset_snapshots = source_payload.get("asset_snapshots", [])
    raw_goals = source_payload.get("goals", [])
    raw_tags = source_payload.get("tags", [])
    raw_record_tags = source_payload.get("record_tags", [])

    if not isinstance(raw_records, list) or not isinstance(raw_mandatory, list):
        raise BackupFormatError(
            "Invalid backup JSON structure: records and mandatory_expenses must be arrays"
        )

    if migrated_legacy:
        if not isinstance(raw_wallets, list):
            raw_wallets = []
        if not isinstance(raw_transfers, list):
            raw_transfers = []

    if not isinstance(raw_wallets, list) or not isinstance(raw_transfers, list):
        raise BackupFormatError(
            "Invalid backup JSON structure: wallets and transfers must be arrays"
        )
    if not isinstance(raw_debts, list) or not isinstance(raw_debt_payments, list):
        raise BackupFormatError(
            "Invalid backup JSON structure: debts and debt_payments must be arrays"
        )
    if (
        not isinstance(raw_assets, list)
        or not isinstance(raw_asset_snapshots, list)
        or not isinstance(raw_goals, list)
    ):
        raise BackupFormatError(
            "Invalid backup JSON structure: assets, asset_snapshots, and goals must be arrays"
        )
    if not isinstance(raw_tags, list) or not isinstance(raw_record_tags, list):
        raise BackupFormatError(
            "Invalid backup JSON structure: tags and record_tags must be arrays"
        )

    errors: list[str] = []
    skipped = 0
    imported = 0
    tags_by_id: dict[int, str] = {}
    for idx, item in enumerate(raw_tags, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"tags[{idx}]: invalid item type")
            continue
        tag_id = _as_positive_int(item.get("id"))
        tag_name = normalize_tag_name(item.get("name"))
        if tag_id is None or not tag_name:
            skipped += 1
            errors.append(f"tags[{idx}]: invalid tag")
            continue
        tags_by_id[tag_id] = tag_name
        imported += 1

    record_tag_names: dict[int, list[str]] = {}
    for idx, item in enumerate(raw_record_tags, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"record_tags[{idx}]: invalid item type")
            continue
        record_id = _as_positive_int(item.get("record_id"))
        tag_id = _as_positive_int(item.get("tag_id"))
        inline_name = normalize_tag_name(item.get("name"))
        tag_name = inline_name or tags_by_id.get(int(tag_id or 0), "")
        if record_id is None or not tag_name:
            skipped += 1
            errors.append(f"record_tags[{idx}]: invalid record-tag assignment")
            continue
        record_tag_names.setdefault(record_id, []).append(tag_name)
        imported += 1

    wallets: list[Wallet] = []
    if raw_wallets:
        for idx, item in enumerate(raw_wallets, start=1):
            if not isinstance(item, dict):
                skipped += 1
                errors.append(f"wallets[{idx}]: invalid item type")
                continue
            try:
                wallet = Wallet(
                    id=int(item.get("id", 0)),
                    name=str(item.get("name", "") or f"Wallet {idx}"),
                    currency=str(item.get("currency", "KZT") or "KZT").upper(),
                    initial_balance=to_money_float(item.get("initial_balance", 0.0) or 0.0),
                    system=bool(item.get("system", int(item.get("id", 0)) == SYSTEM_WALLET_ID)),
                    allow_negative=bool(item.get("allow_negative", False)),
                    is_active=bool(item.get("is_active", True)),
                )
                wallets.append(wallet)
                imported += 1
            except (TypeError, ValueError, KeyError) as exc:
                skipped += 1
                errors.append(f"wallets[{idx}]: invalid wallet ({exc})")
    else:
        # Legacy migration: move global initial_balance into system wallet.
        legacy_balance = to_money_float(source_payload.get("initial_balance", 0.0) or 0.0)
        wallets = [
            Wallet(
                id=SYSTEM_WALLET_ID,
                name="Main wallet",
                currency="KZT",
                initial_balance=legacy_balance,
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ]

    wallet_ids = {wallet.id for wallet in wallets}
    if SYSTEM_WALLET_ID not in wallet_ids:
        wallets.insert(
            0,
            Wallet(
                id=SYSTEM_WALLET_ID,
                name="Main wallet",
                currency="KZT",
                initial_balance=0.0,
                system=True,
                allow_negative=False,
                is_active=True,
            ),
        )
        wallet_ids = {wallet.id for wallet in wallets}

    records: list[Record] = []
    for idx, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"records[{idx}]: invalid item type")
            continue
        record_payload = dict(item)
        if "wallet_id" not in record_payload:
            record_payload["wallet_id"] = SYSTEM_WALLET_ID
        record_id = _as_positive_int(record_payload.get("id"))
        record_payload["tags"] = list(
            normalize_tag_names(
                tuple(record_payload.get("tags", []) or [])
                + tuple(record_tag_names.get(int(record_id or 0), []))
            )
        )
        record, _, error = parse_import_row(
            record_payload,
            row_label=f"records[{idx}]",
            policy=ImportPolicy.FULL_BACKUP,
        )
        if error:
            skipped += 1
            errors.append(error)
            continue
        if record is None:
            continue
        if record.wallet_id not in wallet_ids:
            skipped += 1
            errors.append(f"records[{idx}]: wallet not found ({record.wallet_id})")
            continue
        imported += 1
        records.append(record)

    mandatory_expenses: list[MandatoryExpenseRecord] = []
    for idx, item in enumerate(raw_mandatory, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"mandatory_expenses[{idx}]: invalid item type")
            continue
        payload = dict(item)
        payload["type"] = "mandatory_expense"
        if "wallet_id" not in payload:
            payload["wallet_id"] = SYSTEM_WALLET_ID
        record, _, error = parse_import_row(
            payload,
            row_label=f"mandatory_expenses[{idx}]",
            policy=ImportPolicy.FULL_BACKUP,
            mandatory_only=True,
        )
        if error:
            skipped += 1
            errors.append(error)
            continue
        if isinstance(record, MandatoryExpenseRecord):
            if record.wallet_id not in wallet_ids:
                skipped += 1
                errors.append(f"mandatory_expenses[{idx}]: wallet not found ({record.wallet_id})")
                continue
            imported += 1
            mandatory_expenses.append(record)

    transfers: list[Transfer] = []
    if raw_transfers:
        for idx, item in enumerate(raw_transfers, start=1):
            if not isinstance(item, dict):
                skipped += 1
                errors.append(f"transfers[{idx}]: invalid item type")
                continue
            try:
                transfer = Transfer(
                    id=int(item.get("id", 0)),
                    from_wallet_id=int(item.get("from_wallet_id", 0)),
                    to_wallet_id=int(item.get("to_wallet_id", 0)),
                    date=str(item.get("date", "") or ""),
                    amount_original=to_money_float(item.get("amount_original", 0.0) or 0.0),
                    currency=str(item.get("currency", "KZT") or "KZT").upper(),
                    rate_at_operation=to_rate_float(item.get("rate_at_operation", 1.0) or 1.0),
                    amount_base=to_money_float(item.get("amount_base", 0.0) or 0.0),
                    description=str(item.get("description", "") or ""),
                )
            except (TypeError, ValueError, KeyError) as exc:
                skipped += 1
                errors.append(f"transfers[{idx}]: invalid transfer ({exc})")
                continue
            if transfer.from_wallet_id not in wallet_ids or transfer.to_wallet_id not in wallet_ids:
                skipped += 1
                errors.append(f"transfers[{idx}]: wallet not found")
                continue
            transfers.append(transfer)
            imported += 1
    else:
        derived, derive_errors = _derive_transfers_from_linked_records(records)
        transfers.extend(derived)
        skipped += len(derive_errors)
        errors.extend(derive_errors)

    integrity_errors = _validate_transfer_integrity(records, transfers)
    if integrity_errors:
        skipped += len(integrity_errors)
        errors.extend(integrity_errors)

    debts: list[Debt] = []
    for idx, item in enumerate(raw_debts, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"debts[{idx}]: invalid item type")
            continue
        try:
            debt = Debt(
                id=int(item.get("id", 0)),
                contact_name=str(item.get("contact_name", "") or ""),
                kind=DebtKind(str(item.get("kind", DebtKind.DEBT.value) or DebtKind.DEBT.value)),
                total_amount_minor=int(item.get("total_amount_minor", 0)),
                remaining_amount_minor=int(item.get("remaining_amount_minor", 0)),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                interest_rate=float(item.get("interest_rate", 0.0) or 0.0),
                status=DebtStatus(
                    str(item.get("status", DebtStatus.OPEN.value) or DebtStatus.OPEN.value)
                ),
                created_at=str(item.get("created_at", "") or ""),
                closed_at=(
                    str(item.get("closed_at")) if item.get("closed_at") not in (None, "") else None
                ),
            )
        except (TypeError, ValueError, KeyError) as exc:
            skipped += 1
            errors.append(f"debts[{idx}]: invalid debt ({exc})")
            continue
        debts.append(debt)
        imported += 1

    debt_ids = {int(debt.id) for debt in debts}
    record_ids = {int(record.id) for record in records}
    debt_payments: list[DebtPayment] = []
    for idx, item in enumerate(raw_debt_payments, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"debt_payments[{idx}]: invalid item type")
            continue
        try:
            record_id_val = item.get("record_id")
            record_id = int(record_id_val) if record_id_val not in (None, "") else None
            payment = DebtPayment(
                id=int(item.get("id", 0)),
                debt_id=int(item.get("debt_id", 0)),
                record_id=record_id,
                operation_type=DebtOperationType(
                    str(
                        item.get(
                            "operation_type",
                            DebtOperationType.DEBT_FORGIVE.value
                            if bool(item.get("is_write_off", False))
                            else DebtOperationType.DEBT_REPAY.value,
                        )
                        or DebtOperationType.DEBT_REPAY.value
                    )
                ),
                principal_paid_minor=int(item.get("principal_paid_minor", 0)),
                is_write_off=bool(item.get("is_write_off", False)),
                payment_date=str(item.get("payment_date", "") or ""),
            )
        except (TypeError, ValueError, KeyError) as exc:
            skipped += 1
            errors.append(f"debt_payments[{idx}]: invalid debt payment ({exc})")
            continue
        if int(payment.debt_id) not in debt_ids:
            skipped += 1
            errors.append(f"debt_payments[{idx}]: debt not found ({payment.debt_id})")
            continue
        if payment.record_id is not None and int(payment.record_id) not in record_ids:
            skipped += 1
            errors.append(f"debt_payments[{idx}]: record not found ({payment.record_id})")
            continue
        debt_payments.append(payment)
        imported += 1

    assets: list[Asset] = []
    for idx, item in enumerate(raw_assets, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"assets[{idx}]: invalid item type")
            continue
        try:
            asset = Asset(
                id=int(item.get("id", 0)),
                name=str(item.get("name", "") or ""),
                category=AssetCategory(str(item.get("category", "other") or "other")),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                is_active=bool(item.get("is_active", True)),
                created_at=str(item.get("created_at", "") or ""),
                description=str(item.get("description", "") or ""),
            )
        except (TypeError, ValueError, KeyError) as exc:
            skipped += 1
            errors.append(f"assets[{idx}]: invalid asset ({exc})")
            continue
        assets.append(asset)
        imported += 1

    asset_ids = {int(asset.id) for asset in assets}
    asset_snapshots: list[AssetSnapshot] = []
    for idx, item in enumerate(raw_asset_snapshots, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"asset_snapshots[{idx}]: invalid item type")
            continue
        try:
            snapshot = AssetSnapshot(
                id=int(item.get("id", 0)),
                asset_id=int(item.get("asset_id", 0)),
                snapshot_date=str(item.get("snapshot_date", "") or ""),
                value_minor=int(item.get("value_minor", 0)),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                note=str(item.get("note", "") or ""),
            )
        except (TypeError, ValueError, KeyError) as exc:
            skipped += 1
            errors.append(f"asset_snapshots[{idx}]: invalid asset snapshot ({exc})")
            continue
        if int(snapshot.asset_id) not in asset_ids:
            skipped += 1
            errors.append(f"asset_snapshots[{idx}]: asset not found ({snapshot.asset_id})")
            continue
        asset_snapshots.append(snapshot)
        imported += 1

    goals: list[Goal] = []
    for idx, item in enumerate(raw_goals, start=1):
        if not isinstance(item, dict):
            skipped += 1
            errors.append(f"goals[{idx}]: invalid item type")
            continue
        try:
            goal = Goal(
                id=int(item.get("id", 0)),
                title=str(item.get("title", "") or ""),
                target_amount_minor=int(item.get("target_amount_minor", 0)),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                created_at=str(item.get("created_at", "") or ""),
                is_completed=bool(item.get("is_completed", False)),
                target_date=str(item.get("target_date"))
                if item.get("target_date") not in (None, "")
                else None,
                description=str(item.get("description", "") or ""),
            )
        except (TypeError, ValueError, KeyError) as exc:
            skipped += 1
            errors.append(f"goals[{idx}]: invalid goal ({exc})")
            continue
        goals.append(goal)
        imported += 1

    logger.info(
        "JSON backup import completed: imported=%s skipped=%s file=%s legacy=%s",
        imported,
        skipped,
        filepath,
        migrated_legacy,
    )
    return ImportedBackupData(
        wallets=wallets,
        records=records,
        mandatory_expenses=mandatory_expenses,
        transfers=transfers,
        summary=(imported, skipped, errors),
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
    )


def create_backup(
    filepath: str,
    *,
    wallets: Sequence[Wallet] | None = None,
    records: Sequence[Record],
    mandatory_expenses: Sequence[MandatoryExpenseRecord],
    budgets: Sequence[Budget] = (),
    debts: Sequence[Debt] = (),
    debt_payments: Sequence[DebtPayment] = (),
    assets: Sequence[Asset] = (),
    asset_snapshots: Sequence[AssetSnapshot] = (),
    goals: Sequence[Goal] = (),
    distribution_items: Sequence[DistributionItem] = (),
    distribution_subitems: Sequence[DistributionSubitem] = (),
    distribution_snapshots: Sequence[FrozenDistributionRow] = (),
    transfers: Sequence[Transfer] = (),
    initial_balance: float = 0.0,
    readonly: bool = True,
    storage_mode: str = "unknown",
) -> None:
    export_full_backup_to_json(
        filepath,
        wallets=wallets,
        records=records,
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
        transfers=transfers,
        initial_balance=initial_balance,
        readonly=readonly,
        storage_mode=storage_mode,
    )


def import_backup(
    filepath: str,
    *,
    force: bool = False,
) -> ImportedBackupData:
    warnings.warn(
        "import_backup(...) is deprecated; use import_full_backup_from_json(...) "
        "for low-level snapshot parsing or ImportService.import_file(...) for "
        "application imports.",
        DeprecationWarning,
        stacklevel=2,
    )
    return import_full_backup_from_json(filepath, force=force)
