import ctypes
import logging
import os
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from tkinter import TclError, ttk
from typing import Any

from app.services import CurrencyService
from bootstrap import bootstrap_repository, run_post_startup_maintenance
from domain.import_policy import ImportPolicy
from gui.controllers import FinancialController
from gui.hotkeys import _show_hotkey_help, register_hotkeys
from gui.i18n import get_available_languages, get_language, set_language, tr
from gui.logging_utils import log_ui_error
from gui.record_colors import KIND_TO_FOREGROUND, foreground_for_kind
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
from utils.charting import (
    aggregate_daily_cashflow,
    aggregate_expenses_by_category,
    aggregate_monthly_cashflow,
    extract_months,
    extract_years,
)
from utils.tag_utils import color_for_tag
from version import __version__

logger = logging.getLogger(__name__)


def _enable_windows_dpi_awareness() -> None:
    """Enable high-DPI awareness early so Tk and native file dialogs stay sharp."""
    if os.name != "nt":
        return
    errors: list[str] = []

    try:
        user32 = ctypes.windll.user32
    except Exception as exc:
        logger.debug("DPI awareness skipped: user32 is unavailable: %s", exc)
        return

    try:
        # Best quality on modern Windows: Per-Monitor v2.
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            per_monitor_v2 = ctypes.c_void_p(-4)
            if user32.SetProcessDpiAwarenessContext(per_monitor_v2):
                logger.debug("DPI awareness enabled via SetProcessDpiAwarenessContext(PMv2).")
                return
            errors.append("SetProcessDpiAwarenessContext returned 0")
    except Exception as exc:
        errors.append(f"SetProcessDpiAwarenessContext failed: {exc}")

    try:
        # Fallback for Windows 8.1+.
        shcore = ctypes.windll.shcore
        if hasattr(shcore, "SetProcessDpiAwareness"):
            # 2 == PROCESS_PER_MONITOR_DPI_AWARE
            shcore.SetProcessDpiAwareness(2)
            logger.debug("DPI awareness enabled via SetProcessDpiAwareness(2).")
            return
        errors.append("SetProcessDpiAwareness is unavailable")
    except Exception as exc:
        errors.append(f"SetProcessDpiAwareness failed: {exc}")

    try:
        # Legacy fallback for older Windows versions.
        if hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
            logger.debug("DPI awareness enabled via SetProcessDPIAware().")
            return
        errors.append("SetProcessDPIAware is unavailable")
    except Exception as exc:
        errors.append(f"SetProcessDPIAware failed: {exc}")

    if errors:
        logger.warning("DPI awareness was not enabled. Details: %s", " | ".join(errors))


class FinancialApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        icons_dir = Path(__file__).resolve().parent / "assets" / "icons"
        ico_path = icons_dir / "app.ico"
        png_path = icons_dir / "app.png"

        try:
            # Windows native icon
            if ico_path.exists():
                self.iconbitmap(default=str(ico_path))
        except (TclError, OSError):
            pass

        try:
            # Tk fallback (and for other OS)
            if png_path.exists():
                app_icon = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, app_icon)
                self._app_icon_ref = app_icon  # so that GC does not gather
        except (TclError, OSError):
            pass

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        min_width = min(1640, int(screen_w * 0.9))
        min_height = min(1080, int(screen_h * 0.87))
        self.geometry(f"{min_width}x{min_height}")
        self.minsize(min_width, min_height)
        # Make shutdown explicit: ensures background executor and repository are closed
        # when user closes the window via the window manager.
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.repository = bootstrap_repository(run_maintenance=False)
        self.currency = CurrencyService()
        self.controller = FinancialController(self.repository, self.currency)
        self._apply_saved_ui_preferences()
        self._import_formats = get_import_formats()
        self.title(app_title())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._executor = ThreadPoolExecutor(max_workers=2)
        self._busy = False
        self._startup_sync_running = False
        self._record_id_to_repo_index: dict[str, int] = {}
        self._record_id_to_domain_id: dict[str, int] = {}
        self._chart_refresh_suspended = False
        self._built_tabs: set[str] = set()
        self._analytics_bindings: Any | None = None
        self._dashboard_bindings: Any | None = None
        self._budget_bindings: Any | None = None
        self._debt_bindings: Any | None = None
        self._distribution_bindings: Any | None = None
        self._operations_bindings: Any | None = None
        self._reports_tab: Any | None = None

        self.records_tree: ttk.Treeview | None = None
        self.record_tags_tree: ttk.Treeview | None = None
        self.refresh_operation_wallet_menu: Callable[[], None] | None = None
        self.refresh_transfer_wallet_menus: Callable[[], None] | None = None
        self.refresh_wallets: Callable[[], None] | None = None
        self.refresh_budgets: Callable[[], None] | None = None
        self.refresh_all: Callable[[], None] | None = None
        self._after_jobs: dict[str, str] = {}
        self._online_var: tk.BooleanVar | None = None
        self._currency_status_label: ttk.Label | None = None
        self._price_status_label: ttk.Label | None = None
        self._language_var: tk.StringVar | None = None
        self._language_combo: ttk.Combobox | None = None
        self._theme_var: tk.StringVar | None = None
        self._theme_combo: ttk.Combobox | None = None
        self._theme_label_to_key: dict[str, str] = {}
        self._reload_tabs_pending = False
        self._online_toggle_running = False
        self._hotkey_help_dialog: tk.Toplevel | None = None
        self._hotkeys_registered = False

        self.pie_month_var: tk.StringVar | None = None
        self.pie_month_menu: ttk.Combobox | None = None
        self.chart_month_var: tk.StringVar | None = None
        self.chart_month_menu: ttk.Combobox | None = None
        self.chart_year_var: tk.StringVar | None = None
        self.chart_year_menu: ttk.Combobox | None = None
        self.expense_pie_canvas: tk.Canvas | None = None
        self.expense_legend_canvas: tk.Canvas | None = None
        self.expense_legend_frame: tk.Frame | None = None
        self.daily_bar_canvas: tk.Canvas | None = None
        self.monthly_bar_canvas: tk.Canvas | None = None

        self._status_bar = self._build_status_bar()
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

        self.tab_infographics = ttk.Frame(notebook)
        self.tab_operations = ttk.Frame(notebook)
        self.tab_reports = ttk.Frame(notebook)
        self.tab_analytics = ttk.Frame(notebook)
        self.tab_dashboard = ttk.Frame(notebook)
        self.tab_budget = ttk.Frame(notebook)
        self.tab_debts = ttk.Frame(notebook)
        self.tab_distribution = ttk.Frame(notebook)
        self.tab_settings = ttk.Frame(notebook)
        self._tab_order = [
            "infographics",
            "operations",
            "reports",
            "analytics",
            "dashboard",
            "budget",
            "debts",
            "distribution",
            "settings",
        ]
        self._tab_widgets = {
            "infographics": self.tab_infographics,
            "operations": self.tab_operations,
            "reports": self.tab_reports,
            "analytics": self.tab_analytics,
            "dashboard": self.tab_dashboard,
            "budget": self.tab_budget,
            "debts": self.tab_debts,
            "distribution": self.tab_distribution,
            "settings": self.tab_settings,
        }

        tab_titles = get_tab_titles()
        notebook.add(self.tab_infographics, text=tab_titles["infographics"])
        notebook.add(self.tab_operations, text=tab_titles["operations"])
        notebook.add(self.tab_reports, text=tab_titles["reports"])
        notebook.add(self.tab_analytics, text=tab_titles["analytics"])
        notebook.add(self.tab_dashboard, text=tab_titles["dashboard"])
        notebook.add(self.tab_budget, text=tab_titles["budget"])
        notebook.add(self.tab_debts, text=tab_titles["debts"])
        notebook.add(self.tab_distribution, text=tab_titles["distribution"])
        notebook.add(self.tab_settings, text=tab_titles["settings"])
        self._tab_keys_by_widget = {
            str(self.tab_infographics): "infographics",
            str(self.tab_operations): "operations",
            str(self.tab_reports): "reports",
            str(self.tab_analytics): "analytics",
            str(self.tab_dashboard): "dashboard",
            str(self.tab_budget): "budget",
            str(self.tab_debts): "debts",
            str(self.tab_distribution): "distribution",
            str(self.tab_settings): "settings",
        }
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

        self._schedule_after_idle("deferred_startup", self._start_deferred_startup)

    def destroy(self) -> None:
        self._cancel_all_after_jobs()
        self._executor.shutdown(wait=False, cancel_futures=True)
        close_method = getattr(self.repository, "close", None)
        if callable(close_method):
            close_method()
        super().destroy()

    def _cancel_all_after_jobs(self) -> None:
        for key in list(self._after_jobs):
            self._cancel_after_job(key)

    def _cancel_after_job(self, key: str) -> None:
        job_id = self._after_jobs.pop(key, None)
        if not job_id:
            return
        try:
            self.after_cancel(job_id)
        except TclError:
            return

    def _schedule_after(self, key: str, delay_ms: int, callback: Callable[[], None]) -> str:
        self._cancel_after_job(key)

        def _run() -> None:
            self._after_jobs.pop(key, None)
            callback()

        job_id = self.after(delay_ms, _run)
        self._after_jobs[key] = str(job_id)
        return str(job_id)

    def _schedule_after_idle(self, key: str, callback: Callable[[], None]) -> str:
        self._cancel_after_job(key)

        def _run() -> None:
            self._after_jobs.pop(key, None)
            callback()

        job_id = self.after_idle(_run)
        self._after_jobs[key] = str(job_id)
        return str(job_id)

    def _apply_saved_ui_preferences(self) -> None:
        saved_language = self.controller.load_language_preference()
        if saved_language:
            try:
                set_language(saved_language)
            except ValueError:
                logger.warning("Unsupported saved language preference: %s", saved_language)
        saved_theme = self.controller.load_theme_preference()
        bootstrap_ui(self, saved_theme or get_theme() or DEFAULT_THEME)

    def _reset_tab_bindings(self) -> None:
        self.records_tree = None
        self.record_tags_tree = None
        self.refresh_operation_wallet_menu = None
        self.refresh_transfer_wallet_menus = None
        self.refresh_wallets = None
        self.refresh_budgets = None
        self.refresh_all = None
        self._operations_bindings = None
        self._reports_tab = None
        self._analytics_bindings = None
        self._dashboard_bindings = None
        self._budget_bindings = None
        self._debt_bindings = None
        self._distribution_bindings = None
        self.pie_month_var = None
        self.pie_month_menu = None
        self.chart_month_var = None
        self.chart_month_menu = None
        self.chart_year_var = None
        self.chart_year_menu = None
        self.expense_pie_canvas = None
        self.expense_legend_canvas = None
        self.expense_legend_frame = None
        self.daily_bar_canvas = None
        self.monthly_bar_canvas = None

    def _rebuild_status_bar(self) -> None:
        if hasattr(self, "_status_bar") and self._status_bar is not None:
            try:
                self._status_bar.destroy()
            except (TclError, RuntimeError):
                pass
        self._status_bar = self._build_status_bar()
        self._status_bar.grid(row=2, column=0, sticky="ew")
        self._refresh_status_bar()

    def _rebuild_built_tabs(self) -> None:
        if not hasattr(self, "_notebook"):
            return
        selected = self._notebook.select()
        selected_key = self._tab_keys_by_widget.get(str(selected))
        built_keys = [key for key in self._tab_order if key in self._built_tabs]
        for key in built_keys:
            frame = self._tab_widgets[key]
            for child in frame.winfo_children():
                child.destroy()
        self._built_tabs.clear()
        self._reset_tab_bindings()
        for key in built_keys:
            self._ensure_tab_built(key)
        if selected_key in self._tab_widgets:
            self._notebook.select(self._tab_widgets[selected_key])
        if "operations" in built_keys:
            self._refresh_list()
        if "infographics" in built_keys:
            self._refresh_charts()
        if "budget" in built_keys:
            self._refresh_budgets()
        if "distribution" in built_keys:
            self._refresh_all()

    def reload_strings(self, *, rebuild_tabs: bool = False) -> None:
        self._import_formats = get_import_formats()
        self.title(app_title())
        if hasattr(self, "_notebook"):
            tab_titles = get_tab_titles()
            for key, tab_widget in self._tab_widgets.items():
                self._notebook.tab(tab_widget, text=tab_titles[key])
        self._rebuild_status_bar()
        if rebuild_tabs:
            self._rebuild_built_tabs()

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
        if self._language_var is None:
            return
        selected = str(self._language_var.get() or "").strip().lower()
        if not selected or selected == get_language():
            return
        try:
            set_language(selected)
        except ValueError:
            logger.warning("Unsupported language selected: %s", selected)
            return
        self.controller.save_language_preference(selected)
        self._schedule_reload_strings(rebuild_tabs=True)

    def _on_theme_changed(self, _event: tk.Event | None = None) -> None:
        if self._theme_var is None:
            return
        selected_label = str(self._theme_var.get() or "")
        selected_theme = self._theme_label_to_key.get(selected_label, DEFAULT_THEME)
        if selected_theme == get_theme():
            return
        bootstrap_ui(self, selected_theme)
        self._schedule_notebook_underline()
        self.controller.save_theme_preference(selected_theme)
        self._refresh_theme_surfaces()

    def _schedule_notebook_underline(self) -> None:
        self._schedule_after_idle("notebook_underline", self._render_notebook_underline)

    def _render_notebook_underline(self) -> None:
        if not hasattr(self, "_notebook") or not hasattr(self, "_notebook_underline"):
            return
        palette = get_palette()
        self._notebook_underline.configure(bg=palette.background)
        try:
            current_index = self._notebook.index("current")
            bbox_result = self._notebook.bbox(current_index)
            if bbox_result is None:
                self._notebook_underline.place_forget()
                return
            x, y, width, height = bbox_result
        except (TclError, tk.TclError):
            self._notebook_underline.place_forget()
            return
        if width <= 0 or height <= 0:
            self._notebook_underline.place_forget()
            return
        line_y = max(height - 2, 1)
        self._notebook_underline.place(in_=self._notebook, x=0, y=y + line_y, relwidth=1, height=3)
        self._notebook_underline.delete("all")
        start_x = x + PAD_SM
        end_x = x + max(width - PAD_SM, PAD_SM)
        self._notebook_underline.create_line(
            start_x,
            1,
            end_x,
            1,
            fill=palette.tab_underline,
            width=2,
            capstyle=tk.ROUND,
        )
        self._notebook_underline.lift(self._notebook)  # type: ignore[arg-type]

    def _refresh_theme_surfaces(self) -> None:
        self._refresh_status_bar()
        if self.records_tree is not None:
            self._refresh_list()
            refresh_treeview_zebra(self.records_tree)
        if "infographics" in self._built_tabs:
            self._refresh_charts()
        analytics_refresh = getattr(self._analytics_bindings, "refresh", None)
        if callable(analytics_refresh):
            analytics_refresh()
        dashboard_refresh = getattr(self._dashboard_bindings, "refresh", None)
        if callable(dashboard_refresh):
            dashboard_refresh()
        if callable(self.refresh_budgets):
            self.refresh_budgets()
        debt_refresh = getattr(self._debt_bindings, "refresh", None)
        if callable(debt_refresh):
            debt_refresh()
        if callable(self.refresh_all):
            self.refresh_all()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        try:
            self.attributes("-disabled", busy)
        except TclError:
            pass
        if busy:
            self.progress.grid()
            self.progress.start(12)
            base_title = app_title()
            self.title(f"{base_title} - {message}" if message else base_title)
            self.config(cursor="watch")
        else:
            self.progress.stop()
            self.progress.grid_remove()
            self.title(app_title())
            self.config(cursor="")

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
        block_ui: bool = True,
    ) -> None:
        if block_ui and self._busy:
            show_info(
                tr("app.wait_running", "Дождитесь завершения текущей операции."),
                title=tr("app.wait", "Подождите"),
            )
            return
        if block_ui:
            self._set_busy(True, busy_message)
        future: Future[Any] = self._executor.submit(task)
        poll_job_key = f"background_poll:{id(future)}"

        def _poll() -> None:
            if not future.done():
                self._schedule_after(poll_job_key, 100, _poll)
                return
            if block_ui:
                self._set_busy(False)
            error = future.exception()
            if error is not None:
                if on_error is not None:
                    on_error(error)
                else:
                    logger.exception("Background operation failed", exc_info=error)
                    show_error(str(error))
                return
            on_success(future.result())

        self._schedule_after(poll_job_key, 100, _poll)

    def _build_status_bar(self) -> ttk.Frame:
        bar = ttk.Frame(self, style="StatusBar.TFrame", padding=(PAD_SM, 3))
        bar.grid_columnconfigure(5, weight=1)
        self._online_var = tk.BooleanVar(value=False)
        online_check = ttk.Checkbutton(
            bar,
            text=tr("app.status.online", "Онлайн"),
            variable=self._online_var,
            command=self._on_online_toggle,
            style="StatusBar.TCheckbutton",
        )
        online_check.grid(row=0, column=0, sticky="w", padx=(PAD_SM, PAD_SM), pady=4)
        ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
            row=0, column=1, sticky="ns", pady=5, padx=(0, PAD_SM)
        )
        self._currency_status_label = ttk.Label(
            bar,
            text=tr("app.status.currency_offline", "Курсы: офлайн"),
            anchor="w",
            style="StatusBar.TLabel",
        )
        self._currency_status_label.grid(row=0, column=2, sticky="w", padx=(0, PAD_SM), pady=4)
        ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
            row=0, column=3, sticky="ns", pady=5, padx=(0, PAD_SM)
        )
        self._price_status_label = ttk.Label(
            bar,
            text=tr("app.status.prices_local", "Цены активов: локально"),
            anchor="w",
            style="StatusBar.TLabel",
        )
        self._price_status_label.grid(row=0, column=4, sticky="w", padx=(0, PAD_SM), pady=4)
        ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
            row=0, column=5, sticky="ns", pady=5, padx=(0, PAD_SM)
        )
        ttk.Label(
            bar,
            text=tr("common.language", "Язык:"),
            style="StatusBarMuted.TLabel",
        ).grid(row=0, column=6, sticky="w", padx=(0, 6), pady=4)
        language_codes = [code.upper() for code in get_available_languages()] or ["RU"]
        current_language = get_language().upper()
        if current_language not in language_codes:
            language_codes.insert(0, current_language)
        self._language_var = tk.StringVar(value=current_language)
        self._language_combo = ttk.Combobox(
            bar,
            textvariable=self._language_var,
            values=language_codes,
            width=max(4, min(6, max(len(code) for code in language_codes))),
            state="readonly",
            style="StatusBar.TCombobox",
        )
        self._language_combo.grid(row=0, column=7, sticky="w", padx=(0, PAD_SM), pady=2)
        self._language_combo.bind("<<ComboboxSelected>>", self._on_language_changed, add="+")
        ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
            row=0, column=8, sticky="ns", pady=5, padx=(0, PAD_SM)
        )
        ttk.Label(
            bar,
            text=tr("common.theme", "Тема:"),
            style="StatusBarMuted.TLabel",
        ).grid(row=0, column=9, sticky="w", padx=(0, 6), pady=4)
        self._theme_label_to_key = {
            tr("app.theme.light", "Светлая"): "light",
            tr("app.theme.dark", "Темная"): "dark",
        }
        theme_labels = list(self._theme_label_to_key.keys())
        current_theme_label = next(
            (label for label, key in self._theme_label_to_key.items() if key == get_theme()),
            theme_labels[0],
        )
        self._theme_var = tk.StringVar(value=current_theme_label)
        self._theme_combo = ttk.Combobox(
            bar,
            textvariable=self._theme_var,
            values=theme_labels,
            width=max(10, max(len(label) for label in theme_labels)),
            state="readonly",
            style="StatusBar.TCombobox",
        )
        self._theme_combo.grid(row=0, column=10, sticky="w", padx=(0, PAD_SM), pady=2)
        self._theme_combo.bind("<<ComboboxSelected>>", self._on_theme_changed, add="+")
        ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
            row=0, column=11, sticky="ns", pady=5, padx=(0, PAD_SM)
        )
        ttk.Label(
            bar,
            text=tr("app.status.version", "v{version}", version=__version__),
            style="StatusBarMuted.TLabel",
        ).grid(row=0, column=12, sticky="e", padx=(0, PAD_SM), pady=4)
        ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
            row=0, column=13, sticky="ns", pady=5, padx=(0, 4)
        )
        ttk.Button(
            bar,
            text=tr("app.status.hotkeys_help", "?"),
            style="StatusBar.TButton",
            command=lambda: _show_hotkey_help(self),
            takefocus=False,
            width=1,
        ).grid(row=0, column=14, sticky="e", padx=(0, 6), pady=2)
        return bar

    def _on_online_toggle(self) -> None:
        """Called when the Online/Offline toggle is clicked."""
        if self._online_var is None or self._currency_status_label is None:
            return
        if self._online_toggle_running:
            return

        enabled = self._online_var.get()
        self._online_toggle_running = True
        self._currency_status_label.config(
            text=(
                tr("app.status.currency_fetching", "Обновляем курсы...")
                if enabled
                else tr("app.status.currency_offline", "Курсы: офлайн")
            )
        )

        def task() -> None:
            self.controller.set_online_mode(enabled)

        def on_success(_result: Any) -> None:
            self._online_toggle_running = False
            self._refresh_status_bar()

        def on_error(exc: BaseException) -> None:
            self._online_toggle_running = False
            logger.warning("Online mode toggle error: %s", exc)
            self._refresh_status_bar()

        self._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message="",
            block_ui=False,
        )

    def _refresh_status_bar(self) -> None:
        """Update status bar labels from controller state."""
        if self._online_var is None or self._currency_status_label is None:
            return
        try:
            status = self.controller.get_online_status()
        except (RuntimeError, ValueError, TypeError):
            return
        self._online_var.set(self.controller.get_online_mode())
        self._currency_status_label.config(text=status["currency"])
        if self._price_status_label is not None and not self._price_status_label.cget("text"):
            self._price_status_label.config(
                text=tr("app.status.prices_local", "Цены активов: локально")
            )

    def _start_status_refresh_timer(self) -> None:
        """Refresh status bar every 60 seconds to update timestamps."""
        self._refresh_status_bar()
        self._schedule_after("status_refresh", 60_000, self._start_status_refresh_timer)

    def _apply_saved_online_mode(self) -> None:
        """Load and apply the saved online mode preference."""
        if self._online_var is None or self._currency_status_label is None:
            return
        saved = self.controller.load_online_mode_preference()
        if saved:
            self._online_var.set(True)
            self._currency_status_label.config(
                text=tr("app.status.currency_fetching", "Обновляем курсы...")
            )
            self._online_toggle_running = True

            def task() -> None:
                self.controller.set_online_mode(True)

            def on_success(_result: Any) -> None:
                self._online_toggle_running = False
                self._refresh_status_bar()

            def on_error(exc: BaseException) -> None:
                self._online_toggle_running = False
                logger.warning("Saved online mode apply error: %s", exc)
                self._refresh_status_bar()

            self._run_background(
                task,
                on_success=on_success,
                on_error=on_error,
                busy_message="",
                block_ui=False,
            )
        else:
            self._online_var.set(False)
            self._refresh_status_bar()
        self._start_status_refresh_timer()

    def _import_policy_from_ui(self, mode_label: str) -> ImportPolicy:
        mapping = {
            "operations.mode.replace": ImportPolicy.FULL_BACKUP,
            "operations.mode.legacy": ImportPolicy.LEGACY,
            "operations.mode.current_rate": ImportPolicy.CURRENT_RATE,
        }
        if mode_label in mapping:
            return mapping[mode_label]
        if mode_label == tr("operations.mode.replace", "Полная замена"):
            return ImportPolicy.FULL_BACKUP
        if mode_label == tr("operations.mode.legacy", "Наследуемый импорт"):
            return ImportPolicy.LEGACY
        if mode_label == tr("operations.mode.current_rate", "По текущему курсу"):
            return ImportPolicy.CURRENT_RATE
        return ImportPolicy.CURRENT_RATE

    def _refresh_list(self, records: list[Any] | None = None) -> None:
        if self.records_tree is None:
            return
        for iid in self.records_tree.get_children():
            self.records_tree.delete(iid)
        if self.record_tags_tree is not None:
            for iid in self.record_tags_tree.get_children():
                self.record_tags_tree.delete(iid)
        self._record_id_to_repo_index = {}
        self._record_id_to_domain_id = {}
        for kind, color in KIND_TO_FOREGROUND.items():
            try:
                self.records_tree.tag_configure(kind, foreground=color)
            except TclError:
                pass

        list_items = (
            self.controller.build_record_list_items(records)
            if records is not None
            else self.controller.build_record_list_items()
        )
        tag_color_map = {
            str(getattr(tag, "name", "") or ""): str(getattr(tag, "color", "") or "")
            for tag in self.controller.list_tags()
        }

        def _display_type_label(raw_label: str, kind: str) -> str:
            normalized = str(raw_label or "").strip().lower()
            mapping = {
                "income": tr("operations.type.income", "Доход"),
                "expense": tr("operations.type.expense", "Расход"),
                "mandatory expense": tr("operations.type.mandatory", "Обязательный расход"),
                "transfer": tr("operations.type.transfer", "Перевод"),
            }
            return mapping.get(normalized, mapping.get(kind, str(raw_label)))

        def _display_category_label(raw_category: str, kind: str) -> str:
            category = str(raw_category or "")
            if category:
                category = category.replace("\r", " ").replace("\n", " ")
                category = " ".join(category.split())
            if kind == "transfer" and category.lower().startswith("transfer #"):
                suffix = category.split("#", 1)[1].strip() if "#" in category else ""
                return tr("operations.transfer.category", "Перевод #{id}", id=suffix or "?")
            return category

        for item in list_items:
            self._record_id_to_repo_index[item.record_id] = item.repository_index
            if item.domain_record_id is not None:
                self._record_id_to_domain_id[item.record_id] = item.domain_record_id
            kind = str(getattr(item, "kind", "") or "").strip().lower()
            tags = (kind,) if foreground_for_kind(kind) else ()
            values = (
                str(item.invariant_id),
                str(item.date),
                _display_type_label(str(item.type_label), kind),
                _display_category_label(str(item.category), kind),
                f"{float(item.amount_original):.2f}",
                str(item.currency),
                f"{float(item.amount_kzt):.2f}",
                str(item.wallet_label),
                str(item.extra),
            )
            try:
                self.records_tree.insert("", "end", iid=item.record_id, values=values, tags=tags)
            except TclError:
                self.records_tree.insert("", "end", values=values, tags=tags)
            if self.record_tags_tree is not None:
                item_tags = tuple(getattr(item, "tags", ()) or ())
                tag_tree_tags: tuple[str, ...] = ()
                if item_tags:
                    first_tag = str(item_tags[0])
                    tag_color = tag_color_map.get(first_tag) or color_for_tag(first_tag)
                    tag_style = f"tag_color_{tag_color.replace('#', '').lower()}"
                    try:
                        self.record_tags_tree.tag_configure(tag_style, foreground=tag_color)
                    except TclError:
                        pass
                    tag_tree_tags = (tag_style,)
                try:
                    self.record_tags_tree.insert(
                        "",
                        "end",
                        iid=item.record_id,
                        values=(str(getattr(item, "tags_text", "") or ""),),
                        tags=tag_tree_tags,
                    )
                except TclError:
                    self.record_tags_tree.insert(
                        "",
                        "end",
                        values=(str(getattr(item, "tags_text", "") or ""),),
                        tags=tag_tree_tags,
                    )

    def _refresh_charts(self, records: list[Any] | None = None) -> None:
        if (
            self.chart_month_menu is None
            or self.chart_month_var is None
            or self.pie_month_menu is None
            or self.pie_month_var is None
            or self.chart_year_menu is None
            or self.chart_year_var is None
        ):
            return

        if records is None:
            records = self.repository.load_all()

        self._chart_refresh_suspended = True
        self._update_month_options(records)
        self._update_pie_month_options(records)
        self._update_year_options(records)
        self._chart_refresh_suspended = False

        self._draw_expense_pie(records)
        self._draw_daily_bars(records)
        self._draw_monthly_bars(records)

    def _ensure_tab_built(self, tab_key: str) -> None:
        if tab_key in self._built_tabs:
            return

        if tab_key == "infographics":
            from gui.tabs.infographics_tab import build_infographics_tab

            infographics = build_infographics_tab(
                self.tab_infographics,
                on_chart_filter_change=self._on_chart_filter_change,
                on_refresh_charts=self._refresh_charts,
                on_legend_mousewheel=self._on_legend_mousewheel,
                bind_all=self.bind_all,
                after=self.after,
                after_cancel=self.after_cancel,
            )
            self.pie_month_var = infographics.pie_month_var
            self.pie_month_menu = infographics.pie_month_menu
            self.chart_month_var = infographics.chart_month_var
            self.chart_month_menu = infographics.chart_month_menu
            self.chart_year_var = infographics.chart_year_var
            self.chart_year_menu = infographics.chart_year_menu
            self.expense_pie_canvas = infographics.expense_pie_canvas
            self.expense_legend_canvas = infographics.expense_legend_canvas
            self.expense_legend_frame = infographics.expense_legend_frame
            self.daily_bar_canvas = infographics.daily_bar_canvas
            self.monthly_bar_canvas = infographics.monthly_bar_canvas
        elif tab_key == "operations":
            from gui.tabs.operations_tab import build_operations_tab

            operations = build_operations_tab(self.tab_operations, self, self._import_formats)
            self._operations_bindings = operations
            self.records_tree = operations.records_tree
            self.record_tags_tree = operations.tags_tree
            self.refresh_operation_wallet_menu = operations.refresh_operation_wallet_menu
            self.refresh_transfer_wallet_menus = operations.refresh_transfer_wallet_menus
        elif tab_key == "reports":
            from gui.tabs.reports_tab import build_reports_tab

            self._reports_tab = build_reports_tab(self.tab_reports, self)
        elif tab_key == "analytics":
            from gui.tabs.analytics_tab import build_analytics_tab

            self._analytics_bindings = build_analytics_tab(self.tab_analytics, context=self)
        elif tab_key == "dashboard":
            from gui.tabs.dashboard_tab import build_dashboard_tab

            self._dashboard_bindings = build_dashboard_tab(self.tab_dashboard, context=self)
        elif tab_key == "budget":
            from gui.tabs.budget_tab import build_budget_tab

            self._budget_bindings = build_budget_tab(self.tab_budget, context=self)
            self.refresh_budgets = self._budget_bindings.refresh
        elif tab_key == "debts":
            from gui.tabs.debts_tab import build_debts_tab

            self._debt_bindings = build_debts_tab(self.tab_debts, context=self)
        elif tab_key == "distribution":
            from gui.tabs.distribution_tab import build_distribution_tab

            self._distribution_bindings = build_distribution_tab(
                self.tab_distribution, context=self
            )
            self.refresh_all = self._distribution_bindings.refresh
        elif tab_key == "settings":
            from gui.tabs.settings_tab import build_settings_tab

            build_settings_tab(self.tab_settings, self, self._import_formats)
        else:
            return

        self._built_tabs.add(tab_key)

    def _on_tab_changed(self, _event: tk.Event) -> None:
        if not hasattr(self, "_notebook"):
            return
        selected = self._notebook.select()
        tab_key = self._tab_keys_by_widget.get(str(selected))
        if tab_key is not None:
            self._ensure_tab_built(tab_key)
        self._schedule_notebook_underline()

    def _start_deferred_startup(self) -> None:
        if self._startup_sync_running:
            return
        self._startup_sync_running = True

        def task() -> tuple[list[Any], list[Any]]:
            created_auto_payments = self.controller.apply_mandatory_auto_payments()
            run_post_startup_maintenance()
            records = self.repository.load_all()
            return created_auto_payments, records

        def on_success(result: tuple[list[Any], list[Any]]) -> None:
            self._startup_sync_running = False
            created_auto_payments, records = result
            self._refresh_list(records=records)
            self._refresh_charts(records=records)
            self._refresh_budgets()
            self._refresh_all()
            self._apply_saved_online_mode()
            self._show_startup_auto_payment_message(created_auto_payments)

        def on_error(exc: BaseException) -> None:
            self._startup_sync_running = False
            logger.exception("Deferred startup sync failed", exc_info=exc)
            try:
                records = self.repository.load_all()
            except (RuntimeError, ValueError, TypeError, OSError) as load_error:
                log_ui_error(logger, "UI_APP_STARTUP_LOAD_FAILED", load_error)
                records = None
            if records is not None:
                self._refresh_list(records=records)
                self._refresh_charts(records=records)
            self._apply_saved_online_mode()

        self._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message="",
            block_ui=False,
        )

    def _show_startup_auto_payment_message(self, created_auto_payments: list[Any]) -> None:
        if not created_auto_payments:
            return
        logger.info("Auto-applied mandatory payments on startup: %s", len(created_auto_payments))
        details = []
        for record in created_auto_payments:
            details.append(f"- {record.category}: {record.amount_kzt:.2f} KZT ({record.date})")
        max_details = 5
        if len(details) > max_details:
            displayed = details[:max_details]
            remaining = len(details) - max_details
            displayed.append(f"+ {remaining} more")
            details_text = "\n".join(displayed)
        else:
            details_text = "\n".join(details)
        message_text = (
            tr(
                "app.autopay.summary",
                "Создано автоплатежей: {count}",
                count=len(created_auto_payments),
            )
            + "\n"
            + details_text
        )
        show_info(message_text, title=tr("app.autopay.title", "Автоплатежи применены"))

    def _refresh_wallets(self) -> None:
        """Refresh wallet list in settings tab and wallet menus in operations tab."""
        if self.refresh_wallets is not None:
            try:
                self.refresh_wallets()
            except (TclError, RuntimeError, ValueError, TypeError):
                pass
        if self.refresh_operation_wallet_menu is not None:
            try:
                self.refresh_operation_wallet_menu()
            except (TclError, RuntimeError, ValueError, TypeError):
                pass
        if self.refresh_transfer_wallet_menus is not None:
            try:
                self.refresh_transfer_wallet_menus()
            except (TclError, RuntimeError, ValueError, TypeError):
                pass

    def _refresh_budgets(self) -> None:
        if self.refresh_budgets is not None:
            try:
                self.refresh_budgets()
            except (TclError, RuntimeError, ValueError, TypeError):
                pass

    def _refresh_all(self) -> None:
        if self.refresh_all is not None:
            try:
                self.refresh_all()
            except (TclError, RuntimeError, ValueError, TypeError):
                pass

    def _on_chart_filter_change(self, *_args: Any) -> None:
        if self._chart_refresh_suspended:
            return
        self._refresh_charts()

    def _update_month_options(self, records: Any) -> None:
        if self.chart_month_menu is None or self.chart_month_var is None:
            return
        chart_month_var = self.chart_month_var
        months = extract_months(records)
        current_month = datetime.now().strftime("%Y-%m")
        if current_month not in months:
            months.append(current_month)
        months = sorted(set(months))

        self.chart_month_menu["values"] = months
        if not chart_month_var.get() or chart_month_var.get() not in months:
            chart_month_var.set(months[-1] if months else "")

    def _update_pie_month_options(self, records: Any) -> None:
        if self.pie_month_menu is None or self.pie_month_var is None:
            return
        pie_month_var = self.pie_month_var
        months = extract_months(records)
        current_month = datetime.now().strftime("%Y-%m")
        if current_month not in months:
            months.append(current_month)
        months = sorted(set(months))

        all_time_label = tr("infographics.all_time", "Все время")
        values = [all_time_label] + months
        self.pie_month_menu["values"] = values

        current_value = pie_month_var.get()
        if not current_value:
            pie_month_var.set(all_time_label)
            return
        if current_value != all_time_label and current_value not in months:
            pie_month_var.set(months[-1] if months else all_time_label)

    def _update_year_options(self, records: Any) -> None:
        if self.chart_year_menu is None or self.chart_year_var is None:
            return
        chart_year_var = self.chart_year_var
        years = extract_years(records)
        current_year = datetime.now().year
        if current_year not in years:
            years.append(current_year)
        years = sorted(set(years))

        self.chart_year_menu["values"] = [str(year) for year in years]
        if not chart_year_var.get() or int(chart_year_var.get()) not in years:
            chart_year_var.set(str(years[-1]) if years else "")

    def _draw_expense_pie(self, records: Any) -> None:
        if (
            self.pie_month_var is None
            or self.expense_pie_canvas is None
            or self.expense_legend_frame is None
            or self.expense_legend_canvas is None
        ):
            return
        palette = get_palette()
        try:
            self.expense_pie_canvas.configure(
                bg=palette.surface_elevated,
                highlightbackground=palette.border_soft,
            )
            self.expense_legend_canvas.configure(
                bg=palette.surface_elevated,
                highlightbackground=palette.border_soft,
            )
            self.expense_legend_frame.configure(bg=palette.surface_elevated)
        except TclError:
            pass

        month_value = self.pie_month_var.get()
        filtered = records
        if month_value and month_value != "all":
            filtered = self._filter_records_by_month(records, month_value)
        totals = aggregate_expenses_by_category(filtered)
        data = [(key, value) for key, value in totals.items() if value > 0]
        data.sort(key=lambda item: item[1], reverse=True)
        data = self._group_minor_categories(data, max_slices=10)

        self.expense_pie_canvas.delete("all")
        for child in self.expense_legend_frame.winfo_children():
            child.destroy()

        if not data:
            self.expense_pie_canvas.create_text(
                10,
                10,
                anchor="nw",
                text=tr("common.empty", "Нет данных для отображения"),
                fill=palette.chart_empty,
                font=("Segoe UI", 11),
            )
            return

        width = max(self.expense_pie_canvas.winfo_width(), 220)
        height = max(self.expense_pie_canvas.winfo_height(), 220)
        usable_w = max(width - 32, 120)
        usable_h = max(height - 32, 120)
        radius = max(52, min(usable_w * 0.42, usable_h * 0.48))
        center_x = max(radius + 16, min(width * 0.42, width - radius - 16))
        center_y = height / 2
        x0 = center_x - radius
        y0 = center_y - radius
        x1 = center_x + radius
        y1 = center_y + radius

        colors = self._generate_colors(len(data))

        total = sum(value for _, value in data)
        start = 0
        for index, (category, value) in enumerate(data):
            extent = (value / total) * 360
            color = colors[index % len(colors)]
            self.expense_pie_canvas.create_arc(
                x0,
                y0,
                x1,
                y1,
                start=start,
                extent=extent,
                fill=color,
                outline=palette.chart_outline,
            )
            start += extent

            cleaned_category = self._clean_category(category)
            legend_row = tk.Frame(self.expense_legend_frame, bg=palette.surface_elevated)
            legend_row.pack(fill="x", anchor="w", pady=1, padx=6)
            legend_row.grid_columnconfigure(1, weight=1)
            color_box = tk.Canvas(
                legend_row,
                width=10,
                height=10,
                highlightthickness=0,
                bg=palette.surface_elevated,
            )
            color_box.create_rectangle(0, 0, 10, 10, fill=color, outline=color)
            color_box.grid(row=0, column=0, sticky="nw", padx=(0, 6), pady=2)
            tk.Label(
                legend_row,
                text=f"{cleaned_category}: {value:.2f} KZT",
                font=("Segoe UI", 8),
                wraplength=max(96, self.expense_legend_canvas.winfo_width() - 42),
                justify="left",
                anchor="w",
                bg=palette.surface_elevated,
                fg=palette.chart_text,
            ).grid(row=0, column=1, sticky="w")

    def _group_minor_categories(
        self, data: list[tuple[str, float]], max_slices: int
    ) -> list[tuple[str, float]]:
        if len(data) <= max_slices:
            return data

        major = data[: max_slices - 1]
        other_total = sum(value for _, value in data[max_slices - 1 :])
        major.append((tr("common.other", "Other"), other_total))
        return major

    def _clean_category(self, category: str) -> str:
        """Удаляет переносы строк и лишние пробелы из категории."""
        if not category:
            return category
        cleaned = category.replace("\r", " ").replace("\n", " ")
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _filter_records_by_month(self, records: Any, month_value: str) -> list[Any]:
        try:
            year, month = map(int, month_value.split("-"))
        except (TypeError, ValueError, AttributeError):
            return records

        filtered: list[Any] = []
        for record in records:
            try:
                if isinstance(record.date, date):
                    dt = datetime.combine(record.date, datetime.min.time())
                else:
                    dt = datetime.strptime(record.date, "%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            if dt.year == year and dt.month == month:
                filtered.append(record)
        return filtered

    def _generate_colors(self, count: int) -> list[str]:
        if count <= 0:
            return []
        base_palette = list(get_palette().chart_series)

        if count <= len(base_palette):
            return base_palette[:count]

        colors = list(base_palette)
        remaining = count - len(colors)
        for idx in range(remaining):
            hue = (idx * 360 / max(1, remaining)) % 360
            saturation = 70
            lightness = 50
            colors.append(f"#{self._hsl_to_hex(hue, saturation, lightness)}")
        return colors

    def _hsl_to_hex(self, hue: float, saturation: float, lightness: float) -> str:
        saturation /= 100
        lightness /= 100

        c = (1 - abs(2 * lightness - 1)) * saturation
        x = c * (1 - abs((hue / 60) % 2 - 1))
        m = lightness - c / 2

        if 0 <= hue < 60:
            r, g, b = c, x, 0
        elif 60 <= hue < 120:
            r, g, b = x, c, 0
        elif 120 <= hue < 180:
            r, g, b = 0, c, x
        elif 180 <= hue < 240:
            r, g, b = 0, x, c
        elif 240 <= hue < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        r = int((r + m) * 255)
        g = int((g + m) * 255)
        b = int((b + m) * 255)
        return f"{r:02x}{g:02x}{b:02x}"

    def _draw_daily_bars(self, records: Any) -> None:
        if self.chart_month_var is None or self.daily_bar_canvas is None:
            return
        month_value = self.chart_month_var.get()
        if not month_value:
            return
        year, month = map(int, month_value.split("-"))
        income, expense = aggregate_daily_cashflow(records, year, month)
        labels = [str(idx + 1) for idx in range(len(income))]
        self._draw_bar_chart(self.daily_bar_canvas, labels, income, expense, max_labels=8)

    def _draw_monthly_bars(self, records: Any) -> None:
        if self.chart_year_var is None or self.monthly_bar_canvas is None:
            return
        year_value = self.chart_year_var.get()
        if not year_value:
            return
        year = int(year_value)
        income, expense = aggregate_monthly_cashflow(records, year)
        labels = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        self._draw_bar_chart(self.monthly_bar_canvas, labels, income, expense, 12)

    def _on_legend_mousewheel(self, event: tk.Event) -> None:
        if self.expense_legend_canvas is None:
            return

        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget == self.expense_legend_canvas:
                delta = -1 if event.delta > 0 else 1
                self.expense_legend_canvas.yview_scroll(delta, "units")
                return
            widget = widget.master

    def _draw_bar_chart(
        self,
        canvas: tk.Canvas,
        labels: list[str],
        income_values: list[float],
        expense_values: list[float],
        max_labels: int,
    ) -> None:
        canvas.delete("all")
        palette = get_palette()
        try:
            canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
        except TclError:
            pass
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 220)

        max_income = max(income_values) if income_values else 0
        max_expense = max(expense_values) if expense_values else 0
        max_value = max(max_income, max_expense)

        if max_value <= 0:
            canvas.create_text(
                10,
                10,
                anchor="nw",
                text=tr("common.empty", "Нет данных для отображения"),
                fill=palette.chart_empty,
                font=("Segoe UI", 11),
            )
            return

        padding = {
            "left": 34 if width < 420 else 40,
            "right": 16 if width < 420 else 20,
            "top": 20,
            "bottom": 34 if height < 240 else 30,
        }
        chart_w = width - padding["left"] - padding["right"]
        chart_h = height - padding["top"] - padding["bottom"]
        zero_y = padding["top"] + chart_h / 2
        scale = (chart_h / 2 - 10) / max_value

        canvas.create_line(
            padding["left"],
            zero_y,
            padding["left"] + chart_w,
            zero_y,
            fill=palette.chart_axis,
        )

        group_width = chart_w / max(1, len(labels))
        bar_width = max(4, min(18, group_width * 0.28))

        for idx, label in enumerate(labels):
            x_center = padding["left"] + group_width * idx + group_width / 2
            income_h = income_values[idx] * scale
            expense_h = expense_values[idx] * scale
            x1 = x_center - bar_width / 2
            x2 = x_center + bar_width / 2

            canvas.create_rectangle(
                x1,
                zero_y - income_h,
                x2,
                zero_y,
                fill=palette.chart_income,
                outline="",
            )
            canvas.create_rectangle(
                x1,
                zero_y,
                x2,
                zero_y + expense_h,
                fill=palette.chart_expense,
                outline="",
            )

            label_capacity = max(
                3,
                min(max_labels, int(chart_w // 44) if chart_w > 0 else max_labels),
            )
            label_step = max(1, len(labels) // label_capacity)
            if idx % label_step == 0 or len(labels) <= label_capacity:
                canvas.create_text(
                    x_center,
                    padding["top"] + chart_h + 10,
                    text=label,
                    fill=palette.chart_empty,
                    font=("Segoe UI", 9),
                )

        canvas.create_text(
            padding["left"],
            padding["top"] - 6,
            text=tr("operations.type.income", "Доход"),
            fill=palette.chart_income,
            anchor="sw",
            font=("Segoe UI", 9),
        )
        canvas.create_text(
            padding["left"] + 60,
            padding["top"] - 6,
            text=tr("operations.type.expense", "Расход"),
            fill=palette.chart_expense,
            anchor="sw",
            font=("Segoe UI", 9),
        )


def main() -> None:
    try:
        app = FinancialApp()
        app.mainloop()
    except KeyboardInterrupt:
        show_info(
            tr("app.closed_by_user", "Приложение закрыто пользователем."),
            title=tr("app.info", "Информация"),
        )
