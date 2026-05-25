from __future__ import annotations

from typing import Any

from app.runtime.preferences import OnlineStatusSnapshot
from domain.update import (
    AppUpdateCheckResult,
    AppUpdateDownloadResult,
    AppUpdateReleaseInfo,
    PendingUpdateInstallState,
)


class ControllerRuntimeMixin:
    _currency: Any
    _app_update: Any
    _ui_preferences: Any
    _imports: Any

    def get_currency_rate(self, currency: str) -> float:
        return float(self._currency.get_rate(currency))

    def get_display_currency(self) -> str:
        return self._currency.display_currency

    def get_display_currency_code(self) -> str:
        return self._currency.display_currency

    def get_base_currency_code(self) -> str:
        return self._currency.base_currency

    def get_display_symbol(self) -> str:
        return self._currency.display_symbol

    def get_available_display_currencies(self) -> list[str]:
        return self._currency.get_available_display_currencies()

    def get_runtime_currency_config(self) -> dict[str, object]:
        return self._currency.get_runtime_currency_config()

    def get_supported_currency_provider_names(self) -> list[str]:
        return self._currency.get_supported_provider_names()

    def get_runtime_security_diagnostics(self) -> dict[str, object]:
        return self._currency.get_runtime_security_diagnostics()

    def set_display_currency(self, code: str) -> None:
        self._currency.set_display_currency(code)

    def refresh_currency_rates(self) -> bool:
        return self._currency.refresh_rates()

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
    ) -> None:
        self._currency.update_runtime_currency_config(
            display_currency=display_currency,
            provider_mode=provider_mode,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            exchange_rate_api_key=exchange_rate_api_key,
            auto_update=auto_update,
            update_interval_minutes=update_interval_minutes,
        )

    def to_display_amount(self, amount_base: float) -> float:
        return float(self._currency.to_display(amount_base))

    def format_display_amount(self, amount_base: float, precision: int = 2) -> str:
        value = self.to_display_amount(amount_base)
        return f"{value:,.{precision}f}"

    def format_display_money(
        self,
        amount_base: float,
        *,
        precision: int = 2,
        with_code: bool = True,
    ) -> str:
        amount = self.format_display_amount(amount_base, precision=precision)
        if not with_code:
            return amount
        return f"{amount} {self.get_display_currency_code()}"

    def set_online_mode(self, enabled: bool) -> None:
        self._ui_preferences.set_online_mode(enabled)

    def save_language_preference(self, code: str) -> None:
        self._ui_preferences.save_language_preference(code)

    def load_language_preference(self) -> str | None:
        return self._ui_preferences.load_language_preference()

    def save_theme_preference(self, name: str) -> None:
        self._ui_preferences.save_theme_preference(name)

    def load_theme_preference(self) -> str | None:
        return self._ui_preferences.load_theme_preference()

    def get_online_mode(self) -> bool:
        return self._currency.is_online

    def get_online_status(self) -> OnlineStatusSnapshot:
        return self._ui_preferences.get_online_status_snapshot()

    def load_online_mode_preference(self) -> bool:
        return self._ui_preferences.load_online_mode_preference()

    def save_linux_terminal_preference(self, executable_path: str) -> None:
        self._ui_preferences.save_linux_terminal_preference(executable_path)

    def load_linux_terminal_preference(self) -> str | None:
        return self._ui_preferences.load_linux_terminal_preference()

    def save_pending_update_install_state(self, state: PendingUpdateInstallState) -> None:
        self._ui_preferences.save_pending_update_install_state(state)

    def load_pending_update_install_state(self) -> PendingUpdateInstallState | None:
        return self._ui_preferences.load_pending_update_install_state()

    def clear_pending_update_install_state(self) -> None:
        self._ui_preferences.clear_pending_update_install_state()

    def mark_pending_update_cleanup(self, *, artifact_path: str, target_version: str) -> None:
        self._imports.mark_pending_update_cleanup(
            artifact_path=artifact_path,
            target_version=target_version,
        )

    def reconcile_pending_update_state(self) -> None:
        self._imports.reconcile_pending_update_state()

    def get_app_version(self) -> str:
        return self._app_update.get_current_version()

    def get_app_release_page_url(self) -> str:
        return self._app_update.get_release_page_url()

    def is_app_update_supported(self) -> bool:
        return self._app_update.is_supported_environment()

    def check_for_app_update(self) -> AppUpdateCheckResult:
        return self._app_update.check_for_app_update()

    def download_app_update(
        self,
        release: AppUpdateReleaseInfo,
        *,
        on_progress,
    ) -> AppUpdateDownloadResult:
        return self._app_update.download_app_update(release, on_progress=on_progress)
