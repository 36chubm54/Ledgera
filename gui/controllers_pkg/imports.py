from __future__ import annotations

import logging
import pathlib
from typing import Any

from app.importing.support import normalize_operation_ids_for_import, run_import_transaction
from domain.asset import Asset, AssetSnapshot
from domain.debt import Debt, DebtPayment
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import MandatoryExpenseRecord, Record
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from gui.controllers_pkg.support import wallets_with_system_initial_balance
from services.support.app_update import is_newer_app_version, is_same_or_newer_app_version
from utils.finance.money import to_money_float


class ControllerImportFacade:
    def __init__(
        self,
        *,
        repository: Any,
        currency: Any,
        ui_preferences: Any,
        app_update: Any,
        logger: logging.Logger,
    ) -> None:
        self._repository = repository
        self._currency = currency
        self._ui_preferences = ui_preferences
        self._app_update = app_update
        self._logger = logger

    def mark_pending_update_cleanup(self, *, artifact_path: str, target_version: str) -> None:
        from domain.update import PendingUpdateCleanupState

        self._ui_preferences.save_pending_update_cleanup_state(
            PendingUpdateCleanupState(
                artifact_path=pathlib.Path(artifact_path),
                target_version=target_version,
            )
        )

    def reconcile_pending_update_state(self) -> None:
        current_version = self._app_update.get_current_version()

        cleanup_state = self._ui_preferences.load_pending_update_cleanup_state()
        if cleanup_state is not None:
            if is_same_or_newer_app_version(current_version, cleanup_state.target_version):
                try:
                    cleanup_state.artifact_path.unlink(missing_ok=True)
                except OSError:
                    self._logger.exception(
                        "Failed to remove installed update artifact: %s",
                        cleanup_state.artifact_path,
                    )
                finally:
                    self._ui_preferences.clear_pending_update_cleanup_state()

        install_state = self._ui_preferences.load_pending_update_install_state()
        if install_state is None:
            return
        if not install_state.artifact_path.is_file() or not is_newer_app_version(
            current_version,
            install_state.version,
        ):
            self._ui_preferences.clear_pending_update_install_state()

    def reset_operations_for_import(self, *, initial_balance: float) -> None:
        self._repository.replace_records_and_transfers([], [])
        self._repository.save_initial_balance(to_money_float(initial_balance))

    def reset_mandatory_for_import(self) -> None:
        self._repository.delete_all_mandatory_expenses()

    def reset_all_for_import(self, *, wallets: list[Wallet], initial_balance: float) -> None:
        self._repository.replace_all_data(
            wallets=wallets,
            records=[],
            mandatory_expenses=[],
            transfers=[],
        )
        self._repository.save_initial_balance(to_money_float(initial_balance))

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
        goals: list[Any] | None = None,
        preserve_existing_mandatory: bool,
        replace_assets: Any,
        replace_goals: Any,
    ) -> None:
        target_wallets = list(wallets) if wallets else list(self._repository.load_wallets())
        target_wallets = wallets_with_system_initial_balance(
            target_wallets, to_money_float(initial_balance)
        )

        mandatory_payload: list[MandatoryExpenseRecord] = []
        if preserve_existing_mandatory:
            mandatory_payload.extend(self._repository.load_mandatory_expenses())
        mandatory_payload.extend(mandatory_templates)

        if debts is None or debt_payments is None:
            debt_payload = list(self._repository.load_debts())
            debt_payment_payload = list(self._repository.load_debt_payments())
        else:
            debt_payload = list(debts)
            debt_payment_payload = list(debt_payments)

        self._repository.replace_all_data(
            wallets=target_wallets,
            records=records,
            mandatory_expenses=mandatory_payload,
            tags=tags,
            transfers=transfers,
            debts=debt_payload,
            debt_payments=debt_payment_payload,
        )
        if assets is not None or asset_snapshots is not None:
            replace_assets(list(assets or []), list(asset_snapshots or []))
        if goals is not None:
            replace_goals(list(goals or []))

    @staticmethod
    def get_import_capabilities() -> Any:
        from app.importing.finance import ImportCapabilities

        return ImportCapabilities(
            supports_bulk_replace=True,
            supports_distribution_snapshots_replace=True,
            supports_assets_replace=True,
            supports_goals_replace=True,
            supports_budgets_replace=True,
            supports_distribution_structure_replace=True,
            supports_load_debts=True,
            supports_tags_replace=True,
        )

    def run_import_transaction(self, operation: Any) -> Any:
        return run_import_transaction(self._repository, operation, self._logger)

    def normalize_operation_ids_for_import(self) -> None:
        normalize_operation_ids_for_import(self._repository)

    def import_records(
        self,
        *,
        fmt: str,
        filepath: str,
        policy: ImportPolicy,
        force: bool = False,
        dry_run: bool = False,
        finance_service: Any,
    ) -> ImportResult:
        if fmt not in {"CSV", "XLSX", "JSON"}:
            raise ValueError(f"Unsupported format: {fmt}")
        from services.import_service import ImportService

        return ImportService(finance_service, policy=policy).import_file(
            filepath,
            force=force,
            dry_run=dry_run,
        )

    def import_mandatory(self, *, fmt: str, filepath: str, finance_service: Any) -> ImportResult:
        if fmt not in {"CSV", "XLSX", "JSON"}:
            raise ValueError(f"Unsupported format: {fmt}")
        from services.import_service import ImportService

        return ImportService(
            finance_service, policy=ImportPolicy.FULL_BACKUP
        ).import_mandatory_file(filepath)
