from __future__ import annotations

import logging
from collections.abc import Callable
from tkinter import TclError, ttk
from typing import Any, Protocol

from gui.status_bar_builder import StatusBarBuildResult


class SavedPreferencesController(Protocol):
    def load_language_preference(self) -> str | None: ...

    def load_theme_preference(self) -> str | None: ...


def apply_saved_ui_preferences(
    owner: Any,
    *,
    controller: SavedPreferencesController,
    set_language: Callable[[str], Any],
    bootstrap_ui: Callable[[Any, str], Any],
    get_theme: Callable[[], str],
    default_theme: str,
    logger: logging.Logger,
) -> None:
    saved_language = controller.load_language_preference()
    if saved_language:
        try:
            set_language(saved_language)
        except ValueError:
            logger.warning("Unsupported saved language preference: %s", saved_language)
    saved_theme = controller.load_theme_preference()
    bootstrap_ui(owner, saved_theme or get_theme() or default_theme)


def reset_tab_bindings_state(owner: Any, *, hide_records_tooltip: Callable[[], None]) -> None:
    hide_records_tooltip()
    owner.records_tree = None
    owner.record_tags_tree = None
    owner.refresh_operation_wallet_menu = None
    owner.refresh_transfer_wallet_menus = None
    owner.refresh_wallets = None
    owner.refresh_budgets = None
    owner.refresh_all = None
    owner._operations_bindings = None
    owner._reports_tab = None
    owner._analytics_bindings = None
    owner._dashboard_bindings = None
    owner._budget_bindings = None
    owner._debt_bindings = None
    owner._distribution_bindings = None
    owner._settings_bindings = None
    owner.pie_month_var = None
    owner.pie_month_menu = None
    owner.chart_month_var = None
    owner.chart_month_menu = None
    owner.chart_year_var = None
    owner.chart_year_menu = None
    owner.expense_pie_canvas = None
    owner.expense_legend_canvas = None
    owner.expense_legend_frame = None
    owner.daily_bar_canvas = None
    owner.monthly_bar_canvas = None


def assign_status_bar_state(owner: Any, result: StatusBarBuildResult) -> ttk.Frame:
    owner._online_var = result.online_var
    owner._currency_status_label = result.currency_status_label
    owner._price_status_label = result.price_status_label
    owner._display_currency_var = result.display_currency_var
    owner._display_currency_combo = result.display_currency_combo
    owner._language_var = result.language_var
    owner._language_combo = result.language_combo
    owner._theme_var = result.theme_var
    owner._theme_combo = result.theme_combo
    owner._theme_label_to_key = result.theme_label_to_key
    return result.frame


def rebuild_status_bar(
    owner: Any,
    *,
    build_status_bar_result: Callable[[Any], StatusBarBuildResult],
    refresh_status_bar: Callable[[], None],
) -> ttk.Frame:
    existing = getattr(owner, "_status_bar", None)
    if existing is not None:
        try:
            existing.destroy()
        except (TclError, RuntimeError):
            pass
    frame = assign_status_bar_state(owner, build_status_bar_result(owner))
    frame.grid(row=2, column=0, sticky="ew")
    refresh_status_bar()
    return frame
