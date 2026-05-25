from __future__ import annotations

import logging
from typing import Any

from app.importing.finance import ImportCapabilities
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import MandatoryExpenseRecord, Record
from domain.wallets import Wallet
from services.importing.models import ImportCounters, PreparedImportPayload, ReplaceSectionFlags
from services.importing.parser import ParsedImportData, parse_transfer_row
from utils.finance.money import to_money_float, to_rate_float
from utils.import_core import parse_import_row, safe_type


def prepare_records_payload(owner: Any, parsed: ParsedImportData) -> PreparedImportPayload:
    initial_balance = (
        to_money_float(parsed.initial_balance)
        if parsed.initial_balance is not None
        else to_money_float(owner._finance_service.get_system_initial_balance())
    )
    wallets = owner._wallets_from_payload(parsed.wallets) if parsed.wallets else []
    if wallets:
        wallets, wallet_id_map = owner._normalize_wallet_ids(wallets)
        parsed = owner._remap_parsed_wallet_ids(parsed, wallet_id_map)
    wallet_ids = (
        {wallet.id for wallet in wallets}
        if wallets
        else {wallet.id for wallet in owner._finance_service.load_wallets()}
    )
    get_rate = (
        owner._finance_service.get_currency_rate
        if owner._policy == ImportPolicy.CURRENT_RATE
        else None
    )

    raw_transfer_ops: list[dict[str, Any]] = []
    parsed_records: list[Record] = []
    parsed_mandatory_templates: list[MandatoryExpenseRecord] = []
    strict_distribution = parsed.file_type == "json" and owner._policy == ImportPolicy.FULL_BACKUP
    distribution_items, distribution_subitems_by_item = owner._distribution_structure_from_payload(
        parsed.distribution_items,
        parsed.distribution_subitems,
        strict=strict_distribution,
    )
    budgets = owner._budgets_from_payload(parsed.budgets, strict=strict_distribution)
    debts = owner._debts_from_payload(parsed.debts, strict=strict_distribution)
    assets = owner._assets_from_payload(parsed.assets, strict=strict_distribution)
    asset_snapshots = owner._asset_snapshots_from_payload(
        parsed.asset_snapshots,
        assets=assets,
        strict=strict_distribution,
    )
    goals = owner._goals_from_payload(parsed.goals, strict=strict_distribution)
    frozen_distribution_rows = owner._frozen_rows_from_payload(
        parsed.distribution_snapshots,
        strict=strict_distribution,
    )
    errors: list[str] = []
    skipped = 0
    imported = 0
    seen_initial_balance = parsed.initial_balance is not None

    next_transfer_id = 1
    for index, row in enumerate(parsed.rows, start=2):
        row_type = safe_type(str(row.get("type", "") or "")).lower()
        row_label = f"row {index}"
        if row_type == "transfer":
            parsed_row, transfer, next_transfer_id, error = parse_transfer_row(
                {str(k): str(v) if v is not None else "" for k, v in row.items()},
                row_label=row_label,
                policy=owner._policy,
                get_rate=get_rate,
                next_transfer_id=next_transfer_id,
                wallet_ids=wallet_ids,
            )
            if error:
                skipped += 1
                errors.append(error)
                continue
            if transfer is None or parsed_row is None:
                skipped += 1
                errors.append(f"{row_label}: failed to parse transfer row")
                continue
            parsed_records.extend(parsed_row)
            raw_transfer_ops.append(
                {
                    "transfer_id": int(transfer.id),
                    "from_wallet_id": transfer.from_wallet_id,
                    "to_wallet_id": transfer.to_wallet_id,
                    "transfer_date": str(transfer.date),
                    "amount": to_money_float(transfer.amount_original),
                    "amount_base": to_money_float(transfer.amount_base),
                    "currency": str(transfer.currency).upper(),
                    "rate_at_operation": to_rate_float(transfer.rate_at_operation),
                    "description": str(transfer.description or ""),
                }
            )
            imported += 1
            continue

        record, parsed_balance, error = parse_import_row(
            row,
            row_label=row_label,
            policy=owner._policy,
            get_rate=get_rate,
            mandatory_only=False,
        )
        if error:
            skipped += 1
            errors.append(error)
            continue
        if parsed_balance is not None:
            if seen_initial_balance:
                skipped += 1
                errors.append(f"{row_label}: duplicate initial_balance row")
                continue
            initial_balance = float(parsed_balance)
            seen_initial_balance = True
            continue
        if record is None:
            continue
        if record.wallet_id not in wallet_ids:
            skipped += 1
            errors.append(f"{row_label}: wallet not found ({record.wallet_id})")
            continue
        parsed_records.append(record)
        imported += 1

    for index, row in enumerate(parsed.mandatory_rows, start=2):
        payload = dict(row)
        if not str(payload.get("type", "") or "").strip():
            payload["type"] = "mandatory_expense"
        record, _, error = parse_import_row(
            payload,
            row_label=f"mandatory[{index}]",
            policy=owner._policy,
            get_rate=get_rate,
            mandatory_only=True,
        )
        if error:
            skipped += 1
            errors.append(error)
            continue
        if isinstance(record, MandatoryExpenseRecord):
            parsed_mandatory_templates.append(record)
            imported += 1

    parsed_records = owner._normalize_record_debt_links(
        parsed_records,
        allowed_debt_ids=owner._resolve_allowed_debt_ids_for_record_links(
            parsed=parsed,
            imported_debts=debts,
        ),
        strict=strict_distribution,
    )
    debt_payments = owner._debt_payments_from_payload(
        parsed.debt_payments,
        debts=debts,
        records=parsed_records,
        strict=strict_distribution,
    )

    return PreparedImportPayload(
        parsed=parsed,
        initial_balance=initial_balance,
        wallets=wallets,
        parsed_records=parsed_records,
        parsed_mandatory_templates=parsed_mandatory_templates,
        budgets=budgets,
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems_by_item=distribution_subitems_by_item,
        frozen_distribution_rows=frozen_distribution_rows,
        raw_transfer_ops=raw_transfer_ops,
        imported=imported,
        skipped=skipped,
        errors=errors,
    )


def commit_prepared_records_payload(
    owner: Any,
    prepared: PreparedImportPayload,
    *,
    logger: logging.Logger,
) -> ImportResult:
    parsed = prepared.parsed
    initial_balance = prepared.initial_balance
    wallets = list(prepared.wallets)
    imported_wallets = len(wallets)
    parsed_records = list(prepared.parsed_records)
    parsed_mandatory_templates = list(prepared.parsed_mandatory_templates)
    budgets = list(prepared.budgets)
    debts = list(prepared.debts)
    debt_payments = list(prepared.debt_payments)
    assets = list(prepared.assets)
    asset_snapshots = list(prepared.asset_snapshots)
    goals = list(prepared.goals)
    distribution_items = list(prepared.distribution_items)
    distribution_subitems_by_item = {
        int(item_id): list(subitems)
        for item_id, subitems in prepared.distribution_subitems_by_item.items()
    }
    frozen_distribution_rows = list(prepared.frozen_distribution_rows)
    raw_transfer_ops = list(prepared.raw_transfer_ops)
    imported = prepared.imported
    skipped = prepared.skipped
    errors = tuple(prepared.errors)

    if (
        imported == 0
        and not wallets
        and not parsed_mandatory_templates
        and not budgets
        and not debts
        and not debt_payments
        and not assets
        and not asset_snapshots
        and not goals
        and not distribution_items
        and not frozen_distribution_rows
        and not raw_transfer_ops
    ):
        return ImportResult(imported=0, skipped=skipped, errors=errors)

    flags = owner._resolve_replace_flags(
        parsed=parsed,
        debts=debts,
        debt_payments=debt_payments,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        budgets=budgets,
        distribution_items=distribution_items,
        distribution_subitems_by_item=distribution_subitems_by_item,
        frozen_distribution_rows=frozen_distribution_rows,
    )
    capabilities: ImportCapabilities = owner._finance_service.get_import_capabilities()
    fast_replace_enabled = capabilities.supports_bulk_replace is True
    json_bulk_replace_allowed = parsed.file_type == "json"
    if (
        fast_replace_enabled
        and json_bulk_replace_allowed
        and (owner._policy != ImportPolicy.CURRENT_RATE or json_bulk_replace_allowed)
    ):
        return _commit_bulk_prepared_records_payload(
            owner,
            parsed=parsed,
            initial_balance=initial_balance,
            wallets=wallets,
            imported_wallets=imported_wallets,
            parsed_records=parsed_records,
            parsed_mandatory_templates=parsed_mandatory_templates,
            budgets=budgets,
            debts=debts,
            debt_payments=debt_payments,
            assets=assets,
            asset_snapshots=asset_snapshots,
            goals=goals,
            distribution_items=distribution_items,
            distribution_subitems_by_item=distribution_subitems_by_item,
            frozen_distribution_rows=frozen_distribution_rows,
            raw_transfer_ops=raw_transfer_ops,
            imported=imported,
            skipped=skipped,
            errors=errors,
            capabilities=capabilities,
            flags=flags,
            logger=logger,
        )

    return _commit_incremental_prepared_records_payload(
        owner,
        parsed=parsed,
        initial_balance=initial_balance,
        wallets=wallets,
        imported_wallets=imported_wallets,
        parsed_records=parsed_records,
        parsed_mandatory_templates=parsed_mandatory_templates,
        budgets=budgets,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems_by_item=distribution_subitems_by_item,
        frozen_distribution_rows=frozen_distribution_rows,
        raw_transfer_ops=raw_transfer_ops,
        imported=imported,
        skipped=skipped,
        errors=errors,
        capabilities=capabilities,
        flags=flags,
        logger=logger,
    )


def _commit_bulk_prepared_records_payload(
    owner: Any,
    *,
    parsed: ParsedImportData,
    initial_balance: float,
    wallets: list[Wallet],
    imported_wallets: int,
    parsed_records: list[Record],
    parsed_mandatory_templates: list[MandatoryExpenseRecord],
    budgets: list[Budget],
    debts: list[Debt],
    debt_payments: list[DebtPayment],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    distribution_items: list[DistributionItem],
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
    frozen_distribution_rows: list[FrozenDistributionRow],
    raw_transfer_ops: list[dict[str, Any]],
    imported: int,
    skipped: int,
    errors: tuple[str, ...],
    capabilities: ImportCapabilities,
    flags: ReplaceSectionFlags,
    logger: logging.Logger,
) -> ImportResult:
    target_wallets = wallets if wallets else None
    wallet_ids = (
        {wallet.id for wallet in target_wallets}
        if target_wallets
        else {wallet.id for wallet in owner._finance_service.load_wallets()}
    )

    owner._ensure_wallets_exist(parsed_records, raw_transfer_ops, wallet_ids)
    records, transfers, counters = owner._build_import_operations(
        parsed_records=parsed_records,
        transfer_rows=raw_transfer_ops,
        counters=ImportCounters(wallets=imported_wallets),
    )
    mandatory_templates = owner._normalize_mandatory_templates(parsed_mandatory_templates)
    owner._finance_service.replace_all_for_import(
        wallets=target_wallets,
        initial_balance=initial_balance,
        records=records,
        transfers=transfers,
        mandatory_templates=mandatory_templates,
        tags=owner._tags_from_payload(parsed.tags),
        debts=debts if flags.can_replace_debts else None,
        debt_payments=debt_payments if flags.can_replace_debts else None,
        assets=assets
        if flags.can_replace_assets and capabilities.supports_assets_replace
        else None,
        asset_snapshots=(
            asset_snapshots
            if flags.can_replace_assets and capabilities.supports_assets_replace
            else None
        ),
        goals=goals if flags.can_replace_goals and capabilities.supports_goals_replace else None,
        preserve_existing_mandatory=not bool(target_wallets),
    )
    owner._apply_supported_replacements(
        file_type=parsed.file_type,
        budgets=budgets,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems_by_item=distribution_subitems_by_item,
        frozen_distribution_rows=frozen_distribution_rows,
        capabilities=capabilities,
        flags=flags,
        include_assets_and_goals=False,
    )
    owner._finance_service.normalize_operation_ids_for_import()
    logger.info(
        "Import completed (bulk) file=%s wallets=%s records=%s transfers=%s",
        parsed.path,
        counters.wallets,
        counters.records,
        counters.transfers,
    )
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


def _commit_incremental_prepared_records_payload(
    owner: Any,
    *,
    parsed: ParsedImportData,
    initial_balance: float,
    wallets: list[Wallet],
    imported_wallets: int,
    parsed_records: list[Record],
    parsed_mandatory_templates: list[MandatoryExpenseRecord],
    budgets: list[Budget],
    assets: list[Asset],
    asset_snapshots: list[AssetSnapshot],
    goals: list[Goal],
    distribution_items: list[DistributionItem],
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
    frozen_distribution_rows: list[FrozenDistributionRow],
    raw_transfer_ops: list[dict[str, Any]],
    imported: int,
    skipped: int,
    errors: tuple[str, ...],
    capabilities: ImportCapabilities,
    flags: ReplaceSectionFlags,
    logger: logging.Logger,
) -> ImportResult:
    if wallets:
        owner._finance_service.reset_all_for_import(
            wallets=wallets, initial_balance=initial_balance
        )
        wallet_ids = {wallet.id for wallet in wallets}
    else:
        owner._finance_service.reset_operations_for_import(initial_balance=initial_balance)
        wallet_ids = {wallet.id for wallet in owner._finance_service.load_wallets()}

    owner._ensure_wallets_exist(parsed_records, raw_transfer_ops, wallet_ids)
    counters = ImportCounters(wallets=imported_wallets)
    counters = owner._apply_operations_with_relaxed_wallet_limits(
        parsed_records=parsed_records,
        transfer_rows=raw_transfer_ops,
        counters=counters,
    )
    owner._apply_mandatory_templates(parsed_mandatory_templates)
    owner._apply_supported_replacements(
        file_type=parsed.file_type,
        budgets=budgets,
        assets=assets,
        asset_snapshots=asset_snapshots,
        goals=goals,
        distribution_items=distribution_items,
        distribution_subitems_by_item=distribution_subitems_by_item,
        frozen_distribution_rows=frozen_distribution_rows,
        capabilities=capabilities,
        flags=flags,
    )
    logger.info(
        "Import completed file=%s wallets=%s records=%s transfers=%s",
        parsed.path,
        counters.wallets,
        counters.records,
        counters.transfers,
    )
    owner._finance_service.normalize_operation_ids_for_import()
    return ImportResult(imported=imported, skipped=skipped, errors=errors)
