from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from domain.update import (
    AppReleaseAsset,
    AppUpdateCheckResult,
    AppUpdateDownloadProgress,
    AppUpdateDownloadResult,
    AppUpdateReleaseInfo,
    PendingUpdateInstallState,
)
from gui.tabs.settings.builder import build_settings_tab
from gui.tabs.settings.contracts import SettingsTabContext


def _new_root() -> tk.Tk:
    try:
        return tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable in local environment: {exc}")


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


def _find_labels(parent: tk.Misc) -> list[tk.Label | ttk.Label]:
    found: list[tk.Label | ttk.Label] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, (tk.Label, ttk.Label)):
                found.append(child)
            _walk(child)

    _walk(parent)
    return found


class _Controller:
    def __init__(
        self,
        *,
        supported: bool = True,
        packaged_mode: bool = True,
        appimage_mode: bool = False,
        linux_package_kind: str = "",
    ) -> None:
        self.supported = supported
        self.packaged_mode = packaged_mode
        self.appimage_mode = appimage_mode
        self.linux_package_kind = linux_package_kind
        self.check_calls = 0
        self.download_calls = 0
        self.download_progress: list[AppUpdateDownloadProgress] = []
        self.release = AppUpdateReleaseInfo(
            version="2.0.2",
            tag_name="v2.0.2",
            release_url="https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            asset=AppReleaseAsset(
                name="Ledgera-2.0.2-setup.exe",
                download_url="https://example.invalid/setup.exe",
                size_bytes=4096,
                kind="windows-installer",
            ),
        )
        self.download_path = Path("C:/Temp/Ledgera-2.0.2-setup.exe")
        self.pending_install_state: PendingUpdateInstallState | None = None
        self.cleared_pending_install = False

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
            "user_data_root": "C:/Users/test/AppData/Local/Ledgera",
            "packaged_mode": self.packaged_mode,
            "appimage_mode": self.appimage_mode,
            "linux_package_kind": self.linux_package_kind,
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

    def get_app_release_page_url(self) -> str:
        return "https://github.com/36chubm54/Ledgera/releases"

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

    def save_pending_update_install_state(self, state: PendingUpdateInstallState) -> None:
        self.pending_install_state = state
        self.cleared_pending_install = False

    def load_pending_update_install_state(self) -> PendingUpdateInstallState | None:
        return self.pending_install_state

    def clear_pending_update_install_state(self) -> None:
        self.pending_install_state = None
        self.cleared_pending_install = True


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
                "_launch_downloaded_update_and_exit": lambda self, installer_path, **kwargs: (
                    launches.append(f"{installer_path}|{kwargs.get('target_version') or ''}")
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
                "_launch_downloaded_update_and_exit": lambda self, installer_path, **kwargs: (
                    launches.append(f"{installer_path}|{kwargs.get('target_version') or ''}")
                ),
                "_run_background": _run_background,
            },
        )(),
    )


def test_settings_tab_disables_update_button_when_not_supported() -> None:
    root = _new_root()
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
    root = _new_root()
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
        assert launches == [f"{controller.download_path}|2.0.2"]
    finally:
        root.destroy()


def test_settings_tab_enables_release_page_for_packaged_linux_manual_updates() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=False, packaged_mode=True, appimage_mode=True)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with patch("gui.tabs.settings.update_section.sys.platform", "linux"):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
        root.update_idletasks()

        release_buttons = _find_buttons(parent, "Страница релиза")
        assert release_buttons
        state = getattr(release_buttons[0], "state", None)
        assert callable(state)
        assert "disabled" not in str(state())
    finally:
        root.destroy()


def test_settings_tab_enables_check_button_for_packaged_linux_without_known_package_kind() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=False, packaged_mode=True)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with patch("gui.tabs.settings.update_section.sys.platform", "linux"):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
        root.update_idletasks()

        check_buttons = _find_buttons(parent, "Проверить обновления")
        assert check_buttons
        state = getattr(check_buttons[0], "state", None)
        assert callable(state)
        assert "disabled" in str(state())
    finally:
        root.destroy()


def test_settings_tab_packaged_linux_without_known_package_kind_shows_manual_block() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=False, packaged_mode=True)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with patch("gui.tabs.settings.update_section.sys.platform", "linux"):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
        root.update_idletasks()

        texts = []
        for label in _find_labels(parent):
            try:
                texts.append(str(label.cget("text") or ""))
            except Exception:
                continue
        joined = "\n".join(texts)
        assert "встроенная установка обновлений пока недоступна" in joined
        assert "Можно проверить наличие нового Linux-пакета" not in joined
    finally:
        root.destroy()


def test_settings_tab_keeps_release_page_disabled_for_packaged_non_linux_updates() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=False, packaged_mode=True)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with patch("gui.tabs.settings.update_section.sys.platform", "darwin"):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
        root.update_idletasks()

        release_buttons = _find_buttons(parent, "Страница релиза")
        assert release_buttons
        state = getattr(release_buttons[0], "state", None)
        assert callable(state)
        assert "disabled" in str(state())
    finally:
        root.destroy()


def test_settings_tab_packaged_linux_flow_downloads_and_opens_package() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(
            supported=True,
            packaged_mode=True,
            linux_package_kind="deb",
        )
        controller.release = AppUpdateReleaseInfo(
            version="2.0.2",
            tag_name="v2.0.2",
            release_url="https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            asset=AppReleaseAsset(
                name="Ledgera-2.0.2-x86_64.deb",
                download_url="https://example.invalid/linux.deb",
                size_bytes=4096,
                kind="linux-deb",
            ),
        )
        controller.download_path = Path("/tmp/Ledgera-2.0.2-x86_64.deb")
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
        with patch("gui.tabs.settings.update_section.sys.platform", "linux"):
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
        assert any("Linux-пакет" in prompt or "Linux package" in prompt for prompt in prompts)
        assert any(
            "терминал" in prompt.lower() or "terminal" in prompt.lower() for prompt in prompts
        )
        assert launches == [f"{controller.download_path}|2.0.2"]
    finally:
        root.destroy()


def test_settings_tab_packaged_linux_offers_release_page_after_launch_failure() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(
            supported=True,
            packaged_mode=True,
            linux_package_kind="deb",
        )
        controller.release = AppUpdateReleaseInfo(
            version="2.0.2",
            tag_name="v2.0.2",
            release_url="https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
            asset=AppReleaseAsset(
                name="Ledgera-2.0.2-x86_64.deb",
                download_url="https://example.invalid/linux.deb",
                size_bytes=4096,
                kind="linux-deb",
            ),
        )
        controller.download_path = Path("/tmp/Ledgera-2.0.2-x86_64.deb")
        launches: list[str] = []
        opened_urls: list[str] = []
        prompts: list[str] = []
        errors: list[str] = []
        context = _build_context(controller, launches)
        context._launch_downloaded_update_and_exit = lambda artifact_path, **_kwargs: (
            _ for _ in ()
        ).throw(RuntimeError("no terminal"))
        parent = tk.Frame(root)
        parent.pack()

        def _askyesno(_title: str, message: str) -> bool:
            prompts.append(message)
            return True

        messagebox_module = SimpleNamespace(
            askyesno=_askyesno,
            showerror=lambda _title, message: errors.append(message),
            showinfo=lambda *args, **kwargs: None,
        )
        with (
            patch("gui.tabs.settings.update_section.sys.platform", "linux"),
            patch(
                "gui.tabs.settings.update_section.webbrowser.open",
                lambda url: opened_urls.append(url),
            ),
        ):
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
        assert errors and "no terminal" in errors[0]
        assert any(
            "страницу релиза" in prompt.lower() or "releases page" in prompt.lower()
            for prompt in prompts
        )
        assert opened_urls == [controller.release.release_url]
        assert launches == []
    finally:
        root.destroy()


def test_settings_tab_windows_source_mode_uses_manual_release_path() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=False, packaged_mode=False)
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()
        messagebox_module = SimpleNamespace(
            askyesno=lambda *args, **kwargs: True,
            showerror=lambda *args, **kwargs: None,
            showinfo=lambda *args, **kwargs: None,
        )
        with patch("gui.tabs.settings.update_section.sys.platform", "win32"):
            build_settings_tab(
                parent,
                context,
                messagebox_module=messagebox_module,
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
        root.update_idletasks()

        check_buttons = _find_buttons(parent, "Проверить обновления")
        assert check_buttons
        check_state = getattr(check_buttons[0], "state", None)
        assert callable(check_state)
        assert "disabled" in str(check_state())

        release_buttons = _find_buttons(parent, "Страница релиза")
        assert release_buttons
        release_state = getattr(release_buttons[0], "state", None)
        assert callable(release_state)
        assert "disabled" not in str(release_state())
        assert launches == []
    finally:
        root.destroy()


def test_settings_tab_ignores_repeat_check_clicks_while_flow_is_active() -> None:
    root = _new_root()
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


def test_settings_tab_enables_release_page_after_failed_check_in_supported_env() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=True, packaged_mode=True, linux_package_kind="deb")
        launches: list[str] = []
        pending: list[dict[str, Any]] = []
        errors: list[str] = []
        context = _build_deferred_context(controller, launches, pending)
        parent = tk.Frame(root)
        parent.pack()

        messagebox_module = SimpleNamespace(
            askyesno=lambda *args, **kwargs: False,
            showerror=lambda _title, message: errors.append(message),
            showinfo=lambda *args, **kwargs: None,
        )
        with patch("gui.tabs.settings.update_section.sys.platform", "linux"):
            build_settings_tab(
                parent,
                context,
                messagebox_module=messagebox_module,
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
        root.update()

        check_buttons = _find_buttons(parent, "Проверить обновления")
        release_buttons = _find_buttons(parent, "Страница релиза")
        assert check_buttons and release_buttons
        check_buttons[0].invoke()
        root.update()

        assert len(pending) == 1
        on_error = pending[0]["on_error"]
        assert callable(on_error)
        on_error(RuntimeError("network failed"))
        root.update()

        release_state = getattr(release_buttons[0], "state", None)
        assert callable(release_state)
        assert "disabled" not in str(release_state())
        assert errors and "network failed" in errors[0]
    finally:
        root.destroy()


def test_settings_tab_restores_install_cta_for_pending_download() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=True, packaged_mode=True, linux_package_kind="deb")
        controller.download_path = Path("/tmp/Ledgera-2.0.2-x86_64.deb")
        controller.pending_install_state = PendingUpdateInstallState(
            version="2.0.2",
            asset_kind="linux-deb",
            artifact_path=controller.download_path,
            release_url="https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
        )
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with (
            patch("gui.tabs.settings.update_section.sys.platform", "linux"),
            patch.object(Path, "is_file", lambda self: str(self) == str(controller.download_path)),
        ):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(
                    askyesno=lambda *args, **kwargs: True,
                    showerror=lambda *args, **kwargs: None,
                    showinfo=lambda *args, **kwargs: None,
                ),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
            root.update()

            buttons = _find_buttons(parent, "Установить обновление")
            assert buttons
            buttons[0].invoke()
            root.update()

        assert controller.check_calls == 0
        assert controller.download_calls == 0
        assert launches == [f"{controller.download_path}|2.0.2"]
    finally:
        root.destroy()


def test_settings_tab_restores_install_cta_for_pending_windows_installer() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=True, packaged_mode=True)
        controller.download_path = Path("C:/Temp/Ledgera-2.0.2-setup.exe")
        controller.pending_install_state = PendingUpdateInstallState(
            version="2.0.2",
            asset_kind="windows-installer",
            artifact_path=controller.download_path,
            release_url="https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
        )
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with patch.object(Path, "is_file", lambda self: str(self) == str(controller.download_path)):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(
                    askyesno=lambda *args, **kwargs: True,
                    showerror=lambda *args, **kwargs: None,
                    showinfo=lambda *args, **kwargs: None,
                ),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
            root.update()

            buttons = _find_buttons(parent, "Установить обновление")
            assert buttons
            buttons[0].invoke()
            root.update()

        assert controller.check_calls == 0
        assert controller.download_calls == 0
        assert launches == [f"{controller.download_path}|2.0.2"]
    finally:
        root.destroy()


def test_settings_tab_clears_missing_pending_download_and_falls_back_to_check() -> None:
    root = _new_root()
    root.withdraw()
    try:
        controller = _Controller(supported=True, packaged_mode=True, linux_package_kind="deb")
        controller.download_path = Path("/tmp/Ledgera-2.0.2-x86_64.deb")
        controller.pending_install_state = PendingUpdateInstallState(
            version="2.0.2",
            asset_kind="linux-deb",
            artifact_path=controller.download_path,
            release_url="https://github.com/36chubm54/Ledgera/releases/tag/v2.0.2",
        )
        launches: list[str] = []
        context = _build_context(controller, launches)
        parent = tk.Frame(root)
        parent.pack()

        with (
            patch("gui.tabs.settings.update_section.sys.platform", "linux"),
            patch.object(Path, "is_file", lambda self: False),
        ):
            build_settings_tab(
                parent,
                context,
                messagebox_module=SimpleNamespace(
                    askyesno=lambda *args, **kwargs: False,
                    showerror=lambda *args, **kwargs: None,
                    showinfo=lambda *args, **kwargs: None,
                ),
                wallet_manager_dialog=lambda *args, **kwargs: None,
            )
            root.update()

            buttons = _find_buttons(parent, "Проверить обновления")
            assert buttons
            buttons[0].invoke()
            root.update()

        assert controller.cleared_pending_install is True
        assert controller.check_calls == 1
        assert launches == []
    finally:
        root.destroy()
