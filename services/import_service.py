from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

from app.finance_service import FinanceService, ImportCapabilities
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from services.import_execution_support import (
    TransferRow,
    apply_mandatory_templates,
    apply_operations_with_relaxed_wallet_limits,
    build_import_operations,
    normalize_mandatory_templates,
)
from services.import_mandatory_support import import_mandatory_payload
from services.import_models import ImportCounters, PreparedImportPayload, ReplaceSectionFlags
from services.import_parser import ParsedImportData, parse_import_file, parse_transfer_row
from services.import_payload_support import (
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
from services.import_replace_support import apply_supported_replacements, resolve_replace_flags
from utils.import_core import parse_import_row, safe_type
from utils.money import to_money_float, to_rate_float

logger = logging.getLogger(__name__)


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
        return resolve_replace_flags(
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
            logger=logger,
        )

    def _apply_supported_replacements(
        self,
        *,
        file_type: str,
        budgets: list[Budget],
        assets: list[Asset],
        asset_snapshots: list[AssetSnapshot],
        goals: list[Goal],
        distribution_items: list[DistributionItem],
        distribution_subitems_by_item: dict[int, list[DistributionSubitem]],
        frozen_distribution_rows: list[FrozenDistributionRow],
        capabilities: ImportCapabilities,
        flags: ReplaceSectionFlags,
        include_assets_and_goals: bool = True,
    ) -> None:
        apply_supported_replacements(
            self._finance_service,
            file_type=file_type,
            budgets=budgets,
            assets=assets,
            asset_snapshots=asset_snapshots,
            goals=goals,
            distribution_items=distribution_items,
            distribution_subitems_by_item=distribution_subitems_by_item,
            frozen_distribution_rows=frozen_distribution_rows,
            capabilities=capabilities,
            flags=flags,
            include_assets_and_goals=include_assets_and_goals,
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
            tags=self._tags_from_payload(parsed.tags),
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
        self._apply_supported_replacements(
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
        self._finance_service.normalize_operation_ids_for_import()
        logger.info(
            "Import completed (bulk) file=%s wallets=%s records=%s transfers=%s",
            parsed.path,
            counters.wallets,
            counters.records,
            counters.transfers,
        )
        return ImportResult(imported=imported, skipped=skipped, errors=errors)

    @staticmethod
    def _tags_from_payload(payload: list[dict[str, Any]]) -> list[Tag]:
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
        self._apply_supported_replacements(
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
        self._finance_service.normalize_operation_ids_for_import()
        return ImportResult(imported=imported, skipped=skipped, errors=errors)

    def _build_import_operations(
        self,
        *,
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
    ) -> tuple[list[Record], list[Transfer], ImportCounters]:
        return build_import_operations(
            parsed_records=parsed_records,
            transfer_rows=cast(list[TransferRow], transfer_rows),
            counters=counters,
            split_transfer_pair_fn=lambda linked, label: self._split_transfer_pair(
                linked,
                label=label,
            ),
        )

    def _normalize_mandatory_templates(
        self, templates: list[MandatoryExpenseRecord]
    ) -> list[MandatoryExpenseRecord]:
        return normalize_mandatory_templates(
            templates,
            normalize_description_fn=self._normalize_mandatory_description,
        )

    def _frozen_rows_from_payload(
        self,
        payloads: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> list[FrozenDistributionRow]:
        return frozen_rows_from_payload(payloads, strict=strict, logger=logger)

    def _budgets_from_payload(
        self,
        payloads: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> list[Budget]:
        return budgets_from_payload(payloads, strict=strict)

    def _distribution_structure_from_payload(
        self,
        item_payloads: list[dict[str, Any]],
        subitem_payloads: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> tuple[list[DistributionItem], dict[int, list[DistributionSubitem]]]:
        return distribution_structure_from_payload(
            item_payloads,
            subitem_payloads,
            strict=strict,
        )

    @staticmethod
    def _assets_from_payload(
        raw_assets: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> list[Asset]:
        return assets_from_payload(raw_assets, strict=strict)

    @staticmethod
    def _asset_snapshots_from_payload(
        raw_snapshots: list[dict[str, Any]],
        *,
        assets: list[Asset],
        strict: bool = False,
    ) -> list[AssetSnapshot]:
        return asset_snapshots_from_payload(raw_snapshots, assets=assets, strict=strict)

    @staticmethod
    def _goals_from_payload(
        raw_goals: list[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> list[Goal]:
        return goals_from_payload(raw_goals, strict=strict)

    @staticmethod
    def _debts_from_payload(raw_debts: list[dict[str, Any]], *, strict: bool = False) -> list[Debt]:
        return debts_from_payload(raw_debts, strict=strict)

    @staticmethod
    def _debt_payments_from_payload(
        raw_payments: list[dict[str, Any]],
        *,
        debts: list[Debt],
        records: list[Record],
        strict: bool = False,
    ) -> list[DebtPayment]:
        return debt_payments_from_payload(
            raw_payments,
            debts=debts,
            records=records,
            strict=strict,
        )

    def _resolve_allowed_debt_ids_for_record_links(
        self,
        *,
        parsed: ParsedImportData,
        imported_debts: list[Debt],
    ) -> set[int] | None:
        allowed_ids = resolve_allowed_debt_ids_for_record_links(
            parsed=parsed,
            imported_debts=imported_debts,
        )
        if allowed_ids is not None:
            return allowed_ids

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
        return normalize_record_debt_links(
            records,
            allowed_debt_ids=allowed_debt_ids,
            strict=strict,
        )

    def _apply_operations_with_relaxed_wallet_limits(
        self,
        *,
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
    ) -> ImportCounters:
        return apply_operations_with_relaxed_wallet_limits(
            self._finance_service,
            parsed_records=parsed_records,
            transfer_rows=cast(list[TransferRow], transfer_rows),
            counters=counters,
            fixed_amount_base_fn=self._fixed_amount_base,
            fixed_rate_fn=self._fixed_rate,
            normalize_description_fn=self._normalize_mandatory_description,
            split_transfer_pair_fn=lambda linked, label: self._split_transfer_pair(
                linked,
                label=label,
            ),
        )

    def _apply_mandatory_templates(self, templates: list[MandatoryExpenseRecord]) -> None:
        apply_mandatory_templates(
            self._finance_service,
            templates,
            fixed_amount_base_fn=self._fixed_amount_base,
            fixed_rate_fn=self._fixed_rate,
            normalize_description_fn=self._normalize_mandatory_description,
        )

    def _import_mandatory_payload(self, parsed: ParsedImportData) -> ImportResult:
        return import_mandatory_payload(
            self._finance_service,
            parsed=parsed,
            policy=self._policy,
            fixed_amount_base_fn=self._fixed_amount_base,
            fixed_rate_fn=self._fixed_rate,
            normalize_description_fn=self._normalize_mandatory_description,
            logger=logger,
        )

    @staticmethod
    def _ensure_wallets_exist(
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        wallet_ids: set[int],
    ) -> None:
        ensure_wallets_exist(parsed_records, transfer_rows, wallet_ids)

    @staticmethod
    def _wallets_from_payload(raw_wallets: list[dict[str, Any]]) -> list[Wallet]:
        return wallets_from_payload(raw_wallets)

    @staticmethod
    def _normalize_wallet_ids(wallets: list[Wallet]) -> tuple[list[Wallet], dict[int, int]]:
        return normalize_wallet_ids(wallets)

    @classmethod
    def _remap_parsed_wallet_ids(
        cls,
        parsed: ParsedImportData,
        wallet_id_map: dict[int, int],
    ) -> ParsedImportData:
        return remap_parsed_wallet_ids(parsed, wallet_id_map)

    @staticmethod
    def _remap_wallet_ids_in_row(
        row: dict[str, Any],
        wallet_id_map: dict[int, int],
        *,
        fields: tuple[str, ...],
    ) -> dict[str, Any]:
        return remap_wallet_ids_in_row(row, wallet_id_map, fields=fields)

    @staticmethod
    def _map_wallet_id(value: Any, wallet_id_map: dict[int, int]) -> int | None:
        return map_wallet_id(value, wallet_id_map)

    @staticmethod
    def _build_error(errors: list[str]) -> str:
        return build_error(errors)

    @staticmethod
    def _normalize_mandatory_description(description: str, category: str) -> str:
        return normalize_mandatory_description(description, category)

    def _fixed_amount_base(self, amount_base: float | None) -> float | None:
        if self._policy == ImportPolicy.CURRENT_RATE:
            return None
        if amount_base is None:
            return None
        return to_money_float(amount_base)

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
        return split_transfer_pair(linked, label=label)
