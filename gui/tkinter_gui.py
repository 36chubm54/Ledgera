import logging
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import Any, cast

from app.services import CurrencyService
from bootstrap import bootstrap_repository
from domain.import_policy import ImportPolicy
from gui.controllers import FinancialController
from gui.hotkeys import register_hotkeys
from gui.i18n import set_language, tr
from gui.runtime_coordinator import AfterOwner, UiRuntimeCoordinator
from gui.shell.shell_lifecycle import ensure_tab_built, handle_tab_changed, schedule_deferred_action
from gui.shell.shell_notebook import render_notebook_underline
from gui.shell.shell_notebook import (
    schedule_notebook_underline as schedule_notebook_underline_render,
)
from gui.shell.shell_preferences import (
    handle_owner_display_currency_change,
    handle_owner_language_change,
    handle_owner_theme_change,
    reload_ui_strings,
)
from gui.shell.shell_records import (
    hide_owner_records_tooltip,
    refresh_owner_record_views,
    show_owner_records_tooltip,
)
from gui.shell.shell_refresh import (
    refresh_owner_all,
    refresh_owner_budgets,
    refresh_owner_display_currency_views,
    refresh_owner_theme_surfaces,
    refresh_owner_wallet_views,
)
from gui.shell.shell_runtime import run_background_task, set_busy_state
from gui.shell.shell_setup import attach_tab_aliases, initialize_shell_state
from gui.shell.shell_startup import report_startup_auto_payments
from gui.shell.shell_state import (
    apply_saved_ui_preferences,
    assign_status_bar_state,
    rebuild_status_bar,
    reset_tab_bindings_state,
)
from gui.shell.shell_support import resolve_import_policy
from gui.shell.shell_tabs import apply_tab_titles, rebuild_built_tabs
from gui.shell.shell_window import apply_window_icon, configure_main_window
from gui.startup_coordinator import DeferredStartupCoordinator
from gui.status_bar_builder import build_status_bar
from gui.status_bar_coordinator import StatusBarCoordinator, StatusBarOwner
from gui.tab_lifecycle import TAB_ORDER, TabBuildContext, attach_tabs, build_tab, create_tab_frames
from gui.tabs.infographics_support import (
    handle_chart_filter_change,
    refresh_owner_infographics,
    scroll_owner_legend_canvas,
)
from gui.ui_helpers import show_error, show_info
from gui.ui_text import app_title, get_import_formats, get_tab_titles
from gui.ui_theme import (
    DEFAULT_THEME,
    PAD_SM,
    PAD_XL,
    bootstrap_ui,
    get_palette,
    get_theme,
    refresh_treeview_zebra,
)

logger = logging.getLogger(__name__)


class FinancialApp(tk.Tk):
    _record_id_to_repo_index: dict[str, int]
    _record_id_to_domain_id: dict[str, int]
    _record_id_to_description: dict[str, str]
    _chart_refresh_suspended: bool
    _built_tabs: set[str]
    _analytics_bindings: Any | None
    _dashboard_bindings: Any | None
    _budget_bindings: Any | None
    _debt_bindings: Any | None
    _distribution_bindings: Any | None
    _operations_bindings: Any | None
    _reports_tab: Any | None
    _settings_bindings: Any | None
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

    def __init__(self) -> None:
        super().__init__()

        icons_dir = Path(__file__).resolve().parent / "assets" / "icons"
        apply_window_icon(self, icons_dir=icons_dir)
        configure_main_window(self)

        self.repository = bootstrap_repository(run_maintenance=False)
        base_currency = "KZT"
        get_schema_meta = getattr(self.repository, "get_schema_meta", None)
        if callable(get_schema_meta):
            base_currency = str(get_schema_meta("base_currency") or "KZT").upper()
        self.currency = CurrencyService(base=base_currency)
        self.controller = FinancialController(self.repository, self.currency)
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

        def _refresh_charts_deferred(records: list[Any] | None = None) -> None:
            schedule_deferred_action(
                self._schedule_after_idle,
                "startup_refresh_charts",
                lambda: self._refresh_charts(records=records),
            )

        def _refresh_budgets_deferred() -> None:
            schedule_deferred_action(
                self._schedule_after_idle,
                "startup_refresh_budgets",
                self._refresh_budgets,
            )

        def _refresh_all_deferred() -> None:
            schedule_deferred_action(
                self._schedule_after_idle,
                "startup_refresh_all",
                self._refresh_all,
            )

        self._startup = DeferredStartupCoordinator(
            controller=self.controller,
            repository=self.repository,
            run_background=self._run_background,
            refresh_list=self._refresh_list,
            refresh_charts=_refresh_charts_deferred,
            refresh_budgets=_refresh_budgets_deferred,
            refresh_all=_refresh_all_deferred,
            apply_saved_online_mode=self._apply_saved_online_mode,
            show_auto_payment_message=lambda created_auto_payments: report_startup_auto_payments(
                created_auto_payments,
                logger=logger,
                format_money=lambda amount: self.controller.format_display_money(amount),
                show_info_message=lambda message: show_info(
                    message,
                    title=tr("app.autopay.title", "Автоплатежи применены"),
                ),
            ),
            logger=logger,
        )
        initialize_shell_state(self, after_jobs=self._runtime.after_jobs)

        self._status_bar = assign_status_bar_state(self, build_status_bar(self))
        self._status_bar.grid(row=2, column=0, sticky="ew")

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._notebook = notebook
        self._notebook_underline = tk.Canvas(
            self,
            height=3,
            highlightthickness=0,
            bd=0,
            bg=get_palette().background,
        )

        self._tab_order = list(TAB_ORDER)
        self._tab_widgets = create_tab_frames(notebook)
        attach_tab_aliases(self, self._tab_widgets)
        self._tab_keys_by_widget = attach_tabs(notebook, self._tab_widgets)
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")
        notebook.bind("<Configure>", lambda _event: self._schedule_notebook_underline(), add="+")
        self.bind("<Configure>", lambda _event: self._schedule_notebook_underline(), add="+")

        self._ensure_tab_built("infographics")
        self._ensure_tab_built("operations")
        register_hotkeys(self)

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", padx=PAD_XL, pady=(0, PAD_SM))
        self.progress.grid_remove()
        self._schedule_notebook_underline()

        self._schedule_after_idle("deferred_startup", self._startup.start)

    def destroy(self) -> None:
        self._runtime.shutdown()
        close_method = getattr(self.repository, "close", None)
        if callable(close_method):
            close_method()
        super().destroy()

    def _cancel_all_after_jobs(self) -> None:
        self._runtime.cancel_all_after_jobs()

    def _cancel_after_job(self, key: str) -> None:
        self._runtime.cancel_after_job(key)

    def _schedule_after(self, key: str, delay_ms: int, callback: Callable[[], None]) -> str:
        return self._runtime.schedule_after(key, delay_ms, callback)

    def _schedule_after_idle(self, key: str, callback: Callable[[], None]) -> str:
        return self._runtime.schedule_after_idle(key, callback)

    def _rebuild_status_bar(self) -> None:
        self._status_bar = rebuild_status_bar(
            self,
            build_status_bar_result=build_status_bar,
            refresh_status_bar=self._refresh_status_bar,
        )

    def _rebuild_built_tabs(self) -> None:
        if not hasattr(self, "_notebook"):
            return
        rebuild_built_tabs(
            notebook=self._notebook,
            tab_keys_by_widget=self._tab_keys_by_widget,
            tab_order=self._tab_order,
            built_tabs=self._built_tabs,
            tab_widgets=self._tab_widgets,
            reset_tab_bindings=lambda: reset_tab_bindings_state(
                self,
                hide_records_tooltip=self._hide_records_tooltip,
            ),
            ensure_tab_built=self._ensure_tab_built,
            refresh_operations=self._refresh_list,
            refresh_infographics=self._refresh_charts,
            refresh_budgets=self._refresh_budgets,
            refresh_distribution=self._refresh_all,
        )

    def reload_strings(self, *, rebuild_tabs: bool = False) -> None:
        reload_ui_strings(
            set_import_formats=lambda: setattr(self, "_import_formats", get_import_formats()),
            set_title=self.title,
            title_text=app_title(),
            apply_tab_titles=lambda: (
                apply_tab_titles(
                    self._notebook,
                    self._tab_widgets,
                    tab_titles=get_tab_titles(),
                )
                if hasattr(self, "_notebook")
                else None
            ),
            rebuild_status_bar=self._rebuild_status_bar,
            rebuild_tabs=rebuild_tabs,
            rebuild_built_tabs=self._rebuild_built_tabs,
        )

    def _schedule_reload_strings(self, *, rebuild_tabs: bool = False) -> None:
        self._reload_tabs_pending = self._reload_tabs_pending or rebuild_tabs
        if "reload_strings" in self._after_jobs:
            return

        def _run() -> None:
            pending_tabs = self._reload_tabs_pending
            self._reload_tabs_pending = False
            self.reload_strings(rebuild_tabs=pending_tabs)

        self._schedule_after_idle("reload_strings", _run)

    def _on_language_changed(self, _event: tk.Event | None = None) -> None:
        handle_owner_language_change(self, set_language=set_language, logger=logger)

    def _on_theme_changed(self, _event: tk.Event | None = None) -> None:
        handle_owner_theme_change(self, bootstrap_ui=lambda theme: bootstrap_ui(self, theme))

    def _schedule_notebook_underline(self) -> None:
        schedule_notebook_underline_render(
            schedule_after_idle=self._schedule_after_idle,
            render_callback=self._render_notebook_underline,
        )

    def _render_notebook_underline(self) -> None:
        if not hasattr(self, "_notebook") or not hasattr(self, "_notebook_underline"):
            return
        palette = get_palette()
        try:
            render_notebook_underline(
                notebook=self._notebook,
                canvas=self._notebook_underline,
                background=palette.background,
                line_color=palette.tab_underline,
                horizontal_padding=PAD_SM,
            )
        except tk.TclError:
            self._notebook_underline.place_forget()

    def _refresh_theme_surfaces(self) -> None:
        refresh_owner_theme_surfaces(
            self,
            refresh_tree_zebra=lambda: refresh_treeview_zebra(
                cast(ttk.Treeview, self.records_tree)
            ),
        )

    def _refresh_display_currency_views(self) -> None:
        refresh_owner_display_currency_views(self)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        set_busy_state(self, busy=busy, message=message, base_title=app_title())

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
        block_ui: bool = True,
    ) -> None:
        run_background_task(
            self._runtime,
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message=busy_message,
            block_ui=block_ui,
            is_busy=lambda: self._busy,
            set_busy=self._set_busy,
            show_wait_info=lambda _token: show_info(
                tr("app.wait_running", "Дождитесь завершения текущей операции."),
                title=tr("app.wait", "Подождите"),
            ),
            show_error=show_error,
            logger=logger,
        )

    def _on_online_toggle(self) -> None:
        self._status.on_online_toggle()

    def _refresh_status_bar(self) -> None:
        self._status.refresh_status_bar()

    def _on_display_currency_changed(self, _event: tk.Event | None = None) -> None:
        handle_owner_display_currency_change(self)

    def _start_status_refresh_timer(self) -> None:
        self._status.start_status_refresh_timer()

    def _apply_saved_online_mode(self) -> None:
        self._status.apply_saved_online_mode()

    def _import_policy_from_ui(self, mode_label: str) -> ImportPolicy:
        return resolve_import_policy(mode_label)

    def _refresh_list(self, records: list[Any] | None = None) -> None:
        refresh_owner_record_views(self, records=records)

    def _hide_records_tooltip(self, _event: object | None = None) -> None:
        hide_owner_records_tooltip(self, _event)

    def _show_records_tooltip(self, event: tk.Event) -> None:
        show_owner_records_tooltip(self, event)

    def _refresh_charts(self, records: list[Any] | None = None) -> None:
        refresh_owner_infographics(self, records=records)

    def _ensure_tab_built(self, tab_key: str) -> None:
        ensure_tab_built(
            self._built_tabs,
            tab_key,
            build_tab_for_key=lambda key: build_tab(cast(TabBuildContext, self), key),
        )

    def _on_tab_changed(self, _event: tk.Event) -> None:
        if not hasattr(self, "_notebook"):
            return
        handle_tab_changed(
            self._notebook,
            self._tab_keys_by_widget,
            ensure_tab_built_for_key=self._ensure_tab_built,
            schedule_notebook_underline=self._schedule_notebook_underline,
        )

    def _refresh_wallets(self) -> None:
        refresh_owner_wallet_views(self)

    def _refresh_budgets(self) -> None:
        refresh_owner_budgets(self)

    def _refresh_all(self) -> None:
        refresh_owner_all(self)

    def _on_chart_filter_change(self, *_args: Any) -> None:
        handle_chart_filter_change(self)

    def _on_legend_mousewheel(self, event: tk.Event) -> None:
        scroll_owner_legend_canvas(self, event)


def main() -> None:
    try:
        app = FinancialApp()
        app.mainloop()
    except KeyboardInterrupt:
        show_info(
            tr("app.closed_by_user", "Приложение закрыто пользователем."),
            title=tr("app.info", "Информация"),
        )
