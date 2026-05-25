"""Main Tkinter composition shell.

Keep feature-specific behavior in gui.tabs.* and shell-policy/runtime orchestration
in gui.shell.* so this module stays a shell-only composition root.
"""

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any, cast

from app.services import CurrencyService
from app_paths import get_icons_dir
from bootstrap import bootstrap_repository
from domain.import_policy import ImportPolicy
from gui.controllers import FinancialController
from gui.hotkeys import register_hotkeys
from gui.i18n import set_language, tr
from gui.runtime_coordinator import AfterOwner, UiRuntimeCoordinator
from gui.shell.core.app_init import (
    build_owner_startup_coordinator,
    initialize_owner_busy_overlay,
    initialize_owner_shell_layout,
)
from gui.shell.core.refresh import refresh_owner_theme_surfaces
from gui.shell.core.runtime import set_busy_state
from gui.shell.core.setup import initialize_shell_state
from gui.shell.core.state import (
    apply_saved_ui_preferences,
    rebuild_status_bar,
    reset_tab_bindings_state,
)
from gui.shell.core.ui import (
    finalize_owner_reload_state,
    on_owner_language_changed,
    on_owner_theme_changed,
    rebuild_owner_status_bar,
    reload_owner_strings,
    render_owner_notebook_underline,
    schedule_owner_notebook_underline,
    schedule_owner_reload_strings,
)
from gui.shell.owner.ops import (
    apply_owner_saved_online_mode,
    ensure_owner_tab_built,
    hide_owner_tooltip,
    on_owner_chart_filter_change,
    on_owner_display_currency_changed,
    on_owner_legend_mousewheel,
    on_owner_online_toggle,
    on_owner_tab_changed,
    owner_import_policy_from_ui,
    refresh_owner_all_shell,
    refresh_owner_budget_shell,
    refresh_owner_charts,
    refresh_owner_display_currency_shell,
    refresh_owner_list,
    refresh_owner_status_bar,
    refresh_owner_wallet_shell,
    show_owner_tooltip,
    start_owner_status_refresh_timer,
)
from gui.shell.owner.runtime import (
    destroy_owner_runtime,
    rebuild_owner_tabs,
    run_owner_background_task,
    set_owner_busy,
)
from gui.shell.windowing.updates import (
    launch_owner_downloaded_update_and_exit,
    launch_owner_installer_and_exit,
)
from gui.shell.windowing.window import (
    APP_LINUX_WM_CLASS,
    activate_main_window,
    apply_window_icon,
    configure_main_window,
)
from gui.status_bar_builder import build_status_bar
from gui.status_bar_coordinator import StatusBarCoordinator, StatusBarOwner
from gui.tab_lifecycle import build_tab
from gui.tabs.analytics import AnalyticsTabBindings
from gui.tabs.budget import BudgetTabBindings
from gui.tabs.dashboard import DashboardTabBindings
from gui.tabs.debts import DebtsTabBindings
from gui.tabs.distribution import DistributionTabBindings
from gui.tabs.mandatory import MandatoryTabBindings
from gui.tabs.operations import OperationsTabBindings
from gui.tabs.reports import ReportsFrame
from gui.tabs.settings import SettingsTabBindings
from gui.ui_helpers import show_info
from gui.ui_text import app_title, get_import_formats
from gui.ui_theme import (
    DEFAULT_THEME,
    PAD_SM,
    bootstrap_ui,
    get_theme,
    refresh_treeview_zebra,
)

logger = logging.getLogger(__name__)


class FinancialApp(tk.Tk):
    _notebook: ttk.Notebook
    _notebook_underline: tk.Canvas
    _tab_order: list[str]
    _tab_widgets: dict[str, ttk.Frame]
    _tab_keys_by_widget: dict[str, str]
    _record_id_to_repo_index: dict[str, int]
    _record_id_to_domain_id: dict[str, int]
    _record_id_to_description: dict[str, str]
    _infographics_records_cache: list[object] | None
    _chart_refresh_suspended: bool
    _built_tabs: set[str]
    _analytics_bindings: AnalyticsTabBindings | None
    _dashboard_bindings: DashboardTabBindings | None
    _budget_bindings: BudgetTabBindings | None
    _mandatory_bindings: MandatoryTabBindings | None
    _debt_bindings: DebtsTabBindings | None
    _distribution_bindings: DistributionTabBindings | None
    _operations_bindings: OperationsTabBindings | None
    _reports_tab: ReportsFrame | None
    _settings_bindings: SettingsTabBindings | None
    _after_jobs: dict[str, str]
    _online_var: tk.BooleanVar | None
    _currency_status_label: ttk.Label | None
    _price_status_label: ttk.Label | None
    _display_currency_var: tk.StringVar | None
    _display_currency_combo: ttk.Combobox | None
    _language_var: tk.StringVar | None
    _language_combo: ttk.Combobox | None
    _theme_var: tk.StringVar | None
    _theme_combo: ttk.Combobox | None
    _theme_label_to_key: dict[str, str]
    _reload_tabs_pending: bool
    _online_toggle_running: bool
    _hotkey_help_dialog: tk.Toplevel | None
    _hotkeys_registered: bool
    _records_tooltip_window: tk.Toplevel | None
    _records_tooltip_text: str
    records_tree: ttk.Treeview | None
    record_tags_tree: ttk.Treeview | None
    refresh_operation_wallet_menu: Callable[[], None] | None
    refresh_transfer_wallet_menus: Callable[[], None] | None
    refresh_wallets: Callable[[], None] | None
    refresh_mandatory: Callable[[], None] | None
    refresh_budgets: Callable[[], None] | None
    refresh_all: Callable[[], None] | None
    pie_month_var: tk.StringVar | None
    pie_month_menu: ttk.Combobox | None
    chart_month_var: tk.StringVar | None
    chart_month_menu: ttk.Combobox | None
    chart_year_var: tk.StringVar | None
    chart_year_menu: ttk.Combobox | None
    expense_pie_canvas: tk.Canvas | None
    expense_legend_canvas: tk.Canvas | None
    expense_legend_frame: tk.Frame | None
    daily_bar_canvas: tk.Canvas | None
    monthly_bar_canvas: tk.Canvas | None

    def __init__(self, *, initial_base_currency: str | None = None) -> None:
        super().__init__(className=APP_LINUX_WM_CLASS)

        apply_window_icon(self, icons_dir=get_icons_dir())
        configure_main_window(self)

        self.repository = bootstrap_repository(
            run_maintenance=False,
            initial_base_currency=initial_base_currency,
        )
        base_currency = "KZT"
        get_schema_meta = getattr(self.repository, "get_schema_meta", None)
        if callable(get_schema_meta):
            base_currency = str(get_schema_meta("base_currency") or "KZT").upper()
        self.currency = CurrencyService(base=base_currency)
        self.controller = FinancialController(self.repository, self.currency)
        self.controller.reconcile_pending_update_state()
        apply_saved_ui_preferences(
            self,
            controller=self.controller,
            set_language=set_language,
            bootstrap_ui=bootstrap_ui,
            get_theme=get_theme,
            default_theme=DEFAULT_THEME,
            logger=logger,
        )
        self._import_formats = get_import_formats()
        self.title(app_title())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._runtime = UiRuntimeCoordinator(cast(AfterOwner, self))
        self._status = StatusBarCoordinator(cast(StatusBarOwner, self), logger=logger)
        self._busy = False
        self._startup = build_owner_startup_coordinator(self, logger=logger)
        initialize_shell_state(self, after_jobs=self._runtime.after_jobs)
        initialize_owner_shell_layout(self, register_hotkeys_func=register_hotkeys)
        initialize_owner_busy_overlay(self)
        self._schedule_notebook_underline()
        self._set_busy(True, tr("app.busy.startup", "Подготавливаем рабочее пространство..."))
        self._schedule_after_idle("activate_main_window", lambda: activate_main_window(self))
        self._schedule_after_idle("deferred_startup", self._startup.start)

    def destroy(self) -> None:
        destroy_owner_runtime(self, destroy_base=super().destroy)

    def _cancel_all_after_jobs(self) -> None:
        self._runtime.cancel_all_after_jobs()

    def _cancel_after_job(self, key: str) -> None:
        self._runtime.cancel_after_job(key)

    def _schedule_after(self, key: str, delay_ms: int, callback: Callable[[], None]) -> str:
        return self._runtime.schedule_after(key, delay_ms, callback)

    def _schedule_after_idle(self, key: str, callback: Callable[[], None]) -> str:
        return self._runtime.schedule_after_idle(key, callback)

    def _rebuild_status_bar(self) -> None:
        rebuild_owner_status_bar(
            self,
            rebuild_status_bar=rebuild_status_bar,
            build_status_bar_result=build_status_bar,
        )

    def _rebuild_built_tabs(self) -> None:
        rebuild_owner_tabs(
            self,
            reset_tab_bindings=lambda: reset_tab_bindings_state(
                self,
                hide_records_tooltip=self._hide_records_tooltip,
            ),
        )

    def reload_strings(self, *, rebuild_tabs: bool = False) -> None:
        self._reload_tabs_pending = rebuild_tabs
        reload_owner_strings(
            self,
            rebuild_built_tabs=self._rebuild_built_tabs,
            rebuild_status_bar=self._rebuild_status_bar,
        )

    def _schedule_reload_strings(self, *, rebuild_tabs: bool = False) -> None:
        schedule_owner_reload_strings(
            self,
            rebuild_tabs=rebuild_tabs,
            reload_strings=lambda: self.reload_strings(
                rebuild_tabs=finalize_owner_reload_state(self)
            ),
        )

    def _on_language_changed(self, _event: tk.Event | None = None) -> None:
        on_owner_language_changed(self, logger=logger)

    def _on_theme_changed(self, _event: tk.Event | None = None) -> None:
        on_owner_theme_changed(self, bootstrap_ui=lambda theme: bootstrap_ui(self, theme))

    def _schedule_notebook_underline(self) -> None:
        schedule_owner_notebook_underline(self)

    def _render_notebook_underline(self) -> None:
        render_owner_notebook_underline(self, horizontal_padding=PAD_SM)

    def _refresh_theme_surfaces(self) -> None:
        refresh_owner_theme_surfaces(
            self,
            refresh_tree_zebra=lambda: refresh_treeview_zebra(
                cast(ttk.Treeview, self.records_tree)
            ),
        )

    def _refresh_display_currency_views(self) -> None:
        refresh_owner_display_currency_shell(self)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        set_owner_busy(self, busy, message=message, set_busy_state=set_busy_state)

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
        block_ui: bool = True,
    ) -> None:
        run_owner_background_task(
            self,
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message=busy_message,
            block_ui=block_ui,
            logger=logger,
        )

    def _on_online_toggle(self) -> None:
        on_owner_online_toggle(self._status)

    def _refresh_status_bar(self) -> None:
        refresh_owner_status_bar(self._status)

    def _on_display_currency_changed(self, _event: tk.Event | None = None) -> None:
        on_owner_display_currency_changed(self)

    def _start_status_refresh_timer(self) -> None:
        start_owner_status_refresh_timer(self._status)

    def _apply_saved_online_mode(self) -> None:
        apply_owner_saved_online_mode(self._status)

    def _import_policy_from_ui(self, mode_label: str) -> ImportPolicy:
        return owner_import_policy_from_ui(mode_label)

    def _refresh_list(self, records: list[Any] | None = None) -> None:
        refresh_owner_list(self, records=records)

    def _hide_records_tooltip(self, _event: object | None = None) -> None:
        hide_owner_tooltip(self, _event)

    def _show_records_tooltip(self, event: tk.Event) -> None:
        show_owner_tooltip(self, event)

    def _refresh_charts(self, records: list[Any] | None = None) -> None:
        refresh_owner_charts(self, records=records)

    def _ensure_tab_built(self, tab_key: str) -> None:
        ensure_owner_tab_built(self, tab_key, build_tab_for_key=lambda key: build_tab(self, key))

    def _on_tab_changed(self, _event: tk.Event) -> None:
        on_owner_tab_changed(self)

    def _refresh_wallets(self) -> None:
        refresh_owner_wallet_shell(self)

    def _refresh_budgets(self) -> None:
        refresh_owner_budget_shell(self)

    def _refresh_all(self) -> None:
        refresh_owner_all_shell(self)

    def _on_chart_filter_change(self, *_args: Any) -> None:
        on_owner_chart_filter_change(self)

    def _on_legend_mousewheel(self, event: tk.Event) -> None:
        on_owner_legend_mousewheel(self, event)

    def _launch_downloaded_update_and_exit(
        self,
        artifact_path: str,
        *,
        target_version: str | None = None,
    ) -> None:
        launch_owner_downloaded_update_and_exit(
            self,
            artifact_path=artifact_path,
            load_saved_terminal=self.controller.load_linux_terminal_preference,
            save_terminal=self.controller.save_linux_terminal_preference,
            mark_pending_cleanup=lambda path, version: self.controller.mark_pending_update_cleanup(
                artifact_path=path,
                target_version=version,
            ),
            target_version=target_version,
        )

    def _launch_installer_and_exit(self, installer_path: str) -> None:
        launch_owner_installer_and_exit(self, installer_path)


def main(*, initial_base_currency: str | None = None) -> None:
    try:
        app = FinancialApp(initial_base_currency=initial_base_currency)
        app.mainloop()
    except KeyboardInterrupt:
        show_info(
            tr("app.closed_by_user", "Приложение закрыто пользователем."),
            title=tr("app.info", "Информация"),
        )
