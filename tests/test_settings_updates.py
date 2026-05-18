from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, cast

from domain.update import (
    AppReleaseAsset,
    AppUpdateCheckResult,
    AppUpdateDownloadProgress,
    AppUpdateDownloadResult,
    AppUpdateReleaseInfo,
)
from gui.tabs.settings.builder import build_settings_tab
from gui.tabs.settings.contracts import SettingsTabContext


def _find_buttons(parent: tk.Misc, text: str) -> list[tk.Button | ttk.Button]:
    found: list[tk.Button | ttk.Button] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, (tk.Button, ttk.Button)):
                try:
                    if child.cget("text") == text:
                        found.append(child)
                except Exception:
                    pass
            _walk(child)

    _walk(parent)
    return found


class _Controller:
    def __init__(self, *, supported: bool = True, packaged_mode: bool = True) -> None:
        self.supported = supported
        self.packaged_mode = packaged_mode
        self.check_calls = 0
        self.download_calls = 0
        self.download_progress: list[AppUpdateDownloadProgress] = []
        self.release = AppUpdateReleaseInfo(
            version="2.0.2",
            tag_name="v2.0.2",
            release_url="https://github.com/36chubm54/FinAccountingApp/releases/tag/v2.0.2",
            asset=AppReleaseAsset(
                name="FinAccountingApp-2.0.2-setup.exe",
                download_url="https://example.invalid/setup.exe",
                size_bytes=4096,
            ),
        )
        self.download_path = Path("C:/Temp/FinAccountingApp-2.0.2-setup.exe")

    def get_base_currency_code(self) -> str:
        return "KZT"

    def get_runtime_currency_config(self) -> dict[str, object]:
        return {
            "base_currency": "KZT",
            "display_currency": "KZT",
            "provider_mode": "personal",
            "primary_provider": "nbk",
            "fallback_provider": "exchange_rate",
            "exchange_rate_api_key": "",
            "exchange_rate_api_key_storage_label": "Windows Credential Manager",
            "auto_update": True,
            "update_interval_minutes": 60,
        }

    def get_runtime_security_diagnostics(self) -> dict[str, object]:
        return {
            "user_data_root": "C:/Users/test/AppData/Local/FinAccountingApp",
            "packaged_mode": self.packaged_mode,
        }

    def get_supported_currency_provider_names(self) -> list[str]:
        return ["nbk", "exchange_rate"]

    def get_display_currency_code(self) -> str:
        return "KZT"

    def get_available_display_currencies(self) -> list[str]:
        return ["EUR", "KZT", "RUB", "USD"]

    def update_runtime_currency_config(self, **kwargs: object) -> None:
        del kwargs

    def run_audit(self) -> object:
        return object()

    def get_wallet_balances(self) -> list[Any]:
        return []

    def load_wallets(self) -> list[Any]:
        return []

    def wallet_balance(self, wallet_id: int) -> float:
        del wallet_id
        return 0.0

    def create_wallet(self, **kwargs: object) -> Any:
        return SimpleNamespace(id=1, name=kwargs["name"])

    def soft_delete_wallet(self, wallet_id: int) -> None:
        del wallet_id

    def import_records(self, filepath: str, *, mode: Any, backup: bool) -> Any:
        del filepath, mode, backup
        return object()

    def get_budgets(self) -> list[Any]:
        return []

    def get_debts(self) -> list[Any]:
        return []

    def get_debt_history(self, debt_id: int) -> list[Any]:
        del debt_id
        return []

    def get_assets(self, *, active_only: bool = True) -> list[Any]:
        del active_only
        return []

    def get_asset_history(self, asset_id: int) -> list[Any]:
        del asset_id
        return []

    def get_goals(self) -> list[Any]:
        return []

    def export_distribution_structure(self) -> tuple[list[Any], dict[int, list[Any]]]:
        return [], {}

    def get_frozen_distribution_rows(
        self, start_month: str | None = None, end_month: str | None = None
    ) -> list[Any]:
        del start_month, end_month
        return []

    def get_app_version(self) -> str:
        return "2.0.1"

    def is_app_update_supported(self) -> bool:
        return self.supported

    def check_for_app_update(self) -> AppUpdateCheckResult:
        self.check_calls += 1
        return AppUpdateCheckResult(
            current_version="2.0.1",
            latest_release=self.release,
            update_available=True,
        )

    def download_app_update(
        self,
        release: AppUpdateReleaseInfo,
        *,
        on_progress,
    ) -> AppUpdateDownloadResult:
        self.download_calls += 1
        assert release == self.release
        snapshot = AppUpdateDownloadProgress(bytes_downloaded=4096, total_bytes=4096)
        self.download_progress.append(snapshot)
        on_progress(snapshot)
        return AppUpdateDownloadResult(release=release, downloaded_path=self.download_path)


def _build_context(controller: _Controller, launches: list[str]) -> SettingsTabContext:
    return cast(
        SettingsTabContext,
        type(
            "Ctx",
            (),
            {
                "controller": controller,
                "repository": SimpleNamespace(
                    load_wallets=lambda: [],
                    load_all=lambda: [],
                    load_mandatory_expenses=lambda: [],
                    load_transfers=lambda: [],
                ),
                "refresh_operation_wallet_menu": None,
                "refresh_transfer_wallet_menus": None,
                "refresh_wallets": None,
                "refresh_mandatory": None,
                "_refresh_list": lambda self: None,
                "_refresh_charts": lambda self: None,
                "_refresh_budgets": lambda self: None,
                "_refresh_all": lambda self: None,
                "_launch_installer_and_exit": lambda self, installer_path: launches.append(
                    installer_path
                ),
                "_run_background": lambda self, task, **kwargs: kwargs.get(
                    "on_success", lambda *_: None
                )(task()),
            },
        )(),
    )


def _build_deferred_context(
    controller: _Controller,
    launches: list[str],
    pending: list[dict[str, Any]],
) -> SettingsTabContext:
    def _run_background(self, task, **kwargs):
        pending.append(
            {
                "task": task,
                "on_success": kwargs.get("on_success"),
                "on_error": kwargs.get("on_error"),
            }
        )

    return cast(
        SettingsTabContext,
        type(
            "Ctx",
            (),
            {
                "controller": controller,
                "repository": SimpleNamespace(
                    load_wallets=lambda: [],
                    load_all=lambda: [],
                    load_mandatory_expenses=lambda: [],
                    load_transfers=lambda: [],
                ),
                "refresh_operation_wallet_menu": None,
                "refresh_transfer_wallet_menus": None,
                "refresh_wallets": None,
                "refresh_mandatory": None,
                "_refresh_list": lambda self: None,
                "_refresh_charts": lambda self: None,
                "_refresh_budgets": lambda self: None,
                "_refresh_all": lambda self: None,
                "_launch_installer_and_exit": lambda self, installer_path: launches.append(
                    installer_path
                ),
                "_run_background": _run_background,
            },
        )(),
    )


def test_settings_tab_disables_update_button_when_not_supported() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        controller = _Controller(supported=False)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        build_settings_tab(
            parent,
            context,
            messagebox_module=SimpleNamespace(),
            wallet_manager_dialog=lambda *args, **kwargs: None,
        )
        root.update_idletasks()

        buttons = _find_buttons(parent, "Проверить обновления")
        assert buttons
        state = getattr(buttons[0], "state", None)
        assert callable(state)
        assert "disabled" in str(state())
    finally:
        root.destroy()


def test_settings_tab_update_flow_downloads_and_launches_installer() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        controller = _Controller(supported=True)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        messagebox_module = SimpleNamespace(
            askyesno=lambda *args, **kwargs: True,
            showerror=lambda *args, **kwargs: None,
            showinfo=lambda *args, **kwargs: None,
        )
        build_settings_tab(
            parent,
            context,
            messagebox_module=messagebox_module,
            wallet_manager_dialog=lambda *args, **kwargs: None,
        )
        root.update()

        buttons = _find_buttons(parent, "Проверить обновления")
        assert buttons
        buttons[0].invoke()
        root.update()

        assert controller.check_calls == 1
        assert controller.download_calls == 1
        assert launches == [str(controller.download_path)]
    finally:
        root.destroy()


def test_settings_tab_source_mode_uses_source_specific_install_prompt() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        controller = _Controller(supported=True, packaged_mode=False)
        launches: list[str] = []
        prompts: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        def _askyesno(_title: str, message: str) -> bool:
            prompts.append(message)
            return True

        messagebox_module = SimpleNamespace(
            askyesno=_askyesno,
            showerror=lambda *args, **kwargs: None,
            showinfo=lambda *args, **kwargs: None,
        )
        build_settings_tab(
            parent,
            context,
            messagebox_module=messagebox_module,
            wallet_manager_dialog=lambda *args, **kwargs: None,
        )
        root.update()

        buttons = _find_buttons(parent, "Проверить обновления")
        assert buttons
        buttons[0].invoke()
        root.update()

        assert len(prompts) == 2
        assert "исходной копии проекта" in prompts[1]
        assert launches == [str(controller.download_path)]
    finally:
        root.destroy()


def test_settings_tab_ignores_repeat_check_clicks_while_flow_is_active() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        controller = _Controller(supported=True)
        launches: list[str] = []
        pending: list[dict[str, Any]] = []
        context = _build_deferred_context(controller, launches, pending)
        parent = tk.Frame(root)
        parent.pack()

        messagebox_module = SimpleNamespace(
            askyesno=lambda *args, **kwargs: False,
            showerror=lambda *args, **kwargs: None,
            showinfo=lambda *args, **kwargs: None,
        )
        build_settings_tab(
            parent,
            context,
            messagebox_module=messagebox_module,
            wallet_manager_dialog=lambda *args, **kwargs: None,
        )
        root.update()

        buttons = _find_buttons(parent, "Проверить обновления")
        assert buttons
        buttons[0].invoke()
        buttons[0].invoke()
        root.update()

        assert len(pending) == 1
        assert controller.check_calls == 0

        result = pending[0]["task"]()
        on_success = pending[0]["on_success"]
        assert callable(on_success)
        on_success(result)
        root.update()

        assert controller.check_calls == 1
        state = getattr(buttons[0], "state", None)
        assert callable(state)
        assert "disabled" not in str(state())
    finally:
        root.destroy()
