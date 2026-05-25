from __future__ import annotations

from tkinter import ttk
from typing import Protocol, cast

from gui.tabs.analytics import AnalyticsTabContext
from gui.tabs.budget import BudgetTabContext
from gui.tabs.dashboard import DashboardTabContext
from gui.tabs.debts import DebtsTabContext
from gui.tabs.distribution import DistributionTabContext
from gui.tabs.mandatory import MandatoryTabContext
from gui.tabs.operations import OperationsTabContext
from gui.tabs.reports import ReportsTabContext
from gui.tabs.settings import SettingsTabContext
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


class _InfographicsTabHost(Protocol):
    tab_infographics: ttk.Frame
    pie_month_var: object
    pie_month_menu: object
    chart_month_var: object
    chart_month_menu: object
    chart_year_var: object
    chart_year_menu: object
    expense_pie_canvas: object
    expense_legend_canvas: object
    expense_legend_frame: object
    daily_bar_canvas: object
    monthly_bar_canvas: object

    def after(self, ms: int | str, func=None, *args: object) -> object: ...

    def after_cancel(self, id: str) -> None: ...

    def _on_chart_filter_change(self, *_args: object) -> None: ...

    def _refresh_charts(self, records: list[object] | None = None) -> None: ...

    def _on_legend_mousewheel(self, event: object) -> None: ...


class _OperationsTabHost(Protocol):
    tab_operations: ttk.Frame
    _import_formats: dict[str, dict[str, str]]
    _operations_bindings: object
    records_tree: ttk.Treeview | None
    record_tags_tree: ttk.Treeview | None
    refresh_operation_wallet_menu: object
    refresh_transfer_wallet_menus: object

    def _show_records_tooltip(self, event: object) -> None: ...

    def _hide_records_tooltip(self, _event: object | None = None) -> None: ...


class _ReportsTabHost(Protocol):
    tab_reports: ttk.Frame
    _reports_tab: object


class _AnalyticsTabHost(Protocol):
    tab_analytics: ttk.Frame
    _analytics_bindings: object


class _DashboardTabHost(Protocol):
    tab_dashboard: ttk.Frame
    _dashboard_bindings: object


class _BudgetTabHost(Protocol):
    tab_budget: ttk.Frame
    _budget_bindings: object
    refresh_budgets: object


class _MandatoryTabHost(Protocol):
    tab_mandatory: ttk.Frame
    _import_formats: dict[str, dict[str, str]]
    _mandatory_bindings: object
    refresh_mandatory: object


class _DebtsTabHost(Protocol):
    tab_debts: ttk.Frame
    _debt_bindings: object


class _DistributionTabHost(Protocol):
    tab_distribution: ttk.Frame
    _distribution_bindings: object
    refresh_all: object


class _SettingsTabHost(Protocol):
    tab_settings: ttk.Frame
    _settings_bindings: object


def _build_infographics_tab(app: _InfographicsTabHost) -> bool:
    from gui.tabs.infographics import build_infographics_tab

    def _after(delay_ms: int, callback) -> str:
        return str(app.after(delay_ms, callback))

    infographics = build_infographics_tab(
        app.tab_infographics,
        on_chart_filter_change=app._on_chart_filter_change,
        on_refresh_charts=app._refresh_charts,
        on_legend_mousewheel=app._on_legend_mousewheel,
        after=_after,
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


def _build_operations_tab(app: _OperationsTabHost) -> bool:
    from gui.tabs.operations import build_operations_tab

    operations = build_operations_tab(
        app.tab_operations,
        cast(OperationsTabContext, app),
        app._import_formats,
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


def _build_reports_tab(app: _ReportsTabHost) -> bool:
    from gui.tabs.reports import build_reports_tab

    app._reports_tab = build_reports_tab(app.tab_reports, cast(ReportsTabContext, app))
    return True


def _build_analytics_tab(app: _AnalyticsTabHost) -> bool:
    from gui.tabs.analytics import build_analytics_tab

    app._analytics_bindings = build_analytics_tab(
        app.tab_analytics,
        context=cast(AnalyticsTabContext, app),
    )
    return True


def _build_dashboard_tab(app: _DashboardTabHost) -> bool:
    from gui.tabs.dashboard import build_dashboard_tab

    app._dashboard_bindings = build_dashboard_tab(
        app.tab_dashboard,
        context=cast(DashboardTabContext, app),
    )
    return True


def _build_budget_tab(app: _BudgetTabHost) -> bool:
    from gui.tabs.budget import build_budget_tab

    app._budget_bindings = build_budget_tab(
        app.tab_budget,
        context=cast(BudgetTabContext, app),
    )
    app.refresh_budgets = app._budget_bindings.refresh
    return True


def _build_mandatory_tab(app: _MandatoryTabHost) -> bool:
    from gui.tabs.mandatory import build_mandatory_tab

    app._mandatory_bindings = build_mandatory_tab(
        app.tab_mandatory,
        context=cast(MandatoryTabContext, app),
        import_formats=app._import_formats,
    )
    app.refresh_mandatory = app._mandatory_bindings.refresh
    return True


def _build_debts_tab(app: _DebtsTabHost) -> bool:
    from gui.tabs.debts import build_debts_tab

    app._debt_bindings = build_debts_tab(
        app.tab_debts,
        context=cast(DebtsTabContext, app),
    )
    return True


def _build_distribution_tab(app: _DistributionTabHost) -> bool:
    from gui.tabs.distribution import build_distribution_tab

    app._distribution_bindings = build_distribution_tab(
        app.tab_distribution,
        context=cast(DistributionTabContext, app),
    )
    app.refresh_all = app._distribution_bindings.refresh
    return True


def _build_settings_tab(app: _SettingsTabHost) -> bool:
    from gui.tabs.settings import build_settings_tab

    app._settings_bindings = build_settings_tab(
        app.tab_settings,
        cast(SettingsTabContext, app),
    )
    return True


def build_tab(app: object, tab_key: str) -> bool:
    if tab_key == "infographics":
        return _build_infographics_tab(cast(_InfographicsTabHost, app))
    if tab_key == "operations":
        return _build_operations_tab(cast(_OperationsTabHost, app))
    if tab_key == "reports":
        return _build_reports_tab(cast(_ReportsTabHost, app))
    if tab_key == "analytics":
        return _build_analytics_tab(cast(_AnalyticsTabHost, app))
    if tab_key == "dashboard":
        return _build_dashboard_tab(cast(_DashboardTabHost, app))
    if tab_key == "budget":
        return _build_budget_tab(cast(_BudgetTabHost, app))
    if tab_key == "mandatory":
        return _build_mandatory_tab(cast(_MandatoryTabHost, app))
    if tab_key == "debts":
        return _build_debts_tab(cast(_DebtsTabHost, app))
    if tab_key == "distribution":
        return _build_distribution_tab(cast(_DistributionTabHost, app))
    if tab_key == "settings":
        return _build_settings_tab(cast(_SettingsTabHost, app))
    return False
