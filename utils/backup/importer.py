from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.records import MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from utils.finance.money import to_money_float, to_rate_float
from utils.import_core import parse_import_row
from utils.records.tags import normalize_tag_name, normalize_tag_names

logger = logging.getLogger(__name__)


def as_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def import_full_backup_from_json(
    filepath: str,
    *,
    force: bool,
    max_backup_file_size: int,
    system_wallet_id: int,
    unwrap_backup_payload: Callable[[Any], dict[str, Any]],
    backup_format_error: type[Exception],
    validate_transfer_integrity: Callable[[list[Record], list[Transfer]], list[str]],
    derive_transfers_from_linked_records: Callable[
        [list[Record]], tuple[list[Transfer], list[str]]
    ],
    imported_data_factory: Callable[..., Any],
) -> Any:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"JSON file not found: {filepath}")
    file_size = os.path.getsize(filepath)
    if file_size > max_backup_file_size:
        raise backup_format_error(
            f"Backup JSON is too large: {file_size} bytes (limit: {max_backup_file_size})"
        )

    try:
        with open(filepath, encoding="utf-8") as fp:
            raw_payload = json.load(fp)
    except json.JSONDecodeError as exc:
        raise backup_format_error(f"Invalid backup JSON: {exc}") from exc

    source_payload = unwrap_backup_payload(raw_payload)
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
        raise backup_format_error(
            "Invalid backup JSON structure: records and mandatory_expenses must be arrays"
        )

    if migrated_legacy:
        if not isinstance(raw_wallets, list):
            raw_wallets = []
        if not isinstance(raw_transfers, list):
            raw_transfers = []

    if not isinstance(raw_wallets, list) or not isinstance(raw_transfers, list):
        raise backup_format_error(
            "Invalid backup JSON structure: wallets and transfers must be arrays"
        )
    if not isinstance(raw_debts, list) or not isinstance(raw_debt_payments, list):
        raise backup_format_error(
            "Invalid backup JSON structure: debts and debt_payments must be arrays"
        )
    if (
        not isinstance(raw_assets, list)
        or not isinstance(raw_asset_snapshots, list)
        or not isinstance(raw_goals, list)
    ):
        raise backup_format_error(
            "Invalid backup JSON structure: assets, asset_snapshots, and goals must be arrays"
        )
    if not isinstance(raw_tags, list) or not isinstance(raw_record_tags, list):
        raise backup_format_error(
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
        tag_id = as_positive_int(item.get("id"))
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
        record_id = as_positive_int(item.get("record_id"))
        tag_id = as_positive_int(item.get("tag_id"))
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
                    system=bool(item.get("system", int(item.get("id", 0)) == system_wallet_id)),
                    allow_negative=bool(item.get("allow_negative", False)),
                    is_active=bool(item.get("is_active", True)),
                )
                wallets.append(wallet)
                imported += 1
            except (TypeError, ValueError, KeyError) as exc:
                skipped += 1
                errors.append(f"wallets[{idx}]: invalid wallet ({exc})")
    else:
        legacy_balance = to_money_float(source_payload.get("initial_balance", 0.0) or 0.0)
        wallets = [
            Wallet(
                id=system_wallet_id,
                name="Main wallet",
                currency="KZT",
                initial_balance=legacy_balance,
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ]

    wallet_ids = {wallet.id for wallet in wallets}
    if system_wallet_id not in wallet_ids:
        wallets.insert(
            0,
            Wallet(
                id=system_wallet_id,
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
            record_payload["wallet_id"] = system_wallet_id
        record_id = as_positive_int(record_payload.get("id"))
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
            payload["wallet_id"] = system_wallet_id
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
        derived, derive_errors = derive_transfers_from_linked_records(records)
        transfers.extend(derived)
        skipped += len(derive_errors)
        errors.extend(derive_errors)

    integrity_errors = validate_transfer_integrity(records, transfers)
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
    return imported_data_factory(
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
