from __future__ import annotations

import logging
from typing import Any, cast

from app.importing.finance import FinanceService, ImportCapabilities
from domain.asset import Asset, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtPayment
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import MandatoryExpenseRecord, Record
from domain.transfers import Transfer
from domain.wallets import Wallet
from services.importing.adapters import (
    goals_payload_to_domain,
    tags_from_payload,
)
from services.importing.mandatory_support import import_mandatory_payload
from services.importing.models import ImportCounters, PreparedImportPayload, ReplaceSectionFlags
from services.importing.parser import ParsedImportData, parse_import_file
from services.importing.replace_support import apply_supported_replacements, resolve_replace_flags
from services.importing.service_support import (
    apply_mandatory_templates as apply_import_mandatory_templates,
)
from services.importing.service_support import (
    apply_operations_with_relaxed_wallet_limits as apply_import_operations_with_relaxed_wallet_limits,  # noqa: E501
)
from services.importing.service_support import (
    asset_snapshots_from_payload,
    assets_from_payload,
    budgets_from_payload,
    build_error,
    debt_payments_from_payload,
    debts_from_payload,
    distribution_structure_from_payload,
    ensure_wallets_exist,
    fixed_amount_base,
    fixed_rate,
    frozen_rows_from_payload,
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
from services.importing.service_support import (
    build_import_operations as build_service_import_operations,
)
from services.importing.service_support import (
    normalize_mandatory_templates as normalize_import_mandatory_templates,
)
from services.importing.workflow import commit_prepared_records_payload, prepare_records_payload

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
        return prepare_records_payload(self, parsed)

    def _commit_prepared_records_payload(self, prepared: PreparedImportPayload) -> ImportResult:
        return commit_prepared_records_payload(self, prepared, logger=logger)

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

    _tags_from_payload = staticmethod(tags_from_payload)

    def _build_import_operations(
        self,
        *,
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
    ) -> tuple[list[Record], list[Transfer], ImportCounters]:
        return build_service_import_operations(
            parsed_records=parsed_records,
            transfer_rows=transfer_rows,
            counters=counters,
            split_transfer_pair_fn=lambda linked, label: self._split_transfer_pair(
                linked,
                label=label,
            ),
        )

    def _normalize_mandatory_templates(
        self, templates: list[MandatoryExpenseRecord]
    ) -> list[MandatoryExpenseRecord]:
        return normalize_import_mandatory_templates(
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
        return distribution_structure_from_payload(item_payloads, subitem_payloads, strict=strict)

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
        return goals_payload_to_domain(raw_goals, strict=strict)

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
        return debt_payments_from_payload(raw_payments, debts=debts, records=records, strict=strict)

    def _resolve_allowed_debt_ids_for_record_links(
        self,
        *,
        parsed: ParsedImportData,
        imported_debts: list[Debt],
    ) -> set[int] | None:
        return resolve_allowed_debt_ids_for_record_links(
            parsed=parsed,
            imported_debts=imported_debts,
            finance_service=self._finance_service,
        )

    @staticmethod
    def _normalize_record_debt_links(
        records: list[Record],
        *,
        allowed_debt_ids: set[int] | None,
        strict: bool = False,
    ) -> list[Record]:
        return normalize_record_debt_links(
            records, allowed_debt_ids=allowed_debt_ids, strict=strict
        )

    def _apply_operations_with_relaxed_wallet_limits(
        self,
        *,
        parsed_records: list[Record],
        transfer_rows: list[dict[str, Any]],
        counters: ImportCounters,
    ) -> ImportCounters:
        return apply_import_operations_with_relaxed_wallet_limits(
            self._finance_service,
            parsed_records=parsed_records,
            transfer_rows=transfer_rows,
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
        apply_import_mandatory_templates(
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
        return fixed_amount_base(self._policy, amount_base)

    def _fixed_rate(self, rate_at_operation: float | None) -> float | None:
        return fixed_rate(self._policy, rate_at_operation)

    @staticmethod
    def _split_transfer_pair(
        linked: list[Record],
        *,
        label: str,
    ) -> tuple[Record, Record]:
        return cast(tuple[Record, Record], split_transfer_pair(linked, label=label))
