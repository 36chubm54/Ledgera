from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.importing.finance import FinanceService
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.tags import Tag
from domain.wallets import Wallet
from services.importing.parser import ParsedImportData
from services.importing.payload_support import (
    asset_snapshots_from_payload,
    assets_from_payload,
    budgets_from_payload,
    build_error,
    debt_payments_from_payload,
    debts_from_payload,
    distribution_structure_from_payload,
    ensure_wallets_exist,
    frozen_rows_from_payload,
    goals_from_payload,
    map_wallet_id,
    normalize_mandatory_description,
    normalize_record_debt_links,
    normalize_wallet_ids,
    remap_parsed_wallet_ids,
    remap_wallet_ids_in_row,
    resolve_allowed_debt_ids_for_record_links,
    split_transfer_pair,
    wallets_from_payload,
)


def tags_from_payload(payload: list[dict[str, Any]]) -> list[Tag]:
    tags: list[Tag] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        try:
            tag_id = int(item.get("id", 0) or 0)
        except (TypeError, ValueError):
            tag_id = 0
        try:
            usage_count = int(item.get("usage_count", 0) or 0)
        except (TypeError, ValueError):
            usage_count = 0
        tags.append(
            Tag(
                id=tag_id,
                name=name,
                color=str(item.get("color", "") or ""),
                usage_count=usage_count,
                last_used_at=str(item.get("last_used_at", "") or ""),
            )
        )
    return tags


def frozen_distribution_rows_from_payload(
    payloads: list[dict[str, Any]],
    *,
    strict: bool,
    logger: Any,
) -> list[FrozenDistributionRow]:
    return frozen_rows_from_payload(payloads, strict=strict, logger=logger)


def budgets_payload_to_domain(
    payloads: list[dict[str, Any]],
    *,
    strict: bool,
) -> list[Budget]:
    return budgets_from_payload(payloads, strict=strict)


def distribution_payload_to_domain(
    item_payloads: list[dict[str, Any]],
    subitem_payloads: list[dict[str, Any]],
    *,
    strict: bool,
) -> tuple[list[DistributionItem], dict[int, list[DistributionSubitem]]]:
    return distribution_structure_from_payload(
        item_payloads,
        subitem_payloads,
        strict=strict,
    )


def assets_payload_to_domain(raw_assets: list[dict[str, Any]], *, strict: bool) -> list[Asset]:
    return assets_from_payload(raw_assets, strict=strict)


def asset_snapshots_payload_to_domain(
    raw_snapshots: list[dict[str, Any]],
    *,
    assets: list[Asset],
    strict: bool,
) -> list[AssetSnapshot]:
    return asset_snapshots_from_payload(raw_snapshots, assets=assets, strict=strict)


def goals_payload_to_domain(raw_goals: list[dict[str, Any]], *, strict: bool) -> list[Goal]:
    return goals_from_payload(raw_goals, strict=strict)


def debts_payload_to_domain(raw_debts: list[dict[str, Any]], *, strict: bool) -> list[Debt]:
    return debts_from_payload(raw_debts, strict=strict)


def debt_payments_payload_to_domain(
    raw_payments: list[dict[str, Any]],
    *,
    debts: list[Debt],
    records: list[Record],
    strict: bool,
) -> list[DebtPayment]:
    return debt_payments_from_payload(
        raw_payments,
        debts=debts,
        records=records,
        strict=strict,
    )


def resolve_record_linkable_debt_ids(
    *,
    parsed: ParsedImportData,
    imported_debts: list[Debt],
    finance_service: FinanceService,
) -> set[int] | None:
    allowed_ids = resolve_allowed_debt_ids_for_record_links(
        parsed=parsed,
        imported_debts=imported_debts,
    )
    if allowed_ids is not None:
        return allowed_ids

    capabilities = finance_service.get_import_capabilities()
    if capabilities.supports_load_debts:
        debts = finance_service.load_debts()
        if isinstance(debts, Iterable):
            return {int(debt.id) for debt in debts}
    return None


def normalize_records_debt_links(
    records: list[Record],
    *,
    allowed_debt_ids: set[int] | None,
    strict: bool,
) -> list[Record]:
    return normalize_record_debt_links(
        records,
        allowed_debt_ids=allowed_debt_ids,
        strict=strict,
    )


def ensure_import_wallets_exist(
    parsed_records: list[Record],
    transfer_rows: list[dict[str, Any]],
    wallet_ids: set[int],
) -> None:
    ensure_wallets_exist(parsed_records, transfer_rows, wallet_ids)


def wallets_payload_to_domain(raw_wallets: list[dict[str, Any]]) -> list[Wallet]:
    return wallets_from_payload(raw_wallets)


def normalize_import_wallet_ids(wallets: list[Wallet]) -> tuple[list[Wallet], dict[int, int]]:
    return normalize_wallet_ids(wallets)


def remap_import_wallet_ids(
    parsed: ParsedImportData,
    wallet_id_map: dict[int, int],
) -> ParsedImportData:
    return remap_parsed_wallet_ids(parsed, wallet_id_map)


def remap_import_wallet_ids_in_row(
    row: dict[str, Any],
    wallet_id_map: dict[int, int],
    *,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    return remap_wallet_ids_in_row(row, wallet_id_map, fields=fields)


def map_import_wallet_id(value: Any, wallet_id_map: dict[int, int]) -> int | None:
    return map_wallet_id(value, wallet_id_map)


def build_import_error(errors: list[str]) -> str:
    return build_error(errors)


def normalize_import_mandatory_description(description: str, category: str) -> str:
    return normalize_mandatory_description(description, category)


def split_import_transfer_pair(
    linked: list[Record],
    *,
    label: str,
) -> tuple[ExpenseRecord, IncomeRecord]:
    return split_transfer_pair(linked, label=label)
