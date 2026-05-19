"""Public contracts for the settings tab."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from domain.update import AppUpdateCheckResult, AppUpdateDownloadResult, AppUpdateReleaseInfo
from gui.i18n import tr


class SettingsController(Protocol):
    def import_records(self, filepath: str, *, mode: Any, backup: bool) -> Any: ...

    def get_budgets(self) -> list[Any]: ...

    def get_debts(self) -> list[Any]: ...

    def get_debt_history(self, debt_id: int) -> list[Any]: ...

    def get_assets(self, *, active_only: bool = True) -> list[Any]: ...

    def get_asset_history(self, asset_id: int) -> list[Any]: ...

    def get_goals(self) -> list[Any]: ...

    def export_distribution_structure(self) -> list[Any]: ...

    def get_frozen_distribution_rows(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> list[Any]: ...

    def get_runtime_currency_config(self) -> dict[str, Any]: ...

    def get_supported_currency_provider_names(self) -> list[str]: ...

    def get_runtime_security_diagnostics(self) -> dict[str, Any]: ...

    def get_display_currency_code(self) -> str: ...

    def get_available_display_currencies(self) -> list[str]: ...

    def get_app_version(self) -> str: ...

    def get_app_release_page_url(self) -> str: ...

    def is_app_update_supported(self) -> bool: ...

    def check_for_app_update(self) -> AppUpdateCheckResult: ...

    def download_app_update(
        self,
        release: AppUpdateReleaseInfo,
        *,
        on_progress,
    ) -> AppUpdateDownloadResult: ...

    def update_runtime_currency_config(
        self,
        *,
        display_currency: str,
        provider_mode: str,
        primary_provider: str,
        fallback_provider: str,
        exchange_rate_api_key: str,
        auto_update: bool,
        update_interval_minutes: int | str,
    ) -> None: ...

    def run_audit(self) -> Any: ...

    def get_wallet_balances(self) -> list[Any]: ...

    def load_wallets(self) -> list[Any]: ...

    def wallet_balance(self, wallet_id: int) -> float: ...

    def create_wallet(
        self,
        *,
        name: str,
        currency: str,
        initial_balance: float,
        include_in_total: bool,
    ) -> Any: ...

    def soft_delete_wallet(self, wallet_id: int) -> None: ...


class SettingsRepository(Protocol):
    def load_wallets(self) -> list[Any]: ...

    def load_all(self) -> list[Any]: ...

    def load_mandatory_expenses(self) -> list[Any]: ...

    def load_transfers(self) -> list[Any]: ...


class SettingsTabContext(Protocol):
    controller: SettingsController
    repository: SettingsRepository
    refresh_operation_wallet_menu: Callable[[], None] | None
    refresh_transfer_wallet_menus: Callable[[], None] | None
    refresh_wallets: Callable[[], None] | None
    refresh_mandatory: Callable[[], None] | None

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_budgets(self) -> None: ...

    def _refresh_all(self) -> None: ...

    def _launch_installer_and_exit(self, installer_path: str) -> None: ...

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
        block_ui: bool = True,
    ) -> None: ...


@dataclass(slots=True)
class SettingsTabBindings:
    refresh: Callable[[], None]
