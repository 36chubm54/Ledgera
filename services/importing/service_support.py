from __future__ import annotations

import logging
from typing import Any, cast

from app.importing.finance import FinanceService
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from services.importing.adapters import (
    asset_snapshots_payload_to_domain,
    assets_payload_to_domain,
    budgets_payload_to_domain,
    build_import_error,
    debt_payments_payload_to_domain,
    debts_payload_to_domain,
    distribution_payload_to_domain,
    ensure_import_wallets_exist,
    frozen_distribution_rows_from_payload,
    map_import_wallet_id,
    normalize_import_mandatory_description,
    normalize_import_wallet_ids,
    normalize_records_debt_links,
    remap_import_wallet_ids,
    remap_import_wallet_ids_in_row,
    resolve_record_linkable_debt_ids,
    split_import_transfer_pair,
    wallets_payload_to_domain,
)
from services.importing.execution_support import (
    TransferRow,
)
from services.importing.execution_support import (
    apply_mandatory_templates as apply_import_mandatory_templates,
)
from services.importing.execution_support import (
    apply_operations_with_relaxed_wallet_limits as apply_import_operations_with_relaxed_wallet_limits,  # noqa: E501
)
from services.importing.execution_support import (
    build_import_operations as build_service_import_operations,
)
from services.importing.execution_support import (
    normalize_mandatory_templates as normalize_import_mandatory_templates,
)
from services.importing.models import ImportCounters
from services.importing.parser import ParsedImportData
from utils.finance.money import to_money_float, to_rate_float


def build_import_operations(
    *,
    parsed_records: list[Record],
    transfer_rows: list[dict[str, Any]],
    counters: ImportCounters,
    split_transfer_pair_fn,
) -> tuple[list[Record], list[Transfer], ImportCounters]:
    return build_service_import_operations(
        parsed_records=parsed_records,
        transfer_rows=cast(list[TransferRow], transfer_rows),
        counters=counters,
        split_transfer_pair_fn=split_transfer_pair_fn,
    )


def normalize_mandatory_templates(
    templates: list[MandatoryExpenseRecord],
    *,
    normalize_description_fn,
) -> list[MandatoryExpenseRecord]:
    return normalize_import_mandatory_templates(
        templates,
        normalize_description_fn=normalize_description_fn,
    )


def frozen_rows_from_payload(
    payloads: list[dict[str, Any]],
    *,
    strict: bool,
    logger: logging.Logger,
) -> list[FrozenDistributionRow]:
    return frozen_distribution_rows_from_payload(payloads, strict=strict, logger=logger)


def budgets_from_payload(payloads: list[dict[str, Any]], *, strict: bool) -> list[Budget]:
    return budgets_payload_to_domain(payloads, strict=strict)


def distribution_structure_from_payload(
    item_payloads: list[dict[str, Any]],
    subitem_payloads: list[dict[str, Any]],
    *,
    strict: bool,
) -> tuple[list[DistributionItem], dict[int, list[DistributionSubitem]]]:
    return distribution_payload_to_domain(item_payloads, subitem_payloads, strict=strict)


def assets_from_payload(raw_assets: list[dict[str, Any]], *, strict: bool) -> list[Asset]:
    return assets_payload_to_domain(raw_assets, strict=strict)


def asset_snapshots_from_payload(
    raw_snapshots: list[dict[str, Any]],
    *,
    assets: list[Asset],
    strict: bool,
) -> list[AssetSnapshot]:
    return asset_snapshots_payload_to_domain(raw_snapshots, assets=assets, strict=strict)


def debts_from_payload(raw_debts: list[dict[str, Any]], *, strict: bool) -> list[Debt]:
    return debts_payload_to_domain(raw_debts, strict=strict)


def debt_payments_from_payload(
    raw_payments: list[dict[str, Any]],
    *,
    debts: list[Debt],
    records: list[Record],
    strict: bool,
) -> list[DebtPayment]:
    return debt_payments_payload_to_domain(
        raw_payments,
        debts=debts,
        records=records,
        strict=strict,
    )


def resolve_allowed_debt_ids_for_record_links(
    *,
    parsed: ParsedImportData,
    imported_debts: list[Debt],
    finance_service: FinanceService,
) -> set[int] | None:
    return resolve_record_linkable_debt_ids(
        parsed=parsed,
        imported_debts=imported_debts,
        finance_service=finance_service,
    )


def normalize_record_debt_links(
    records: list[Record],
    *,
    allowed_debt_ids: set[int] | None,
    strict: bool,
) -> list[Record]:
    return normalize_records_debt_links(records, allowed_debt_ids=allowed_debt_ids, strict=strict)


def apply_operations_with_relaxed_wallet_limits(
    finance_service: FinanceService,
    *,
    parsed_records: list[Record],
    transfer_rows: list[dict[str, Any]],
    counters: ImportCounters,
    fixed_amount_base_fn,
    fixed_rate_fn,
    normalize_description_fn,
    split_transfer_pair_fn,
) -> ImportCounters:
    return apply_import_operations_with_relaxed_wallet_limits(
        finance_service,
        parsed_records=parsed_records,
        transfer_rows=cast(list[TransferRow], transfer_rows),
        counters=counters,
        fixed_amount_base_fn=fixed_amount_base_fn,
        fixed_rate_fn=fixed_rate_fn,
        normalize_description_fn=normalize_description_fn,
        split_transfer_pair_fn=split_transfer_pair_fn,
    )


def apply_mandatory_templates(
    finance_service: FinanceService,
    templates: list[MandatoryExpenseRecord],
    *,
    fixed_amount_base_fn,
    fixed_rate_fn,
    normalize_description_fn,
) -> None:
    apply_import_mandatory_templates(
        finance_service,
        templates,
        fixed_amount_base_fn=fixed_amount_base_fn,
        fixed_rate_fn=fixed_rate_fn,
        normalize_description_fn=normalize_description_fn,
    )


def ensure_wallets_exist(
    parsed_records: list[Record],
    transfer_rows: list[dict[str, Any]],
    wallet_ids: set[int],
) -> None:
    ensure_import_wallets_exist(parsed_records, transfer_rows, wallet_ids)


def wallets_from_payload(raw_wallets: list[dict[str, Any]]) -> list[Wallet]:
    return wallets_payload_to_domain(raw_wallets)


def normalize_wallet_ids(wallets: list[Wallet]) -> tuple[list[Wallet], dict[int, int]]:
    return normalize_import_wallet_ids(wallets)


def remap_parsed_wallet_ids(
    parsed: ParsedImportData,
    wallet_id_map: dict[int, int],
) -> ParsedImportData:
    return remap_import_wallet_ids(parsed, wallet_id_map)


def remap_wallet_ids_in_row(
    row: dict[str, Any],
    wallet_id_map: dict[int, int],
    *,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    return remap_import_wallet_ids_in_row(row, wallet_id_map, fields=fields)


def map_wallet_id(value: Any, wallet_id_map: dict[int, int]) -> int | None:
    return map_import_wallet_id(value, wallet_id_map)


def build_error(errors: list[str]) -> str:
    return build_import_error(errors)


def normalize_mandatory_description(description: str, category: str) -> str:
    return normalize_import_mandatory_description(description, category)


def fixed_amount_base(policy: ImportPolicy, amount_base: float | None) -> float | None:
    if policy == ImportPolicy.CURRENT_RATE:
        return None
    if amount_base is None:
        return None
    return to_money_float(amount_base)


def fixed_rate(policy: ImportPolicy, rate_at_operation: float | None) -> float | None:
    if policy == ImportPolicy.CURRENT_RATE:
        return None
    if rate_at_operation is None:
        return None
    return to_rate_float(rate_at_operation)


def split_transfer_pair(
    linked: list[Record],
    *,
    label: str,
) -> tuple[ExpenseRecord, IncomeRecord]:
    return split_import_transfer_pair(linked, label=label)
