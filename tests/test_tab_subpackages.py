from __future__ import annotations

import importlib


def test_settings_reports_and_mandatory_subpackages_are_importable() -> None:
    analytics_pkg = importlib.import_module("gui.tabs.analytics")
    analytics_builder = importlib.import_module("gui.tabs.analytics.core.builder")
    analytics_contracts = importlib.import_module("gui.tabs.analytics.core.contracts")
    analytics_refresh = importlib.import_module("gui.tabs.analytics.core.refresh")
    analytics_render = importlib.import_module("gui.tabs.analytics.core.render")
    analytics_summary = importlib.import_module("gui.tabs.analytics.core.summary_section")
    analytics_breakdown = importlib.import_module("gui.tabs.analytics.core.breakdown_section")
    analytics_monthly = importlib.import_module("gui.tabs.analytics.core.monthly_section")
    budget_pkg = importlib.import_module("gui.tabs.budget")
    budget_builder = importlib.import_module("gui.tabs.budget.core.builder")
    budget_actions = importlib.import_module("gui.tabs.budget.support.actions")
    budget_list = importlib.import_module("gui.tabs.budget.support.list_section")
    debts_pkg = importlib.import_module("gui.tabs.debts")
    debts_builder = importlib.import_module("gui.tabs.debts.core.builder")
    debts_forms = importlib.import_module("gui.tabs.debts.support.forms")
    debts_render = importlib.import_module("gui.tabs.debts.support.render")
    debts_actions = importlib.import_module("gui.tabs.debts.support.actions")
    debts_keyboard = importlib.import_module("gui.tabs.debts.support.keyboard")
    debts_history = importlib.import_module("gui.tabs.debts.support.history_section")
    distribution_pkg = importlib.import_module("gui.tabs.distribution")
    distribution_builder = importlib.import_module("gui.tabs.distribution.core.builder")
    distribution_formatting = importlib.import_module("gui.tabs.distribution.support.formatting")
    distribution_prompts = importlib.import_module("gui.tabs.distribution.support.prompts")
    distribution_results_data = importlib.import_module(
        "gui.tabs.distribution.support.results_data"
    )
    distribution_structure = importlib.import_module(
        "gui.tabs.distribution.support.structure_section"
    )
    distribution_results = importlib.import_module("gui.tabs.distribution.support.results_section")
    distribution_actions = importlib.import_module("gui.tabs.distribution.support.actions")
    settings_pkg = importlib.import_module("gui.tabs.settings")
    settings_wallets = importlib.import_module("gui.tabs.settings.wallets_section")
    settings_currency = importlib.import_module("gui.tabs.settings.currency_section")
    settings_backup = importlib.import_module("gui.tabs.settings.backup_section")
    mandatory_builder = importlib.import_module("gui.tabs.mandatory.core.builder")
    mandatory_section = importlib.import_module("gui.tabs.mandatory.support.section")
    mandatory_actions = importlib.import_module("gui.tabs.mandatory.support.actions")
    mandatory_forms = importlib.import_module("gui.tabs.mandatory.support.forms")
    mandatory_tree = importlib.import_module("gui.tabs.mandatory.support.tree_section")
    mandatory_keyboard = importlib.import_module("gui.tabs.mandatory.support.keyboard")
    reports_pkg = importlib.import_module("gui.tabs.reports")
    reports_builder = importlib.import_module("gui.tabs.reports.core.builder")
    reports_controller = importlib.import_module("gui.tabs.reports.core.controller")
    reports_layout = importlib.import_module("gui.tabs.reports.core.layout")
    reports_render = importlib.import_module("gui.tabs.reports.core.render")
    dashboard_pkg = importlib.import_module("gui.tabs.dashboard")
    dashboard_builder = importlib.import_module("gui.tabs.dashboard.core.builder")
    dashboard_contracts = importlib.import_module("gui.tabs.dashboard.core.contracts")
    dashboard_actions = importlib.import_module("gui.tabs.dashboard.support.actions")
    dashboard_dialogs = importlib.import_module("gui.tabs.dashboard.support.dialogs")
    dashboard_render = importlib.import_module("gui.tabs.dashboard.support.render")
    infographics_pkg = importlib.import_module("gui.tabs.infographics")
    infographics_builder = importlib.import_module("gui.tabs.infographics.core.builder")
    infographics_contracts = importlib.import_module("gui.tabs.infographics.core.contracts")
    infographics_pie = importlib.import_module("gui.tabs.infographics.support.pie_section")
    infographics_bar = importlib.import_module("gui.tabs.infographics.support.bar_section")
    infographics_refresh = importlib.import_module("gui.tabs.infographics.support.refresh")

    assert analytics_pkg.build_analytics_tab is analytics_builder.build_analytics_tab
    assert analytics_pkg.AnalyticsTabBindings is analytics_contracts.AnalyticsTabBindings
    assert analytics_pkg.AnalyticsTabContext is analytics_contracts.AnalyticsTabContext
    assert analytics_pkg._draw_breakdown_pie is analytics_render._draw_breakdown_pie
    assert analytics_pkg._draw_net_worth_line is analytics_render._draw_net_worth_line
    assert hasattr(analytics_render, "_draw_breakdown_pie")
    assert hasattr(analytics_render, "_draw_net_worth_line")
    assert hasattr(analytics_refresh, "refresh_analytics")
    assert hasattr(analytics_summary, "build_summary_section")
    assert hasattr(analytics_breakdown, "build_breakdown_section")
    assert hasattr(analytics_monthly, "build_monthly_section")

    assert budget_pkg.build_budget_tab is budget_builder.build_budget_tab
    assert hasattr(budget_pkg, "BudgetTabBindings")
    assert hasattr(budget_pkg, "BudgetTabContext")
    assert hasattr(budget_actions, "_normalize_budget_limit_input")
    assert hasattr(budget_actions, "_visual_budget_state")
    assert hasattr(budget_list, "_draw_progress_bars")

    assert debts_pkg.build_debts_tab is not None
    assert hasattr(debts_pkg, "DebtsTabBindings")
    assert hasattr(debts_pkg, "DebtsTabContext")
    assert debts_pkg.refresh_debts_views is not None
    assert debts_pkg._segment_widths is debts_render._segment_widths
    assert debts_pkg._draw_debt_progress is debts_render._draw_debt_progress
    assert hasattr(debts_pkg, "messagebox")
    assert hasattr(debts_builder, "build_debts_tab")
    assert hasattr(debts_render, "_segment_widths")
    assert hasattr(debts_render, "_draw_debt_progress")
    assert hasattr(debts_actions, "create_debt_action")
    assert hasattr(debts_forms, "build_create_form")
    assert hasattr(debts_keyboard, "bind_control_shortcuts")
    assert hasattr(debts_history, "refresh_history")

    assert distribution_pkg.build_distribution_tab is distribution_builder.build_distribution_tab
    assert distribution_pkg.DistributionTabBindings is not None
    assert distribution_pkg.DistributionTabContext is not None
    assert (
        distribution_pkg._snapshot_values_to_display
        is distribution_formatting._snapshot_values_to_display
    )
    assert distribution_pkg._parse_snapshot_amount is distribution_formatting._parse_snapshot_amount
    assert distribution_pkg._fmt_amount is distribution_formatting._fmt_amount
    assert distribution_pkg._default_start is distribution_formatting._default_start
    assert distribution_pkg._default_end is distribution_formatting._default_end
    assert hasattr(distribution_formatting, "_snapshot_values_to_display")
    assert hasattr(distribution_prompts, "DistributionActionUi")
    assert hasattr(distribution_results_data, "compose_column_meta")
    assert hasattr(distribution_structure, "build_structure_section")
    assert hasattr(distribution_results, "refresh_results")
    assert hasattr(distribution_actions, "toggle_fixed_row")

    assert hasattr(settings_pkg, "build_settings_tab")
    assert hasattr(settings_pkg, "SettingsTabBindings")
    assert hasattr(settings_pkg, "SettingsTabContext")
    assert hasattr(settings_wallets, "build_wallets_section")
    assert hasattr(settings_currency, "build_currency_section")
    assert hasattr(settings_currency, "build_audit_section")
    assert hasattr(settings_backup, "build_backup_section")

    assert hasattr(mandatory_builder, "build_mandatory_tab")
    assert hasattr(mandatory_section, "build_mandatory_section")
    assert hasattr(mandatory_actions, "save_add_to_records")
    assert hasattr(mandatory_forms, "build_add_mandatory_panel")
    assert hasattr(mandatory_tree, "build_mandatory_tree")
    assert hasattr(mandatory_keyboard, "bind_focus_navigation")

    operations_pkg = importlib.import_module("gui.tabs.operations")
    operations_builder = importlib.import_module("gui.tabs.operations.core.builder")
    operations_form = importlib.import_module("gui.tabs.operations.core.form_section")
    operations_journal = importlib.import_module("gui.tabs.operations.core.journal_section")
    operations_inline = importlib.import_module("gui.tabs.operations.core.inline_editors")
    operations_transfer = importlib.import_module("gui.tabs.operations.core.transfer_section")

    assert reports_pkg.build_reports_tab is reports_builder.build_reports_tab
    assert hasattr(reports_builder, "ReportsFrame")
    assert hasattr(reports_controller, "ReportsController")
    assert hasattr(reports_layout, "build_reports_layout")
    assert hasattr(reports_render, "refresh_operations_table")

    assert dashboard_pkg.build_dashboard_tab is dashboard_builder.build_dashboard_tab
    assert dashboard_pkg.DashboardTabBindings is dashboard_contracts.DashboardTabBindings
    assert dashboard_pkg.DashboardTabContext is dashboard_contracts.DashboardTabContext
    assert dashboard_pkg._prepare_goal_payload is dashboard_actions._prepare_goal_payload
    assert hasattr(dashboard_dialogs, "show_asset_editor_dialog")
    assert hasattr(dashboard_dialogs, "show_bulk_asset_snapshot_dialog")
    assert hasattr(dashboard_dialogs, "show_create_goal_dialog")
    assert hasattr(dashboard_dialogs, "show_manage_assets_dialog")
    assert hasattr(dashboard_render, "_draw_trend")

    assert operations_pkg.build_operations_tab is operations_builder.build_operations_tab
    assert hasattr(operations_form, "build_operation_form_section")
    assert hasattr(operations_journal, "build_journal_section")
    assert hasattr(operations_inline, "build_inline_editors")
    assert hasattr(operations_transfer, "build_transfer_section")

    assert infographics_pkg.build_infographics_tab is infographics_builder.build_infographics_tab
    assert (
        infographics_pkg.InfographicsTabBindings is infographics_contracts.InfographicsTabBindings
    )
    assert infographics_pkg.draw_expense_pie is infographics_pie.draw_expense_pie
    assert infographics_pkg.update_pie_month_options is infographics_pie.update_pie_month_options
    assert (
        infographics_pkg._legend_category_max_width is infographics_pie._legend_category_max_width
    )
    assert hasattr(infographics_bar, "draw_bar_chart")
    assert hasattr(infographics_refresh, "refresh_infographics_charts")
