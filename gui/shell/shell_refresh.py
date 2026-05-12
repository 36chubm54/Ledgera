from __future__ import annotations

from collections.abc import Callable, Iterable
from tkinter import TclError
from typing import Any

_SAFE_EXCEPTIONS = (TclError, RuntimeError, ValueError, TypeError)


def safe_call(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        callback()
    except _SAFE_EXCEPTIONS:
        pass


def safe_refresh_binding(binding: Any) -> None:
    refresh = getattr(binding, "refresh", None)
    if callable(refresh):
        safe_call(refresh)


def safe_refresh_reports_views(reports_tab: Any) -> None:
    for attr in ("_refresh_summary_only", "_refresh_operations_table", "_refresh_monthly_table"):
        callback = getattr(reports_tab, attr, None)
        if callable(callback):
            safe_call(callback)


def refresh_theme_surfaces(
    *,
    refresh_status_bar: Callable[[], None],
    has_records_tree: bool,
    refresh_list: Callable[[], None],
    refresh_tree_zebra: Callable[[], None],
    infographics_built: bool,
    refresh_charts: Callable[[], None],
    refresh_budgets: Callable[[], None] | None,
    refresh_all: Callable[[], None] | None,
    bindings: Iterable[Any],
) -> None:
    safe_call(refresh_status_bar)
    if has_records_tree:
        safe_call(refresh_list)
        safe_call(refresh_tree_zebra)
    if infographics_built:
        safe_call(refresh_charts)
    for binding in bindings:
        safe_refresh_binding(binding)
    safe_call(refresh_budgets)
    safe_call(refresh_all)


def refresh_owner_theme_surfaces(owner: Any, *, refresh_tree_zebra: Callable[[], None]) -> None:
    refresh_theme_surfaces(
        refresh_status_bar=owner._refresh_status_bar,
        has_records_tree=owner.records_tree is not None,
        refresh_list=owner._refresh_list,
        refresh_tree_zebra=refresh_tree_zebra,
        infographics_built="infographics" in owner._built_tabs,
        refresh_charts=owner._refresh_charts,
        refresh_budgets=owner.refresh_budgets,
        refresh_all=owner.refresh_all,
        bindings=(
            owner._analytics_bindings,
            owner._dashboard_bindings,
            owner._debt_bindings,
        ),
    )


def refresh_display_currency_views(
    *,
    refresh_status_bar: Callable[[], None],
    has_records_tree: bool,
    refresh_list: Callable[[], None],
    infographics_built: bool,
    refresh_charts: Callable[[], None],
    reports_tab: Any,
    bindings: Iterable[Any],
) -> None:
    safe_call(refresh_status_bar)
    if has_records_tree:
        safe_call(refresh_list)
    if infographics_built:
        safe_call(refresh_charts)
    safe_refresh_reports_views(reports_tab)
    for binding in bindings:
        safe_refresh_binding(binding)


def refresh_owner_display_currency_views(owner: Any) -> None:
    refresh_display_currency_views(
        refresh_status_bar=owner._refresh_status_bar,
        has_records_tree=owner.records_tree is not None,
        refresh_list=owner._refresh_list,
        infographics_built="infographics" in owner._built_tabs,
        refresh_charts=owner._refresh_charts,
        reports_tab=owner._reports_tab,
        bindings=(
            owner._analytics_bindings,
            owner._dashboard_bindings,
            owner._budget_bindings,
            owner._debt_bindings,
            owner._distribution_bindings,
            owner._settings_bindings,
        ),
    )


def refresh_wallet_views(
    *,
    refresh_wallets: Callable[[], object] | None,
    refresh_operation_wallet_menu: Callable[[], object] | None,
    refresh_transfer_wallet_menus: Callable[[], object] | None,
) -> None:
    safe_call(refresh_wallets)
    safe_call(refresh_operation_wallet_menu)
    safe_call(refresh_transfer_wallet_menus)


def refresh_owner_wallet_views(owner: Any) -> None:
    refresh_wallet_views(
        refresh_wallets=owner.refresh_wallets,
        refresh_operation_wallet_menu=owner.refresh_operation_wallet_menu,
        refresh_transfer_wallet_menus=owner.refresh_transfer_wallet_menus,
    )


def refresh_optional_view(callback: Callable[[], object] | None) -> None:
    safe_call(callback)


def refresh_owner_budgets(owner: Any) -> None:
    refresh_optional_view(owner.refresh_budgets)


def refresh_owner_all(owner: Any) -> None:
    refresh_optional_view(owner.refresh_all)


def should_refresh_charts(chart_refresh_suspended: bool) -> bool:
    return not chart_refresh_suspended


def scroll_legend_canvas(
    *,
    legend_canvas: Any,
    winfo_containing: Callable[[int, int], Any],
    event: Any,
) -> bool:
    if legend_canvas is None:
        return False

    widget = winfo_containing(event.x_root, event.y_root)
    while widget is not None:
        if widget == legend_canvas:
            delta = -1 if event.delta > 0 else 1
            legend_canvas.yview_scroll(delta, "units")
            return True
        widget = widget.master
    return False
