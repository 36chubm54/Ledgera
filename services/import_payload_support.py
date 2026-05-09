from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from typing import Any

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.wallets import Wallet
from services.import_parser import ParsedImportData
from utils.import_core import as_float, parse_optional_strict_int
from utils.money import to_money_float


def frozen_rows_from_payload(
    payloads: list[dict[str, Any]],
    *,
    strict: bool = False,
    logger,
) -> list[FrozenDistributionRow]:
    frozen_rows: list[FrozenDistributionRow] = []
    seen_months: set[str] = set()
    for index, item in enumerate(payloads):
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid distribution snapshot payload: expected object")
            continue
        month = str(item.get("month", "") or "").strip()
        if not month:
            if strict:
                raise ValueError(f"Distribution snapshot at index {index} is missing month")
            logger.warning("Skipping distribution snapshot without month at index %s", index)
            continue
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            if strict:
                raise ValueError(f"Distribution snapshot has invalid month: {month}") from exc
            logger.warning("Skipping distribution snapshot with invalid month '%s'", month)
            continue
        if month in seen_months:
            if strict:
                raise ValueError(f"Duplicate distribution snapshot month: {month}")
            logger.warning("Skipping duplicate distribution snapshot month '%s'", month)
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
        frozen_rows.append(
            FrozenDistributionRow(
                month=month,
                column_order=tuple(str(column) for column in column_order_raw),
                headings_by_column={str(k): str(v) for k, v in headings_raw.items()},
                values_by_column={str(k): str(v) for k, v in values_raw.items()},
                is_negative=bool(item.get("is_negative", False)),
                auto_fixed=bool(item.get("auto_fixed", False)),
            )
        )
        seen_months.add(month)
    return frozen_rows


def budgets_from_payload(
    payloads: list[dict[str, Any]],
    *,
    strict: bool = False,
) -> list[Budget]:
    budgets: list[Budget] = []
    seen_ids: set[int] = set()
    for item in payloads:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid budget payload: expected object")
            continue
        budget_id = parse_optional_strict_int(item.get("id")) or 0
        if budget_id <= 0:
            if strict:
                raise ValueError(f"Invalid budget id: {item.get('id')!r}")
            continue
        if budget_id in seen_ids:
            if strict:
                raise ValueError(f"Duplicate budget id: {budget_id}")
            continue
        category = str(item.get("category", "") or "").strip()
        scope_type = str(item.get("scope_type", "category") or "category").strip().lower()
        scope_value = str(item.get("scope_value", category) or category).strip()
        start_date = str(item.get("start_date", "") or "").strip()
        end_date = str(item.get("end_date", "") or "").strip()
        limit_kzt = as_float(item.get("limit_kzt"), None)
        limit_kzt_minor = parse_optional_strict_int(item.get("limit_kzt_minor"))
        if not category:
            if strict:
                raise ValueError(f"Budget #{budget_id} has empty category")
            continue
        if scope_type not in {"category", "tag"}:
            if strict:
                raise ValueError(f"Budget #{budget_id} has invalid scope_type")
            continue
        if not scope_value:
            if strict:
                raise ValueError(f"Budget #{budget_id} has empty scope_value")
            continue
        if not start_date or not end_date:
            if strict:
                raise ValueError(f"Budget #{budget_id} is missing start_date/end_date")
            continue
        if limit_kzt is None:
            if strict:
                raise ValueError(f"Budget #{budget_id} has invalid limit_kzt")
            continue
        if limit_kzt_minor is None:
            limit_kzt_minor = int(round(to_money_float(limit_kzt) * 100))
        if limit_kzt_minor <= 0:
            if strict:
                raise ValueError(f"Budget #{budget_id} must have positive limit_kzt_minor")
            continue
        seen_ids.add(budget_id)
        budgets.append(
            Budget(
                id=budget_id,
                category=category,
                start_date=start_date,
                end_date=end_date,
                limit_kzt=to_money_float(limit_kzt),
                limit_kzt_minor=int(limit_kzt_minor),
                include_mandatory=bool(item.get("include_mandatory", False)),
                scope_type=scope_type,
                scope_value=scope_value,
            )
        )
    return budgets


def distribution_structure_from_payload(
    item_payloads: list[dict[str, Any]],
    subitem_payloads: list[dict[str, Any]],
    *,
    strict: bool = False,
) -> tuple[list[DistributionItem], dict[int, list[DistributionSubitem]]]:
    items: list[DistributionItem] = []
    seen_item_ids: set[int] = set()
    for item in item_payloads:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid distribution item payload: expected object")
            continue
        item_id = parse_optional_strict_int(item.get("id")) or 0
        if item_id <= 0:
            if strict:
                raise ValueError(f"Invalid distribution item id: {item.get('id')!r}")
            continue
        if item_id in seen_item_ids:
            if strict:
                raise ValueError(f"Duplicate distribution item id: {item_id}")
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            if strict:
                raise ValueError(f"Distribution item #{item_id} has empty name")
            continue
        seen_item_ids.add(item_id)
        items.append(
            DistributionItem(
                id=item_id,
                name=name,
                group_name=str(item.get("group_name", "") or ""),
                sort_order=int(parse_optional_strict_int(item.get("sort_order")) or 0),
                pct=to_money_float(as_float(item.get("pct"), 0.0) or 0.0),
                pct_minor=int(parse_optional_strict_int(item.get("pct_minor")) or 0),
                is_active=bool(item.get("is_active", True)),
            )
        )
    item_ids = {int(item.id) for item in items}
    subitems_by_item: dict[int, list[DistributionSubitem]] = defaultdict(list)
    seen_subitem_ids: set[int] = set()
    for subitem in subitem_payloads:
        if not isinstance(subitem, dict):
            if strict:
                raise ValueError("Invalid distribution subitem payload: expected object")
            continue
        subitem_id = parse_optional_strict_int(subitem.get("id")) or 0
        item_id = parse_optional_strict_int(subitem.get("item_id")) or 0
        if subitem_id <= 0:
            if strict:
                raise ValueError(f"Invalid distribution subitem id: {subitem.get('id')!r}")
            continue
        if subitem_id in seen_subitem_ids:
            if strict:
                raise ValueError(f"Duplicate distribution subitem id: {subitem_id}")
            continue
        if item_id <= 0 or item_id not in item_ids:
            if strict:
                raise ValueError(
                    f"Distribution subitem #{subitem_id} references missing item_id={item_id}"
                )
            continue
        name = str(subitem.get("name", "") or "").strip()
        if not name:
            if strict:
                raise ValueError(f"Distribution subitem #{subitem_id} has empty name")
            continue
        seen_subitem_ids.add(subitem_id)
        subitems_by_item[item_id].append(
            DistributionSubitem(
                id=subitem_id,
                item_id=item_id,
                name=name,
                sort_order=int(parse_optional_strict_int(subitem.get("sort_order")) or 0),
                pct=to_money_float(as_float(subitem.get("pct"), 0.0) or 0.0),
                pct_minor=int(parse_optional_strict_int(subitem.get("pct_minor")) or 0),
                is_active=bool(subitem.get("is_active", True)),
            )
        )
    return items, dict(subitems_by_item)


def assets_from_payload(raw_assets: list[dict[str, Any]], *, strict: bool = False) -> list[Asset]:
    assets: list[Asset] = []
    seen_ids: set[int] = set()
    for item in raw_assets:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid asset payload: expected object")
            continue
        asset_id = parse_optional_strict_int(item.get("id")) or 0
        if asset_id <= 0:
            if strict:
                raise ValueError(f"Invalid asset id: {item.get('id')!r}")
            continue
        if asset_id in seen_ids:
            if strict:
                raise ValueError(f"Duplicate asset id: {asset_id}")
            continue
        try:
            asset = Asset(
                id=asset_id,
                name=str(item.get("name", "") or "").strip(),
                category=AssetCategory(
                    str(item.get("category", "other") or "other").strip().lower()
                ),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                is_active=bool(item.get("is_active", True)),
                created_at=str(item.get("created_at", "") or "").strip(),
                description=str(item.get("description", "") or ""),
            )
        except (TypeError, ValueError):
            if strict:
                raise
            continue
        seen_ids.add(asset_id)
        assets.append(asset)
    return assets


def asset_snapshots_from_payload(
    raw_snapshots: list[dict[str, Any]],
    *,
    assets: list[Asset],
    strict: bool = False,
) -> list[AssetSnapshot]:
    snapshots: list[AssetSnapshot] = []
    seen_ids: set[int] = set()
    asset_ids = {int(asset.id) for asset in assets}
    for item in raw_snapshots:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid asset snapshot payload: expected object")
            continue
        snapshot_id = parse_optional_strict_int(item.get("id")) or 0
        asset_id = parse_optional_strict_int(item.get("asset_id")) or 0
        if snapshot_id <= 0:
            if strict:
                raise ValueError(f"Invalid asset snapshot id: {item.get('id')!r}")
            continue
        if snapshot_id in seen_ids:
            if strict:
                raise ValueError(f"Duplicate asset snapshot id: {snapshot_id}")
            continue
        if asset_id not in asset_ids:
            if strict:
                raise ValueError(
                    f"Asset snapshot #{snapshot_id} references missing asset_id={asset_id}"
                )
            continue
        try:
            snapshot = AssetSnapshot(
                id=snapshot_id,
                asset_id=asset_id,
                snapshot_date=str(item.get("snapshot_date", "") or "").strip(),
                value_minor=int(parse_optional_strict_int(item.get("value_minor")) or 0),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                note=str(item.get("note", "") or ""),
            )
        except (TypeError, ValueError):
            if strict:
                raise
            continue
        seen_ids.add(snapshot_id)
        snapshots.append(snapshot)
    return snapshots


def goals_from_payload(raw_goals: list[dict[str, Any]], *, strict: bool = False) -> list[Goal]:
    goals: list[Goal] = []
    seen_ids: set[int] = set()
    for item in raw_goals:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid goal payload: expected object")
            continue
        goal_id = parse_optional_strict_int(item.get("id")) or 0
        if goal_id <= 0:
            if strict:
                raise ValueError(f"Invalid goal id: {item.get('id')!r}")
            continue
        if goal_id in seen_ids:
            if strict:
                raise ValueError(f"Duplicate goal id: {goal_id}")
            continue
        try:
            goal = Goal(
                id=goal_id,
                title=str(item.get("title", "") or "").strip(),
                target_amount_minor=int(
                    parse_optional_strict_int(item.get("target_amount_minor")) or 0
                ),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                created_at=str(item.get("created_at", "") or "").strip(),
                is_completed=bool(item.get("is_completed", False)),
                target_date=str(item.get("target_date", "") or "").strip() or None,
                description=str(item.get("description", "") or ""),
            )
        except (TypeError, ValueError):
            if strict:
                raise
            continue
        seen_ids.add(goal_id)
        goals.append(goal)
    return goals


def debts_from_payload(raw_debts: list[dict[str, Any]], *, strict: bool = False) -> list[Debt]:
    debts: list[Debt] = []
    seen_ids: set[int] = set()
    for item in raw_debts:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid debt payload: expected object")
            continue
        debt_id = parse_optional_strict_int(item.get("id")) or 0
        if debt_id <= 0:
            if strict:
                raise ValueError(f"Invalid debt id: {item.get('id')!r}")
            continue
        if debt_id in seen_ids:
            if strict:
                raise ValueError(f"Duplicate debt id: {debt_id}")
            continue
        try:
            debt = Debt(
                id=debt_id,
                contact_name=str(item.get("contact_name", "") or "").strip(),
                kind=DebtKind(str(item.get("kind", "") or "").strip().lower()),
                total_amount_minor=int(
                    parse_optional_strict_int(item.get("total_amount_minor")) or 0
                ),
                remaining_amount_minor=int(
                    parse_optional_strict_int(item.get("remaining_amount_minor")) or 0
                ),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                interest_rate=float(as_float(item.get("interest_rate"), 0.0) or 0.0),
                status=DebtStatus(str(item.get("status", "") or "").strip().lower()),
                created_at=str(item.get("created_at", "") or "").strip(),
                closed_at=str(item.get("closed_at", "") or "").strip() or None,
            )
        except (TypeError, ValueError):
            if strict:
                raise
            continue
        seen_ids.add(debt_id)
        debts.append(debt)
    return debts


def debt_payments_from_payload(
    raw_payments: list[dict[str, Any]],
    *,
    debts: list[Debt],
    records: list[Record],
    strict: bool = False,
) -> list[DebtPayment]:
    payments: list[DebtPayment] = []
    seen_ids: set[int] = set()
    debt_ids = {int(debt.id) for debt in debts}
    record_ids = {
        int(record.id)
        for record in records
        if getattr(record, "id", None) is not None and int(record.id) > 0
    }
    for item in raw_payments:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("Invalid debt payment payload: expected object")
            continue
        payment_id = parse_optional_strict_int(item.get("id")) or 0
        debt_id = parse_optional_strict_int(item.get("debt_id")) or 0
        record_id = parse_optional_strict_int(item.get("record_id"))
        if payment_id <= 0:
            if strict:
                raise ValueError(f"Invalid debt payment id: {item.get('id')!r}")
            continue
        if payment_id in seen_ids:
            if strict:
                raise ValueError(f"Duplicate debt payment id: {payment_id}")
            continue
        if debt_id not in debt_ids:
            if strict:
                raise ValueError(f"Debt payment #{payment_id} references missing debt_id={debt_id}")
            continue
        if record_id is not None and record_id not in record_ids:
            if strict:
                raise ValueError(
                    f"Debt payment #{payment_id} references missing record_id={record_id}"
                )
            continue
        try:
            payment = DebtPayment(
                id=payment_id,
                debt_id=debt_id,
                record_id=record_id,
                operation_type=DebtOperationType(
                    str(item.get("operation_type", "") or "").strip().lower()
                ),
                principal_paid_minor=int(
                    parse_optional_strict_int(item.get("principal_paid_minor")) or 0
                ),
                is_write_off=bool(item.get("is_write_off", False)),
                payment_date=str(item.get("payment_date", "") or "").strip(),
            )
        except (TypeError, ValueError):
            if strict:
                raise
            continue
        seen_ids.add(payment_id)
        payments.append(payment)
    return payments


def resolve_allowed_debt_ids_for_record_links(
    *,
    parsed: ParsedImportData,
    imported_debts: list[Debt],
) -> set[int] | None:
    if parsed.file_type == "json" and "debts" in set(parsed.json_sections_present):
        return {int(debt.id) for debt in imported_debts}
    return None


def normalize_record_debt_links(
    records: list[Record],
    *,
    allowed_debt_ids: set[int] | None,
    strict: bool = False,
) -> list[Record]:
    if allowed_debt_ids is None:
        return records
    normalized_records: list[Record] = []
    for record in records:
        if record.related_debt_id is None or int(record.related_debt_id) in allowed_debt_ids:
            normalized_records.append(record)
            continue
        if strict:
            raise ValueError(
                f"Record #{record.id} references missing debt #{record.related_debt_id}"
            )
        normalized_records.append(replace(record, related_debt_id=None))
    return normalized_records


def ensure_wallets_exist(
    parsed_records: list[Record],
    transfer_rows: list[dict[str, Any]],
    wallet_ids: set[int],
) -> None:
    for record in parsed_records:
        if int(record.wallet_id) not in wallet_ids:
            raise ValueError(f"Wallet not found during import: {record.wallet_id}")
    for transfer in transfer_rows:
        from_wallet_id = int(transfer["from_wallet_id"])
        to_wallet_id = int(transfer["to_wallet_id"])
        if from_wallet_id not in wallet_ids:
            raise ValueError(f"Wallet not found during import: {from_wallet_id}")
        if to_wallet_id not in wallet_ids:
            raise ValueError(f"Wallet not found during import: {to_wallet_id}")


def wallets_from_payload(raw_wallets: list[dict[str, Any]]) -> list[Wallet]:
    wallets: list[Wallet] = []
    seen_ids: set[int] = set()
    system_wallet_ids: set[int] = set()
    for item in raw_wallets:
        wallet_id = parse_optional_strict_int(item.get("id"))
        if item.get("id") not in (None, "") and wallet_id is None:
            raise ValueError(f"Invalid wallet id in import payload: {item.get('id')}")
        wallet_id = wallet_id or 0
        if wallet_id <= 0:
            continue
        if wallet_id in seen_ids:
            raise ValueError(f"Duplicate wallet id in import payload: {wallet_id}")
        seen_ids.add(wallet_id)
        is_system = bool(item.get("system", wallet_id == 1))
        if is_system:
            system_wallet_ids.add(wallet_id)
        wallets.append(
            Wallet(
                id=wallet_id,
                name=str(item.get("name", "") or f"Wallet {wallet_id}"),
                currency=str(item.get("currency", "KZT") or "KZT").upper(),
                initial_balance=to_money_float(as_float(item.get("initial_balance"), 0.0) or 0.0),
                system=is_system,
                allow_negative=bool(item.get("allow_negative", False)),
                is_active=bool(item.get("is_active", True)),
            )
        )
    if len(system_wallet_ids) > 1:
        duplicates = ", ".join(str(wallet_id) for wallet_id in sorted(system_wallet_ids))
        raise ValueError(f"Multiple system wallets in import payload: {duplicates}")
    if not wallets:
        wallets = [
            Wallet(
                id=1,
                name="Main wallet",
                currency="KZT",
                initial_balance=0.0,
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ]
    return wallets


def normalize_wallet_ids(wallets: list[Wallet]) -> tuple[list[Wallet], dict[int, int]]:
    normalized: list[Wallet] = []
    wallet_id_map: dict[int, int] = {}
    for new_id, wallet in enumerate(sorted(wallets, key=lambda item: int(item.id)), start=1):
        wallet_id_map[int(wallet.id)] = new_id
        normalized.append(replace(wallet, id=new_id, system=bool(wallet.system) or new_id == 1))
    if normalized and not any(wallet.system for wallet in normalized):
        normalized[0] = replace(normalized[0], system=True)
    return normalized, wallet_id_map


def remap_parsed_wallet_ids(
    parsed: ParsedImportData,
    wallet_id_map: dict[int, int],
) -> ParsedImportData:
    rows = [
        remap_wallet_ids_in_row(
            row,
            wallet_id_map,
            fields=("wallet_id", "from_wallet_id", "to_wallet_id"),
        )
        for row in parsed.rows
    ]
    mandatory_rows = [
        remap_wallet_ids_in_row(row, wallet_id_map, fields=("wallet_id",))
        for row in parsed.mandatory_rows
    ]
    wallets = [
        remap_wallet_ids_in_row(wallet, wallet_id_map, fields=("id",)) for wallet in parsed.wallets
    ]
    return ParsedImportData(
        path=parsed.path,
        file_type=parsed.file_type,
        rows=rows,
        mandatory_rows=mandatory_rows,
        budgets=list(parsed.budgets),
        debts=list(parsed.debts),
        debt_payments=list(parsed.debt_payments),
        assets=list(parsed.assets),
        asset_snapshots=list(parsed.asset_snapshots),
        goals=list(parsed.goals),
        distribution_items=list(parsed.distribution_items),
        distribution_subitems=list(parsed.distribution_subitems),
        distribution_snapshots=list(parsed.distribution_snapshots),
        wallets=wallets,
        tags=list(parsed.tags),
        record_tags=list(parsed.record_tags),
        initial_balance=parsed.initial_balance,
        json_sections_present=parsed.json_sections_present,
    )


def remap_wallet_ids_in_row(
    row: dict[str, Any],
    wallet_id_map: dict[int, int],
    *,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    remapped = dict(row)
    for field in fields:
        value = remapped.get(field)
        mapped = map_wallet_id(value, wallet_id_map)
        if mapped is not None:
            remapped[field] = mapped
    return remapped


def map_wallet_id(value: Any, wallet_id_map: dict[int, int]) -> int | None:
    wallet_id = parse_optional_strict_int(value)
    if value not in (None, "") and wallet_id is None:
        raise ValueError(f"Invalid wallet id in import payload: {value}")
    wallet_id = wallet_id or 0
    if wallet_id <= 0:
        return None
    return wallet_id_map.get(wallet_id, wallet_id)


def build_error(errors: list[str]) -> str:
    details = "; ".join(errors[:3])
    if len(errors) > 3:
        details += f"; ... and {len(errors) - 3} more"
    return f"Import aborted: {len(errors)} invalid rows ({details})"


def normalize_mandatory_description(description: str, category: str) -> str:
    normalized = description.strip()
    if normalized:
        return normalized
    category_name = (category or "").strip()
    if category_name:
        return f"Imported {category_name}"
    return "Imported mandatory expense"


def split_transfer_pair(
    linked: list[Record],
    *,
    label: str,
) -> tuple[ExpenseRecord, IncomeRecord]:
    if len(linked) != 2:
        raise ValueError(f"Transfer integrity violated for {label}: expected 2 linked records")
    source = next((item for item in linked if isinstance(item, ExpenseRecord)), None)
    target = next((item for item in linked if isinstance(item, IncomeRecord)), None)
    if source is None or target is None:
        raise ValueError(
            f"Transfer integrity violated for {label}: requires one expense and one income"
        )
    if source.currency != target.currency:
        raise ValueError(f"Transfer integrity violated for {label}: currency mismatch")
    if to_money_float(source.amount_original or 0.0) != to_money_float(
        target.amount_original or 0.0
    ):
        raise ValueError(f"Transfer integrity violated for {label}: amount_original mismatch")
    return source, target
