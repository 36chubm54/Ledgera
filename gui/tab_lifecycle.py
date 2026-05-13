from __future__ import annotations

from tkinter import ttk
from typing import Any, Protocol, cast

from gui.tabs.analytics_tab import AnalyticsTabContext
from gui.tabs.budget_tab import BudgetTabContext
from gui.tabs.dashboard_tab import DashboardTabContext
from gui.tabs.debts_tab import DebtsTabContext
from gui.tabs.distribution_tab import DistributionTabContext
from gui.tabs.mandatory_tab import MandatoryTabContext
from gui.tabs.operations_tab import OperationsTabContext
from gui.tabs.reports_tab import ReportsTabContext
from gui.tabs.settings_tab import SettingsTabContext
from gui.ui_text import get_tab_titles

TAB_ORDER = [
    "infographics",
    "operations",
    "reports",
    "analytics",
    "dashboard",
    "budget",
    "debts",
    "distribution",
    "mandatory",
    "settings",
]


def create_tab_frames(notebook: ttk.Notebook) -> dict[str, ttk.Frame]:
    return {
        "infographics": ttk.Frame(notebook),
        "operations": ttk.Frame(notebook),
        "reports": ttk.Frame(notebook),
        "analytics": ttk.Frame(notebook),
        "dashboard": ttk.Frame(notebook),
        "budget": ttk.Frame(notebook),
        "mandatory": ttk.Frame(notebook),
        "debts": ttk.Frame(notebook),
        "distribution": ttk.Frame(notebook),
        "settings": ttk.Frame(notebook),
    }


def attach_tabs(notebook: ttk.Notebook, tab_widgets: dict[str, ttk.Frame]) -> dict[str, str]:
    tab_titles = get_tab_titles()
    for key in TAB_ORDER:
        notebook.add(tab_widgets[key], text=tab_titles[key])
    return {str(tab_widgets[key]): key for key in TAB_ORDER}


class TabBuildContext(Protocol):
    controller: Any
    repository: Any
    currency: Any
    _import_formats: dict[str, dict[str, str]]
    _record_id_to_repo_index: dict[str, int]
    _record_id_to_domain_id: dict[str, int]
    refresh_budgets: Any
    refresh_all: Any
    tab_infographics: ttk.Frame
    tab_operations: ttk.Frame
    tab_reports: ttk.Frame
    tab_analytics: ttk.Frame
    tab_dashboard: ttk.Frame
    tab_budget: ttk.Frame
    tab_mandatory: ttk.Frame
    tab_debts: ttk.Frame
    tab_distribution: ttk.Frame
    tab_settings: ttk.Frame
    pie_month_var: Any
    pie_month_menu: Any
    chart_month_var: Any
    chart_month_menu: Any
    chart_year_var: Any
    chart_year_menu: Any
    expense_pie_canvas: Any
    expense_legend_canvas: Any
    expense_legend_frame: Any
    daily_bar_canvas: Any
    monthly_bar_canvas: Any
    _operations_bindings: Any
    records_tree: Any
    record_tags_tree: Any
    refresh_operation_wallet_menu: Any
    refresh_transfer_wallet_menus: Any
    _reports_tab: Any
    _analytics_bindings: Any
    _dashboard_bindings: Any
    _budget_bindings: Any
    _mandatory_bindings: Any
    _debt_bindings: Any
    _distribution_bindings: Any
    _settings_bindings: Any
    refresh_wallets: Any
    refresh_mandatory: Any

    def bind_all(
        self, sequence: str | None = None, func: Any | None = None, add: str | None = None
    ) -> Any: ...

    def after(self, ms: int | str, func: Any | None = None, *args: object) -> Any: ...

    def after_cancel(self, id: str) -> None: ...

    def _on_chart_filter_change(self, *_args: Any) -> None: ...

    def _refresh_charts(self, records: list[Any] | None = None) -> None: ...

    def _refresh_list(self) -> None: ...

    def _refresh_wallets(self) -> None: ...

    def _refresh_budgets(self) -> None: ...

    def _refresh_all(self) -> None: ...

    def _run_background(self, task: Any, **kwargs: Any) -> None: ...

    def _import_policy_from_ui(self, mode_label: str) -> Any: ...

    def _on_legend_mousewheel(self, event: Any) -> None: ...

    def _show_records_tooltip(self, event: Any) -> None: ...

    def _hide_records_tooltip(self, _event: object | None = None) -> None: ...


def build_tab(app: Any, tab_key: str) -> bool:
    app = cast(TabBuildContext, app)
    if tab_key == "infographics":
        from gui.tabs.infographics_tab import build_infographics_tab

        infographics = build_infographics_tab(
            app.tab_infographics,
            on_chart_filter_change=app._on_chart_filter_change,
            on_refresh_charts=app._refresh_charts,
            on_legend_mousewheel=app._on_legend_mousewheel,
            bind_all=app.bind_all,
            after=app.after,
            after_cancel=app.after_cancel,
        )
        app.pie_month_var = infographics.pie_month_var
        app.pie_month_menu = infographics.pie_month_menu
        app.chart_month_var = infographics.chart_month_var
        app.chart_month_menu = infographics.chart_month_menu
        app.chart_year_var = infographics.chart_year_var
        app.chart_year_menu = infographics.chart_year_menu
        app.expense_pie_canvas = infographics.expense_pie_canvas
        app.expense_legend_canvas = infographics.expense_legend_canvas
        app.expense_legend_frame = infographics.expense_legend_frame
        app.daily_bar_canvas = infographics.daily_bar_canvas
        app.monthly_bar_canvas = infographics.monthly_bar_canvas
        return True
    if tab_key == "operations":
        from gui.tabs.operations_tab import build_operations_tab

        operations = build_operations_tab(
            app.tab_operations, cast(OperationsTabContext, app), app._import_formats
        )
        app._operations_bindings = operations
        app.records_tree = operations.records_tree
        app.record_tags_tree = operations.tags_tree
        app.records_tree.bind("<Motion>", app._show_records_tooltip, add="+")
        app.records_tree.bind("<Leave>", app._hide_records_tooltip, add="+")
        app.records_tree.bind("<ButtonPress-1>", app._hide_records_tooltip, add="+")
        app.records_tree.bind("<MouseWheel>", app._hide_records_tooltip, add="+")
        app.refresh_operation_wallet_menu = operations.refresh_operation_wallet_menu
        app.refresh_transfer_wallet_menus = operations.refresh_transfer_wallet_menus
        return True
    if tab_key == "reports":
        from gui.tabs.reports_tab import build_reports_tab

        app._reports_tab = build_reports_tab(app.tab_reports, cast(ReportsTabContext, app))
        return True
    if tab_key == "analytics":
        from gui.tabs.analytics_tab import build_analytics_tab

        app._analytics_bindings = build_analytics_tab(
            app.tab_analytics, context=cast(AnalyticsTabContext, app)
        )
        return True
    if tab_key == "dashboard":
        from gui.tabs.dashboard_tab import build_dashboard_tab

        app._dashboard_bindings = build_dashboard_tab(
            app.tab_dashboard, context=cast(DashboardTabContext, app)
        )
        return True
    if tab_key == "budget":
        from gui.tabs.budget_tab import build_budget_tab

        app._budget_bindings = build_budget_tab(app.tab_budget, context=cast(BudgetTabContext, app))
        app.refresh_budgets = app._budget_bindings.refresh
        return True
    if tab_key == "mandatory":
        from gui.tabs.mandatory_tab import build_mandatory_tab

        app._mandatory_bindings = build_mandatory_tab(
            app.tab_mandatory,
            context=cast(MandatoryTabContext, app),
            import_formats=app._import_formats,
        )
        app.refresh_mandatory = app._mandatory_bindings.refresh
        return True
    if tab_key == "debts":
        from gui.tabs.debts_tab import build_debts_tab

        app._debt_bindings = build_debts_tab(app.tab_debts, context=cast(DebtsTabContext, app))
        return True
    if tab_key == "distribution":
        from gui.tabs.distribution_tab import build_distribution_tab

        app._distribution_bindings = build_distribution_tab(
            app.tab_distribution, context=cast(DistributionTabContext, app)
        )
        app.refresh_all = app._distribution_bindings.refresh
        return True
    if tab_key == "settings":
        from gui.tabs.settings_tab import build_settings_tab

        app._settings_bindings = build_settings_tab(
            app.tab_settings, cast(SettingsTabContext, app), app._import_formats
        )
        return True
    return False
