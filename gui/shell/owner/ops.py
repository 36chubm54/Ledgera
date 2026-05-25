from __future__ import annotations

from typing import Any

from domain.import_policy import ImportPolicy
from gui.shell.core.lifecycle import ensure_tab_built, handle_tab_changed
from gui.shell.core.records import (
    hide_owner_records_tooltip,
    refresh_owner_record_views,
    show_owner_records_tooltip,
)
from gui.shell.core.refresh import (
    refresh_owner_all,
    refresh_owner_budgets,
    refresh_owner_display_currency_views,
    refresh_owner_wallet_views,
)
from gui.shell.core.support import resolve_import_policy
from gui.status_bar_coordinator import StatusBarCoordinator
from gui.tabs.infographics.support.refresh import (
    handle_chart_filter_change,
    refresh_owner_infographics,
    scroll_owner_legend_canvas,
)


def on_owner_online_toggle(status: StatusBarCoordinator) -> None:
    status.on_online_toggle()


def refresh_owner_status_bar(status: StatusBarCoordinator) -> None:
    status.refresh_status_bar()


def on_owner_display_currency_changed(owner: Any) -> None:
    from gui.shell.owner.preferences import handle_owner_display_currency_change

    handle_owner_display_currency_change(owner)


def start_owner_status_refresh_timer(status: StatusBarCoordinator) -> None:
    status.start_status_refresh_timer()


def apply_owner_saved_online_mode(status: StatusBarCoordinator) -> None:
    status.apply_saved_online_mode()


def owner_import_policy_from_ui(mode_label: str) -> ImportPolicy:
    return resolve_import_policy(mode_label)


def refresh_owner_list(owner: Any, records: list[Any] | None = None) -> None:
    refresh_owner_record_views(owner, records=records)


def hide_owner_tooltip(owner: Any, event: object | None = None) -> None:
    hide_owner_records_tooltip(owner, event)


def show_owner_tooltip(owner: Any, event: Any) -> None:
    show_owner_records_tooltip(owner, event)


def refresh_owner_charts(owner: Any, records: list[Any] | None = None) -> None:
    refresh_owner_infographics(
        owner,
        records=records,
        load_fresh=records is None,
    )


def ensure_owner_tab_built(owner: Any, tab_key: str, *, build_tab_for_key: Any) -> None:
    ensure_tab_built(
        owner._built_tabs,
        tab_key,
        build_tab_for_key=build_tab_for_key,
    )


def on_owner_tab_changed(owner: Any) -> None:
    if not hasattr(owner, "_notebook"):
        return
    handle_tab_changed(
        owner._notebook,
        owner._tab_keys_by_widget,
        ensure_tab_built_for_key=owner._ensure_tab_built,
        schedule_notebook_underline=owner._schedule_notebook_underline,
    )


def refresh_owner_wallet_shell(owner: Any) -> None:
    refresh_owner_wallet_views(owner)


def refresh_owner_budget_shell(owner: Any) -> None:
    refresh_owner_budgets(owner)


def refresh_owner_all_shell(owner: Any) -> None:
    refresh_owner_all(owner)


def on_owner_chart_filter_change(owner: Any) -> None:
    handle_chart_filter_change(owner)


def on_owner_legend_mousewheel(owner: Any, event: Any) -> None:
    scroll_owner_legend_canvas(owner, event)


def refresh_owner_display_currency_shell(owner: Any) -> None:
    refresh_owner_display_currency_views(owner)
