from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from app.importing.finance import ImportCapabilities
from app.runtime.audit import run_repository_audit
from domain.asset import Asset, AssetSnapshot
from domain.audit import AuditReport
from domain.debt import Debt, DebtPayment
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet

if TYPE_CHECKING:
    from domain.goal import Goal


class ControllerImportBridgeMixin:
    _repository: Any
    _imports: Any
    replace_assets: Any
    replace_goals: Any

    def reset_operations_for_import(self, *, initial_balance: float) -> None:
        self._imports.reset_operations_for_import(initial_balance=initial_balance)

    def reset_mandatory_for_import(self) -> None:
        self._imports.reset_mandatory_for_import()

    def reset_all_for_import(self, *, wallets: list[Wallet], initial_balance: float) -> None:
        self._imports.reset_all_for_import(wallets=wallets, initial_balance=initial_balance)

    def replace_all_for_import(
        self,
        *,
        wallets: list[Wallet] | None,
        initial_balance: float,
        records: list[Record],
        transfers: list[Transfer],
        mandatory_templates: list[MandatoryExpenseRecord],
        tags: list[Tag] | None = None,
        debts: list[Debt] | None = None,
        debt_payments: list[DebtPayment] | None = None,
        assets: list[Asset] | None = None,
        asset_snapshots: list[AssetSnapshot] | None = None,
        goals: list[Goal] | None = None,
        preserve_existing_mandatory: bool = False,
    ) -> None:
        self._imports.replace_all_for_import(
            wallets=wallets,
            initial_balance=initial_balance,
            records=records,
            transfers=transfers,
            mandatory_templates=mandatory_templates,
            tags=tags,
            debts=debts,
            debt_payments=debt_payments,
            assets=assets,
            asset_snapshots=asset_snapshots,
            goals=goals,
            preserve_existing_mandatory=preserve_existing_mandatory,
            replace_assets=self.replace_assets,
            replace_goals=self.replace_goals,
        )

    def get_import_capabilities(self) -> ImportCapabilities:
        return cast(ImportCapabilities, self._imports.get_import_capabilities())

    def run_import_transaction(self, operation):
        return self._imports.run_import_transaction(operation)

    def normalize_operation_ids_for_import(self) -> None:
        self._imports.normalize_operation_ids_for_import()

    def import_records(
        self,
        fmt: str,
        filepath: str,
        policy: ImportPolicy,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> ImportResult:
        return self._imports.import_records(
            fmt=fmt,
            filepath=filepath,
            policy=policy,
            force=force,
            dry_run=dry_run,
            finance_service=self,
        )

    def import_mandatory(self, fmt: str, filepath: str) -> ImportResult:
        return self._imports.import_mandatory(
            fmt=fmt,
            filepath=filepath,
            finance_service=self,
        )

    def run_audit(self) -> AuditReport:
        return run_repository_audit(self._repository)
