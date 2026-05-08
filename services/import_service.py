from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from app.finance_service import FinanceService, ImportCapabilities
from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from services.import_parser import ParsedImportData, parse_import_file, parse_transfer_row
from utils.import_core import (
    as_float,
    parse_import_row,
    parse_optional_strict_int,
    safe_type,
)
from utils.money import to_money_float, to_rate_float

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportCounters:
    wallets: int = 0
    records: int = 0
    transfers: int = 0


@dataclass(frozen=True)
class PreparedImportPayload:
    parsed: ParsedImportData
    initial_balance: float
    wallets: list[Wallet]
    parsed_records: list[Record]
    parsed_mandatory_templates: list[MandatoryExpenseRecord]
    budgets: list[Budget]
    debts: list[Debt]
    debt_payments: list[DebtPayment]
    assets: list[Asset]
    asset_snapshots: list[AssetSnapshot]
    goals: list[Goal]
    distribution_items: list[DistributionItem]
    distribution_subitems_by_item: dict[int, list[DistributionSubitem]]
    frozen_distribution_rows: list[FrozenDistributionRow]
    raw_transfer_ops: list[dict[str, Any]]
    imported: int
    skipped: int
    errors: list[str]


@dataclass(frozen=True)
class ReplaceSectionFlags:
    can_replace_debts: bool
    can_replace_assets: bool
    can_replace_goals: bool
    can_replace_budgets: bool
    can_replace_distribution_structure: bool
    can_replace_distribution_snapshots: bool


class ImportService:
    def __init__(
        self,
        finance_service: FinanceService,
        *,
        policy: ImportPolicy = ImportPolicy.FULL_BACKUP,
    ) -> None:
        self._finance_service = finance_service
        self._policy = policy

    def import_file(self, path: str, *, force: bool = False, dry_run: bool = False) -> ImportResult:
        parsed = parse_import_file(path, force=force)
        prepared = self._prepare_records_payload(parsed)
        if dry_run:
            return ImportResult(
                imported=prepared.imported,
                skipped=prepared.skipped,
                errors=tuple(prepared.errors),
                dry_run=True,
            )
        return self._finance_service.run_import_transaction(
            lambda: self._commit_prepared_records_payload(prepared)
        )

    def import_mandatory_file(self, path: str) -> ImportResult:
        parsed = parse_import_file(path)
        return self._finance_service.run_import_transaction(
            lambda: self._import_mandatory_payload(parsed)
        )

    def _prepare_records_payload(self, parsed: ParsedImportData) -> PreparedImportPayload:
        initial_balance = (
            to_money_float(parsed.initial_balance)
            if parsed.initial_balance is not None
            else to_money_float(self._finance_service.get_system_initial_balance())
        )
        wallets = self._wallets_from_payload(parsed.wallets) if parsed.wallets else []
        if wallets:
            wallets, wallet_id_map = self._normalize_wallet_ids(wallets)
            parsed = self._remap_parsed_wallet_ids(parsed, wallet_id_map)
        _ = len(wallets)

        wallet_ids = (
            {wallet.id for wallet in wallets}
            if wallets
            else {wallet.id for wallet in self._finance_service.load_wallets()}
        )
        get_rate = (
            self._finance_service.get_currency_rate
            if self._policy == ImportPolicy.CURRENT_RATE
            else None
        )

        raw_transfer_ops: list[dict[str, Any]] = []
        parsed_records: list[Record] = []
        parsed_mandatory_templates: list[MandatoryExpenseRecord] = []
        strict_distribution = (
            parsed.file_type == "json" and self._policy == ImportPolicy.FULL_BACKUP
        )
        distribution_items, distribution_subitems_by_item = (
            self._distribution_structure_from_payload(
                parsed.distribution_items,
                parsed.distribution_subitems,
                strict=strict_distribution,
            )
        )
        budgets = self._budgets_from_payload(parsed.budgets, strict=strict_distribution)
        debts = self._debts_from_payload(parsed.debts, strict=strict_distribution)
        assets = self._assets_from_payload(parsed.assets, strict=strict_distribution)
        asset_snapshots = self._asset_snapshots_from_payload(
            parsed.asset_snapshots,
            assets=assets,
            strict=strict_distribution,
        )
        goals = self._goals_from_payload(parsed.goals, strict=strict_distribution)
        frozen_distribution_rows = self._frozen_rows_from_payload(
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
                    policy=self._policy,
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
                        "amount_kzt": to_money_float(transfer.amount_kzt),
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
                policy=self._policy,
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
                policy=self._policy,
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

        parsed_records = self._normalize_record_debt_links(
            parsed_records,
            allowed_debt_ids=self._resolve_allowed_debt_ids_for_record_links(
                parsed=parsed,
                imported_debts=debts,
            ),
            strict=strict_distribution,
        )
        debt_payments = self._debt_payments_from_payload(
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

    def _commit_prepared_records_payload(self, prepared: PreparedImportPayload) -> ImportResult:
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

        flags = self._resolve_replace_flags(
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
        capabilities: ImportCapabilities = self._finance_service.get_import_capabilities()
        fast_replace_enabled = capabilities.supports_bulk_replace is True
        json_bulk_replace_allowed = parsed.file_type == "json"
        if (
            fast_replace_enabled
            and json_bulk_replace_allowed
            and (self._policy != ImportPolicy.CURRENT_RATE or json_bulk_replace_allowed)
        ):
            return self._commit_bulk_prepared_records_payload(
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
            )

        return self._commit_incremental_prepared_records_payload(
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
        )

    def _resolve_replace_flags(
        self,
        *,
        parsed: ParsedImportData,
        debts: list[Debt],
        debt_payments: list[DebtPayment],
        assets: list[Asset],
        asset_snapshots: list[AssetSnapshot],
        goals: list[Goal],
        budgets: list[Budget],
        distribution_items: list[DistributionItem],
        distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
        frozen_distribution_rows: list[FrozenDistributionRow],
    ) -> ReplaceSectionFlags:
        section_keys, fallback_used = self._resolve_json_section_keys(
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
        if fallback_used:
            logger.warning(
                "Import JSON section metadata is missing; enabling fallback detection from payload"
            )
        return ReplaceSectionFlags(
            can_replace_debts=self._section_present_or_payload_nonempty(
                section_keys,
                required_keys=("debts", "debt_payments"),
                payloads=(debts, debt_payments),
            ),
            can_replace_assets=self._section_present_or_payload_nonempty(
                section_keys,
                required_keys=("assets", "asset_snapshots"),
                payloads=(assets, asset_snapshots),
            ),
            can_replace_goals=self._section_present_or_payload_nonempty(
                section_keys,
                required_keys=("goals",),
                payloads=(goals,),
            ),
            can_replace_budgets=self._section_present_or_payload_nonempty(
                section_keys,
                required_keys=("budgets",),
                payloads=(budgets,),
            ),
            can_replace_distribution_structure=self._section_present_or_payload_nonempty(
                section_keys,
                required_keys=("distribution_items", "distribution_subitems"),
                payloads=(distribution_items, list(distribution_subitems_by_item.values())),
            ),
            can_replace_distribution_snapshots=self._section_present_or_payload_nonempty(
                section_keys,
                required_keys=("distribution_snapshots",),
                payloads=(frozen_distribution_rows,),
            ),
        )

    def _commit_bulk_prepared_records_payload(
        self,
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
    ) -> ImportResult:
        target_wallets = wallets if wallets else None
        if target_wallets:
            wallet_ids = {wallet.id for wallet in target_wallets}
        else:
            wallet_ids = {wallet.id for wallet in self._finance_service.load_wallets()}

        self._ensure_wallets_exist(parsed_records, raw_transfer_ops, wallet_ids)
        records, transfers, counters = self._build_import_operations(
            parsed_records=parsed_records,
            transfer_rows=raw_transfer_ops,
            counters=ImportCounters(wallets=imported_wallets),
        )
        mandatory_templates = self._normalize_mandatory_templates(parsed_mandatory_templates)
        self._finance_service.replace_all_for_import(
            wallets=target_wallets,
            initial_balance=initial_balance,
            records=records,
            transfers=transfers,
            mandatory_templates=mandatory_templates,
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
            goals=goals
            if flags.can_replace_goals and capabilities.supports_goals_replace
            else None,
            preserve_existing_mandatory=not bool(target_wallets),
        )
        self._replace_distribution_structure_if_supported(
            parsed.file_type,
            distribution_items,
            distribution_subitems_by_item,
            capabilities=capabilities,
            enabled=flags.can_replace_distribution_structure,
        )
        self._replace_budgets_if_supported(
            parsed.file_type,
            budgets,
            capabilities=capabilities,
            enabled=flags.can_replace_budgets,
        )
        self._replace_distribution_snapshots_if_supported(
            parsed.file_type,
            frozen_distribution_rows,
            capabilities=capabilities,
            enabled=flags.can_replace_distribution_snapshots,
        )
        self._finance_service.normalize_operation_ids_for_import()
        logger.info(
            "Import completed (bulk) file=%s wallets=%s records=%s transfers=%s",
            parsed.path,
            counters.wallets,
            counters.records,
            counters.transfers,
        )
        return ImportResult(imported=imported, skipped=skipped, errors=errors)

    def _commit_incremental_prepared_records_payload(
        self,
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
    ) -> ImportResult:
        if wallets:
            self._finance_service.reset_all_for_import(
                wallets=wallets, initial_balance=initial_balance
            )
            wallet_ids = {wallet.id for wallet in wallets}
        else:
            self._finance_service.reset_operations_for_import(initial_balance=initial_balance)
            wallet_ids = {wallet.id for wallet in self._finance_service.load_wallets()}

        self._ensure_wallets_exist(parsed_records, raw_transfer_ops, wallet_ids)
        counters = ImportCounters(wallets=imported_wallets)
        counters = self._apply_operations_with_relaxed_wallet_limits(
            parsed_records=parsed_records,
            transfer_rows=raw_transfer_ops,
            counters=counters,
        )
        self._apply_mandatory_templates(parsed_mandatory_templates)
        self._replace_assets_if_supported(
            parsed.file_type,
            assets,
            asset_snapshots,
            capabilities=capabilities,
            enabled=flags.can_replace_assets,
        )
        self._replace_goals_if_supported(
            parsed.file_type,
            goals,
            capabilities=capabilities,
            enabled=flags.can_replace_goals,
        )
        self._replace_distribution_structure_if_supported(
            parsed.file_type,
            distribution_items,
            distribution_subitems_by_item,
            capabilities=capabilities,
            enabled=flags.can_replace_distribution_structure,
        )
        self._replace_budgets_if_supported(
            parsed.file_type,
            budgets,
            capabilities=capabilities,
            enabled=flags.can_replace_budgets,
        )
        self._replace_distribution_snapshots_if_supported(
            parsed.file_type,
            frozen_distribution_rows,
            capabilities=capabilities,  # type: ignore
            enabled=flags.can_replace_distribution_snapshots,
        )
        logger.info(
            "Import completed file=%s wallets=%s records=%s transfers=%s",
            parsed.path,
            counters.wallets,
            counters.records,
            counters.transfers,
        )
        self._finance_service.normalize_operation_ids_for_import()
        return ImportResult(imported=imported, skipped=skipped, errors=errors)

    def _replace_distribution_snapshots_if_supported(
        self,
        file_type: str,
        rows: list[FrozenDistributionRow],
        *,
        capabilities: ImportCapabilities,
        enabled: bool = True,
    ) -> None:
        if (
            file_type != "json"
            or not enabled
            or not capabilities.supports_distribution_snapshots_replace
        ):
            return
        self._finance_service.replace_distribution_snapshots(rows)

    def _replace_assets_if_supported(
        self,
        file_type: str,
        assets: list[Asset],
        snapshots: list[AssetSnapshot],
        *,
        capabilities: ImportCapabilities,
        enabled: bool = True,
    ) -> None:
        if file_type != "json" or not enabled or not capabilities.supports_assets_replace:
            return
        self._finance_service.replace_assets(assets, snapshots)

    def _replace_goals_if_supported(
        self,
        file_type: str,
        goals: list[Goal],
        *,
        capabilities: ImportCapabilities,
        enabled: bool = True,
    ) -> None:
        if file_type != "json" or not enabled or not capabilities.supports_goals_replace:
            return
        self._finance_service.replace_goals(goals)

    def _replace_budgets_if_supported(
        self,
        file_type: str,
        budgets: list[Budget],
        *,
        capabilities: ImportCapabilities,
        enabled: bool = True,
    ) -> None:
        if file_type != "json" or not enabled or not capabilities.supports_budgets_replace:
            return
        self._finance_service.replace_budgets(budgets)

    def _replace_distribution_structure_if_supported(
        self,
        file_type: str,
        items: list[DistributionItem],
        subitems_by_item: dict[int, list[DistributionSubitem]],
        *,
        capabilities: ImportCapabilities,
        enabled: bool = True,
    ) -> None:
        if (
            file_type != "json"
            or not enabled
            or not capabilities.supports_distribution_structure_replace
        ):
            return
        self._finance_service.replace_distribution_structure(items, subitems_by_item)

    @staticmethod
    def _section_present_or_payload_nonempty(
        section_keys: set[str],
        *,
        required_keys: tuple[str, ...],
        payloads: tuple[Any, ...],
    ) -> bool:
        if all(key in section_keys for key in required_keys):
            return True
        for payload in payloads:
            if isinstance(payload, dict):
                if payload:
                    return True
                continue
            if isinstance(payload, (list, tuple, set)):
                if len(payload) > 0:
                    return True
        return False

    @staticmethod
    def _resolve_json_section_keys(
        *,
        parsed: ParsedImportData,
        debts: list[Debt],
        debt_payments: list[DebtPayment],
        assets: list[Asset],
        asset_snapshots: list[AssetSnapshot],
        goals: list[Goal],
        budgets: list[Budget],
        distribution_items: list[DistributionItem],
        distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
        frozen_distribution_rows: list[FrozenDistributionRow],
    ) -> tuple[set[str], bool]:
        if parsed.file_type != "json":
            return set(), False

        section_keys = {str(key) for key in parsed.json_sections_present}
        if section_keys:
            return section_keys, False

        fallback_sections: set[str] = set()
        if parsed.wallets:
            fallback_sections.add("wallets")
        if parsed.rows:
            fallback_sections.add("records")
        if parsed.debts or debts:
            fallback_sections.add("debts")
        if parsed.debt_payments or debt_payments:
            fallback_sections.add("debt_payments")
        if parsed.assets or assets:
            fallback_sections.add("assets")
        if parsed.asset_snapshots or asset_snapshots:
            fallback_sections.add("asset_snapshots")
        if parsed.goals or goals:
            fallback_sections.add("goals")
        if parsed.budgets or budgets:
            fallback_sections.add("budgets")
        if parsed.distribution_items or distribution_items:
            fallback_sections.add("distribution_items")
        if parsed.distribution_subitems or distribution_subitems_by_item:
            fallback_sections.add("distribution_subitems")
        if parsed.distribution_snapshots or frozen_distribution_rows:
            fallback_sections.add("distribution_snapshots")
        return fallback_sections, True

    def _build_import_operations(
        self,
        *,
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
    ) -> tuple[list[Record], list[Transfer], ImportCounters]:
        records: list[Record] = []
        transfers: list[Transfer] = []
        next_record_id = 1
        next_transfer_id = 1
        created_transfer_ids: set[int] = set()
        transfer_records: dict[int, list[Record]] = defaultdict(list)
        for record in parsed_records:
            if record.transfer_id is not None:
                transfer_records[int(record.transfer_id)].append(record)

        for record in parsed_records:
            if record.transfer_id is None:
                records.append(replace(record, id=next_record_id, transfer_id=None))
                next_record_id += 1
                continue
            transfer_id = int(record.transfer_id)
            if transfer_id in created_transfer_ids:
                continue
            source, target = self._split_transfer_pair(
                transfer_records.get(transfer_id, []),
                label=f"#{transfer_id}",
            )
            transfer = Transfer(
                id=next_transfer_id,
                from_wallet_id=int(source.wallet_id),
                to_wallet_id=int(target.wallet_id),
                date=str(source.date),
                amount_original=to_money_float(source.amount_original or 0.0),
                currency=str(source.currency).upper(),
                rate_at_operation=to_rate_float(source.rate_at_operation),
                amount_kzt=to_money_float(source.amount_kzt or 0.0),
                description=str(source.description or ""),
            )
            transfers.append(transfer)
            records.append(
                ExpenseRecord(
                    id=next_record_id,
                    date=str(source.date),
                    wallet_id=int(source.wallet_id),
                    transfer_id=int(transfer.id),
                    amount_original=to_money_float(source.amount_original or 0.0),
                    currency=str(source.currency).upper(),
                    rate_at_operation=to_rate_float(source.rate_at_operation),
                    amount_kzt=to_money_float(source.amount_kzt or 0.0),
                    category="Transfer",
                )
            )
            next_record_id += 1
            records.append(
                IncomeRecord(
                    id=next_record_id,
                    date=str(source.date),
                    wallet_id=int(target.wallet_id),
                    transfer_id=int(transfer.id),
                    amount_original=to_money_float(source.amount_original or 0.0),
                    currency=str(source.currency).upper(),
                    rate_at_operation=to_rate_float(source.rate_at_operation),
                    amount_kzt=to_money_float(source.amount_kzt or 0.0),
                    category="Transfer",
                )
            )
            next_record_id += 1
            next_transfer_id += 1
            created_transfer_ids.add(transfer_id)

        grouped_ids = {
            int(record.transfer_id)
            for record in parsed_records
            if isinstance(record.transfer_id, int) and record.transfer_id > 0
        }
        transfers_count = counters.transfers + len(created_transfer_ids)
        for transfer_row in transfer_rows:
            if int(transfer_row["transfer_id"]) in grouped_ids:
                continue
            transfer = Transfer(
                id=next_transfer_id,
                from_wallet_id=int(transfer_row["from_wallet_id"]),
                to_wallet_id=int(transfer_row["to_wallet_id"]),
                date=str(transfer_row["transfer_date"]),
                amount_original=to_money_float(transfer_row["amount"]),
                currency=str(transfer_row["currency"]).upper(),
                rate_at_operation=to_rate_float(transfer_row["rate_at_operation"]),
                amount_kzt=to_money_float(transfer_row["amount_kzt"]),
                description=str(transfer_row.get("description", "")),
            )
            transfers.append(transfer)
            records.append(
                ExpenseRecord(
                    id=next_record_id,
                    date=str(transfer.date),
                    wallet_id=int(transfer.from_wallet_id),
                    transfer_id=int(transfer.id),
                    amount_original=to_money_float(transfer.amount_original),
                    currency=str(transfer.currency).upper(),
                    rate_at_operation=to_rate_float(transfer.rate_at_operation),
                    amount_kzt=to_money_float(transfer.amount_kzt),
                    category="Transfer",
                )
            )
            next_record_id += 1
            records.append(
                IncomeRecord(
                    id=next_record_id,
                    date=str(transfer.date),
                    wallet_id=int(transfer.to_wallet_id),
                    transfer_id=int(transfer.id),
                    amount_original=to_money_float(transfer.amount_original),
                    currency=str(transfer.currency).upper(),
                    rate_at_operation=to_rate_float(transfer.rate_at_operation),
                    amount_kzt=to_money_float(transfer.amount_kzt),
                    category="Transfer",
                )
            )
            next_record_id += 1
            next_transfer_id += 1
            transfers_count += 1

        return (
            records,
            transfers,
            ImportCounters(
                wallets=counters.wallets,
                records=len(records),
                transfers=transfers_count,
            ),
        )

    def _normalize_mandatory_templates(
        self, templates: list[MandatoryExpenseRecord]
    ) -> list[MandatoryExpenseRecord]:
        normalized: list[MandatoryExpenseRecord] = []
        for index, template in enumerate(templates, start=1):
            description = self._normalize_mandatory_description(
                str(template.description or ""),
                str(template.category),
            )
            normalized.append(
                MandatoryExpenseRecord(
                    id=index,
                    wallet_id=int(template.wallet_id),
                    date=str(template.date or ""),
                    amount_original=to_money_float(template.amount_original or 0.0),
                    currency=str(template.currency).upper(),
                    rate_at_operation=to_rate_float(template.rate_at_operation),
                    amount_kzt=to_money_float(template.amount_kzt or 0.0),
                    category=str(template.category),
                    description=description,
                    period=str(template.period),  # type: ignore[arg-type]
                    auto_pay=bool(str(template.date or "").strip()),
                )
            )
        return normalized

    def _frozen_rows_from_payload(
        self,
        payloads: list[dict[str, Any]],
        *,
        strict: bool = False,
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

    def _budgets_from_payload(
        self,
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

    def _distribution_structure_from_payload(
        self,
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

    @staticmethod
    def _assets_from_payload(
        raw_assets: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> list[Asset]:
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

    @staticmethod
    def _asset_snapshots_from_payload(
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

    @staticmethod
    def _goals_from_payload(
        raw_goals: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> list[Goal]:
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

    @staticmethod
    def _debts_from_payload(raw_debts: list[dict[str, Any]], *, strict: bool = False) -> list[Debt]:
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

    @staticmethod
    def _debt_payments_from_payload(
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
                    raise ValueError(
                        f"Debt payment #{payment_id} references missing debt_id={debt_id}"
                    )
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

    def _resolve_allowed_debt_ids_for_record_links(
        self,
        *,
        parsed: ParsedImportData,
        imported_debts: list[Debt],
    ) -> set[int] | None:
        if parsed.file_type == "json" and "debts" in set(parsed.json_sections_present):
            return {int(debt.id) for debt in imported_debts}

        capabilities = self._finance_service.get_import_capabilities()
        if capabilities.supports_load_debts:
            debts = self._finance_service.load_debts()
            if isinstance(debts, Iterable):
                return {int(debt.id) for debt in debts}

        # When debt source is unavailable, keep links unchanged instead of
        # destructive clearing on records-only imports.
        return None

    @staticmethod
    def _normalize_record_debt_links(
        records: list[Record],
        *,
        allowed_debt_ids: set[int] | None,
        strict: bool = False,
    ) -> list[Record]:
        if allowed_debt_ids is None:
            return list(records)
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

    def _apply_operations_with_relaxed_wallet_limits(
        self,
        *,
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
    ) -> ImportCounters:
        wallet_ids: set[int] = set()
        for record in parsed_records:
            wallet_ids.add(int(record.wallet_id))
        for transfer in transfer_rows:
            wallet_ids.add(int(transfer["from_wallet_id"]))
            wallet_ids.add(int(transfer["to_wallet_id"]))

        wallets = {wallet.id: wallet for wallet in self._finance_service.load_wallets()}
        changed_wallet_ids: set[int] = set()
        for wallet_id in sorted(wallet_ids):
            wallet = wallets.get(wallet_id)
            if wallet is None or wallet.allow_negative:
                continue
            self._finance_service.set_wallet_allow_negative_for_import(wallet_id, True)
            changed_wallet_ids.add(wallet_id)

        try:
            result = self._apply_records(parsed_records, counters)
            result = self._apply_grouped_transfers(parsed_records, result)
            result = self._apply_transfer_rows(transfer_rows, result, parsed_records)
            return result
        finally:
            for wallet_id in sorted(changed_wallet_ids):
                self._finance_service.set_wallet_allow_negative_for_import(wallet_id, False)

    def _apply_mandatory_templates(self, templates: list[MandatoryExpenseRecord]) -> None:
        wallet_ids = {int(wallet.id) for wallet in self._finance_service.load_wallets()}
        for template in templates:
            if int(template.wallet_id) not in wallet_ids:
                raise ValueError(
                    f"Mandatory template references missing wallet: {template.wallet_id}"
                )
            description = self._normalize_mandatory_description(
                str(template.description or ""),
                str(template.category),
            )
            self._finance_service.create_mandatory_expense(
                amount=to_money_float(template.amount_original or 0.0),
                currency=str(template.currency).upper(),
                wallet_id=int(template.wallet_id),
                category=str(template.category),
                description=description,
                period=str(template.period),
                date=str(template.date or ""),
                amount_kzt=self._fixed_amount_kzt(template.amount_kzt),
                rate_at_operation=self._fixed_rate(template.rate_at_operation),
            )

    def _import_mandatory_payload(self, parsed: ParsedImportData) -> ImportResult:
        source_rows = parsed.mandatory_rows if parsed.file_type == "json" else parsed.rows
        self._finance_service.reset_mandatory_for_import()
        get_rate = (
            self._finance_service.get_currency_rate
            if self._policy == ImportPolicy.CURRENT_RATE
            else None
        )
        wallet_ids = {int(wallet.id) for wallet in self._finance_service.load_wallets()}

        imported = 0
        skipped = 0
        errors: list[str] = []
        for index, row in enumerate(source_rows, start=2):
            record, _, error = parse_import_row(
                row,
                row_label=f"row {index}",
                policy=self._policy,
                get_rate=get_rate,
                mandatory_only=True,
            )
            if error:
                skipped += 1
                errors.append(error)
                continue
            if not isinstance(record, MandatoryExpenseRecord):
                skipped += 1
                errors.append(f"row {index}: expected mandatory expense")
                continue
            if int(record.wallet_id) not in wallet_ids:
                skipped += 1
                errors.append(f"row {index}: wallet not found ({int(record.wallet_id)})")
                continue
            description = self._normalize_mandatory_description(
                str(record.description or ""),
                str(record.category),
            )
            self._finance_service.create_mandatory_expense(
                amount=to_money_float(record.amount_original or 0.0),
                currency=str(record.currency).upper(),
                wallet_id=int(record.wallet_id),
                category=str(record.category),
                description=description,
                period=str(record.period),
                date=str(record.date or ""),
                amount_kzt=self._fixed_amount_kzt(record.amount_kzt),
                rate_at_operation=self._fixed_rate(record.rate_at_operation),
            )
            imported += 1
        logger.info(
            "Mandatory import completed file=%s wallets=0 records=0 transfers=0 templates=%s",
            parsed.path,
            imported,
        )
        return ImportResult(imported=imported, skipped=skipped, errors=tuple(errors))

    def _apply_records(
        self, parsed_records: list[Record], counters: ImportCounters
    ) -> ImportCounters:
        records_count = counters.records
        created_transfer_ids: set[int] = set()
        transfer_records: dict[int, list[Record]] = defaultdict(list)
        for record in parsed_records:
            if record.transfer_id is not None:
                transfer_records[int(record.transfer_id)].append(record)

        transfers_count = counters.transfers
        for record in parsed_records:
            if record.transfer_id is not None:
                transfer_id = int(record.transfer_id)
                if transfer_id in created_transfer_ids:
                    continue
                source, target = self._split_transfer_pair(
                    transfer_records.get(transfer_id, []),
                    label=f"#{transfer_id}",
                )
                self._finance_service.create_transfer(
                    from_wallet_id=int(source.wallet_id),
                    to_wallet_id=int(target.wallet_id),
                    transfer_date=str(source.date),
                    amount=to_money_float(source.amount_original or 0.0),
                    currency=str(source.currency).upper(),
                    description=str(source.description or ""),
                    amount_kzt=self._fixed_amount_kzt(source.amount_kzt),
                    rate_at_operation=self._fixed_rate(source.rate_at_operation),
                )
                created_transfer_ids.add(transfer_id)
                records_count += 2
                transfers_count += 1
                continue
            if isinstance(record, IncomeRecord):
                create_income_payload: dict[str, Any] = {
                    "date": str(record.date),
                    "wallet_id": int(record.wallet_id),
                    "amount": to_money_float(record.amount_original or 0.0),
                    "currency": str(record.currency).upper(),
                    "category": str(record.category),
                    "description": str(record.description or ""),
                    "amount_kzt": self._fixed_amount_kzt(record.amount_kzt),
                    "rate_at_operation": self._fixed_rate(record.rate_at_operation),
                }
                record_tags = tuple(getattr(record, "tags", ()) or ())
                if record_tags:
                    create_income_payload["tags"] = record_tags
                if record.related_debt_id is not None:
                    create_income_payload["related_debt_id"] = int(record.related_debt_id)
                self._finance_service.create_income(
                    **create_income_payload,
                )
                records_count += 1
                continue
            if isinstance(record, MandatoryExpenseRecord):
                description = self._normalize_mandatory_description(
                    str(record.description or ""),
                    str(record.category),
                )
                self._finance_service.create_mandatory_expense_record(
                    date=str(record.date),
                    wallet_id=int(record.wallet_id),
                    amount=to_money_float(record.amount_original or 0.0),
                    currency=str(record.currency).upper(),
                    category=str(record.category),
                    description=description,
                    period=str(record.period),
                    amount_kzt=self._fixed_amount_kzt(record.amount_kzt),
                    rate_at_operation=self._fixed_rate(record.rate_at_operation),
                )
                records_count += 1
                continue
            create_expense_payload: dict[str, Any] = {
                "date": str(record.date),
                "wallet_id": int(record.wallet_id),
                "amount": to_money_float(record.amount_original or 0.0),
                "currency": str(record.currency).upper(),
                "category": str(record.category),
                "description": str(record.description or ""),
                "amount_kzt": self._fixed_amount_kzt(record.amount_kzt),
                "rate_at_operation": self._fixed_rate(record.rate_at_operation),
            }
            record_tags = tuple(getattr(record, "tags", ()) or ())
            if record_tags:
                create_expense_payload["tags"] = record_tags
            if record.related_debt_id is not None:
                create_expense_payload["related_debt_id"] = int(record.related_debt_id)
            self._finance_service.create_expense(**create_expense_payload)
            records_count += 1
        return ImportCounters(
            wallets=counters.wallets,
            records=records_count,
            transfers=transfers_count,
        )

    def _apply_grouped_transfers(
        self,
        parsed_records: list[Record],
        counters: ImportCounters,
    ) -> ImportCounters:
        return counters

    def _apply_transfer_rows(
        self,
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
        parsed_records: list[Record],
    ) -> ImportCounters:
        transfers_count = counters.transfers
        grouped_ids = {
            int(record.transfer_id)
            for record in parsed_records
            if isinstance(record.transfer_id, int) and record.transfer_id > 0
        }
        for transfer in transfer_rows:
            if int(transfer["transfer_id"]) in grouped_ids:
                continue
            self._finance_service.create_transfer(
                from_wallet_id=int(transfer["from_wallet_id"]),
                to_wallet_id=int(transfer["to_wallet_id"]),
                transfer_date=str(transfer["transfer_date"]),
                amount=to_money_float(transfer["amount"]),
                currency=str(transfer["currency"]).upper(),
                description=str(transfer.get("description", "")),
                amount_kzt=self._fixed_amount_kzt(to_money_float(transfer["amount_kzt"])),
                rate_at_operation=self._fixed_rate(to_rate_float(transfer["rate_at_operation"])),
            )
            transfers_count += 1
        return ImportCounters(
            wallets=counters.wallets,
            records=counters.records,
            transfers=transfers_count,
        )

    @staticmethod
    def _ensure_wallets_exist(
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

    @staticmethod
    def _wallets_from_payload(raw_wallets: list[dict[str, Any]]) -> list[Wallet]:
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
                    initial_balance=to_money_float(
                        as_float(item.get("initial_balance"), 0.0) or 0.0
                    ),
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

    @staticmethod
    def _normalize_wallet_ids(wallets: list[Wallet]) -> tuple[list[Wallet], dict[int, int]]:
        normalized: list[Wallet] = []
        wallet_id_map: dict[int, int] = {}
        for new_id, wallet in enumerate(sorted(wallets, key=lambda item: int(item.id)), start=1):
            wallet_id_map[int(wallet.id)] = new_id
            normalized.append(
                replace(
                    wallet,
                    id=new_id,
                    system=bool(wallet.system) or new_id == 1,
                )
            )
        if normalized and not any(wallet.system for wallet in normalized):
            normalized[0] = replace(normalized[0], system=True)
        return normalized, wallet_id_map

    @classmethod
    def _remap_parsed_wallet_ids(
        cls,
        parsed: ParsedImportData,
        wallet_id_map: dict[int, int],
    ) -> ParsedImportData:
        rows = [
            cls._remap_wallet_ids_in_row(
                row,
                wallet_id_map,
                fields=("wallet_id", "from_wallet_id", "to_wallet_id"),
            )
            for row in parsed.rows
        ]
        mandatory_rows = [
            cls._remap_wallet_ids_in_row(row, wallet_id_map, fields=("wallet_id",))
            for row in parsed.mandatory_rows
        ]
        wallets = [
            cls._remap_wallet_ids_in_row(wallet, wallet_id_map, fields=("id",))
            for wallet in parsed.wallets
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

    @staticmethod
    def _remap_wallet_ids_in_row(
        row: dict[str, Any],
        wallet_id_map: dict[int, int],
        *,
        fields: tuple[str, ...],
    ) -> dict[str, Any]:
        remapped = dict(row)
        for field in fields:
            value = remapped.get(field)
            mapped = ImportService._map_wallet_id(value, wallet_id_map)
            if mapped is not None:
                remapped[field] = mapped
        return remapped

    @staticmethod
    def _map_wallet_id(value: Any, wallet_id_map: dict[int, int]) -> int | None:
        wallet_id = parse_optional_strict_int(value)
        if value not in (None, "") and wallet_id is None:
            raise ValueError(f"Invalid wallet id in import payload: {value}")
        wallet_id = wallet_id or 0
        if wallet_id <= 0:
            return None
        return wallet_id_map.get(wallet_id, wallet_id)

    @staticmethod
    def _build_error(errors: list[str]) -> str:
        details = "; ".join(errors[:3])
        if len(errors) > 3:
            details += f"; ... and {len(errors) - 3} more"
        return f"Import aborted: {len(errors)} invalid rows ({details})"

    @staticmethod
    def _normalize_mandatory_description(description: str, category: str) -> str:
        normalized = description.strip()
        if normalized:
            return normalized
        category_name = (category or "").strip()
        if category_name:
            return f"Imported {category_name}"
        return "Imported mandatory expense"

    def _fixed_amount_kzt(self, amount_kzt: float | None) -> float | None:
        if self._policy == ImportPolicy.CURRENT_RATE:
            return None
        if amount_kzt is None:
            return None
        return to_money_float(amount_kzt)

    def _fixed_rate(self, rate_at_operation: float | None) -> float | None:
        if self._policy == ImportPolicy.CURRENT_RATE:
            return None
        if rate_at_operation is None:
            return None
        return to_rate_float(rate_at_operation)

    @staticmethod
    def _split_transfer_pair(
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
        if source.wallet_id == target.wallet_id:
            raise ValueError(f"Transfer integrity violated for {label}: wallets must be different")
        if str(source.date) != str(target.date):
            raise ValueError(f"Transfer integrity violated for {label}: date mismatch")
        if str(source.currency).upper() != str(target.currency).upper():
            raise ValueError(f"Transfer integrity violated for {label}: currency mismatch")
        source_amount = to_money_float(source.amount_original or 0.0)
        target_amount = to_money_float(target.amount_original or 0.0)
        if abs(source_amount - target_amount) > 1e-9:
            raise ValueError(f"Transfer integrity violated for {label}: amount_original mismatch")
        return source, target
