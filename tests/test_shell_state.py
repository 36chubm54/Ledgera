from __future__ import annotations

import logging
from tkinter import TclError
from types import SimpleNamespace
from unittest.mock import Mock

from gui.shell.core.state import (
    apply_saved_ui_preferences,
    assign_status_bar_state,
    rebuild_status_bar,
    reset_tab_bindings_state,
)
from gui.status_bar_builder import StatusBarBuildResult


class _SavedPreferencesController:
    def load_language_preference(self) -> str | None:
        return "ru"

    def load_theme_preference(self) -> str | None:
        return "dark"


def test_apply_saved_ui_preferences_applies_saved_language_and_theme() -> None:
    owner = object()
    set_language = Mock()
    bootstrap_ui = Mock()

    apply_saved_ui_preferences(
        owner,
        controller=_SavedPreferencesController(),
        set_language=set_language,
        bootstrap_ui=bootstrap_ui,
        get_theme=lambda: "light",
        default_theme="light",
        logger=Mock(),
    )

    set_language.assert_called_once_with("ru")
    bootstrap_ui.assert_called_once_with(owner, "dark")


def test_reset_tab_bindings_state_clears_shell_bindings() -> None:
    owner = SimpleNamespace(
        records_tree=object(),
        record_tags_tree=object(),
        refresh_operation_wallet_menu=object(),
        refresh_transfer_wallet_menus=object(),
        refresh_wallets=object(),
        refresh_budgets=object(),
        refresh_all=object(),
        _operations_bindings=object(),
        _reports_tab=object(),
        _analytics_bindings=object(),
        _dashboard_bindings=object(),
        _budget_bindings=object(),
        _debt_bindings=object(),
        _distribution_bindings=object(),
        _settings_bindings=object(),
        pie_month_var=object(),
        pie_month_menu=object(),
        chart_month_var=object(),
        chart_month_menu=object(),
        chart_year_var=object(),
        chart_year_menu=object(),
        expense_pie_canvas=object(),
        expense_legend_canvas=object(),
        expense_legend_frame=object(),
        daily_bar_canvas=object(),
        monthly_bar_canvas=object(),
    )
    hide_records_tooltip = Mock()

    reset_tab_bindings_state(owner, hide_records_tooltip=hide_records_tooltip)

    hide_records_tooltip.assert_called_once()
    assert owner.records_tree is None
    assert owner._settings_bindings is None
    assert owner.monthly_bar_canvas is None


def test_assign_status_bar_state_copies_builder_result_to_owner() -> None:
    owner = SimpleNamespace()
    frame = Mock()
    result = StatusBarBuildResult(
        frame=frame,
        online_var=Mock(),
        currency_status_label=Mock(),
        price_status_label=Mock(),
        display_currency_var=Mock(),
        display_currency_combo=Mock(),
        language_var=Mock(),
        language_combo=Mock(),
        theme_var=Mock(),
        theme_combo=Mock(),
        theme_label_to_key={"Темная": "dark"},
    )

    assigned_frame = assign_status_bar_state(owner, result)

    assert assigned_frame is frame
    assert owner._theme_label_to_key == {"Темная": "dark"}
    assert owner._display_currency_combo is result.display_currency_combo


def test_rebuild_status_bar_replaces_existing_frame_and_refreshes() -> None:
    old_frame = Mock()
    new_frame = Mock()
    owner = SimpleNamespace(_status_bar=old_frame)
    refresh_status_bar = Mock()

    result = StatusBarBuildResult(
        frame=new_frame,
        online_var=Mock(),
        currency_status_label=Mock(),
        price_status_label=Mock(),
        display_currency_var=Mock(),
        display_currency_combo=Mock(),
        language_var=Mock(),
        language_combo=Mock(),
        theme_var=Mock(),
        theme_combo=Mock(),
        theme_label_to_key={},
    )

    frame = rebuild_status_bar(
        owner,
        build_status_bar_result=lambda _owner: result,
        refresh_status_bar=refresh_status_bar,
    )

    old_frame.destroy.assert_called_once()
    new_frame.grid.assert_called_once()
    refresh_status_bar.assert_called_once()
    assert frame is new_frame


def test_rebuild_status_bar_logs_expected_cleanup_failure(caplog) -> None:
    old_frame = Mock()
    old_frame.destroy.side_effect = TclError("status bar already gone")
    new_frame = Mock()
    owner = SimpleNamespace(_status_bar=old_frame)

    result = StatusBarBuildResult(
        frame=new_frame,
        online_var=Mock(),
        currency_status_label=Mock(),
        price_status_label=Mock(),
        display_currency_var=Mock(),
        display_currency_combo=Mock(),
        language_var=Mock(),
        language_combo=Mock(),
        theme_var=Mock(),
        theme_combo=Mock(),
        theme_label_to_key={},
    )

    caplog.set_level(logging.DEBUG)

    rebuild_status_bar(
        owner,
        build_status_bar_result=lambda _owner: result,
        refresh_status_bar=Mock(),
    )

    assert "Existing status bar cleanup skipped" in caplog.text
    assert "status bar already gone" in caplog.text
