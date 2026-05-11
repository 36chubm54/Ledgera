from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def initialize_shell_state(owner: Any, *, after_jobs: Mapping[str, str]) -> None:
    owner._record_id_to_repo_index = {}
    owner._record_id_to_domain_id = {}
    owner._record_id_to_description = {}
    owner._chart_refresh_suspended = False
    owner._built_tabs = set()
    owner._analytics_bindings = None
    owner._dashboard_bindings = None
    owner._budget_bindings = None
    owner._debt_bindings = None
    owner._distribution_bindings = None
    owner._operations_bindings = None
    owner._reports_tab = None
    owner._settings_bindings = None

    owner.records_tree = None
    owner.record_tags_tree = None
    owner.refresh_operation_wallet_menu = None
    owner.refresh_transfer_wallet_menus = None
    owner.refresh_wallets = None
    owner.refresh_budgets = None
    owner.refresh_all = None
    owner._after_jobs = after_jobs
    owner._online_var = None
    owner._currency_status_label = None
    owner._price_status_label = None
    owner._display_currency_var = None
    owner._display_currency_combo = None
    owner._language_var = None
    owner._language_combo = None
    owner._theme_var = None
    owner._theme_combo = None
    owner._theme_label_to_key = {}
    owner._reload_tabs_pending = False
    owner._online_toggle_running = False
    owner._hotkey_help_dialog = None
    owner._hotkeys_registered = False
    owner._records_tooltip_window = None
    owner._records_tooltip_text = ""

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


def attach_tab_aliases(owner: Any, tab_widgets: Mapping[str, Any]) -> None:
    owner.tab_infographics = tab_widgets["infographics"]
    owner.tab_operations = tab_widgets["operations"]
    owner.tab_reports = tab_widgets["reports"]
    owner.tab_analytics = tab_widgets["analytics"]
    owner.tab_dashboard = tab_widgets["dashboard"]
    owner.tab_budget = tab_widgets["budget"]
    owner.tab_debts = tab_widgets["debts"]
    owner.tab_distribution = tab_widgets["distribution"]
    owner.tab_settings = tab_widgets["settings"]
