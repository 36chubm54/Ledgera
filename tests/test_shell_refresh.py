from __future__ import annotations

from types import SimpleNamespace

from gui.shell.shell_refresh import (
    refresh_display_currency_views,
    refresh_optional_view,
    refresh_owner_all,
    refresh_owner_budgets,
    refresh_owner_display_currency_views,
    refresh_owner_theme_surfaces,
    refresh_owner_wallet_views,
    refresh_theme_surfaces,
    refresh_wallet_views,
    safe_call,
    safe_refresh_reports_views,
    scroll_legend_canvas,
    should_refresh_charts,
)


def test_safe_call_ignores_none_and_runtime_errors() -> None:
    safe_call(None)
    safe_call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))


def test_safe_call_propagates_value_and_type_errors() -> None:
    try:
        safe_call(lambda: (_ for _ in ()).throw(ValueError("bad value")))
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError should not be swallowed")

    try:
        safe_call(lambda: (_ for _ in ()).throw(TypeError("bad type")))
    except TypeError:
        pass
    else:
        raise AssertionError("TypeError should not be swallowed")


def test_safe_refresh_reports_views_calls_all_known_refreshes() -> None:
    called: list[str] = []
    reports_tab = SimpleNamespace(
        _refresh_summary_only=lambda: called.append("summary"),
        _refresh_operations_table=lambda: called.append("ops"),
        _refresh_monthly_table=lambda: called.append("monthly"),
    )

    safe_refresh_reports_views(reports_tab)

    assert called == ["summary", "ops", "monthly"]


def test_refresh_theme_surfaces_calls_expected_callbacks() -> None:
    called: list[str] = []
    binding = SimpleNamespace(refresh=lambda: called.append("binding"))

    refresh_theme_surfaces(
        refresh_status_bar=lambda: called.append("status"),
        has_records_tree=True,
        refresh_list=lambda: called.append("list"),
        refresh_tree_zebra=lambda: called.append("zebra"),
        infographics_built=True,
        refresh_charts=lambda: called.append("charts"),
        refresh_budgets=lambda: called.append("budgets"),
        refresh_all=lambda: called.append("all"),
        bindings=(binding,),
    )

    assert called == ["status", "list", "zebra", "charts", "binding", "budgets", "all"]


def test_refresh_display_currency_views_calls_reports_and_bindings() -> None:
    called: list[str] = []
    binding = SimpleNamespace(refresh=lambda: called.append("binding"))
    reports_tab = SimpleNamespace(
        _refresh_summary_only=lambda: called.append("summary"),
        _refresh_operations_table=lambda: called.append("ops"),
        _refresh_monthly_table=lambda: called.append("monthly"),
    )

    refresh_display_currency_views(
        refresh_status_bar=lambda: called.append("status"),
        has_records_tree=True,
        refresh_list=lambda: called.append("list"),
        infographics_built=True,
        refresh_charts=lambda: called.append("charts"),
        reports_tab=reports_tab,
        bindings=(binding,),
    )

    assert called == ["status", "list", "charts", "summary", "ops", "monthly", "binding"]


def test_refresh_wallet_views_calls_all_wallet_callbacks() -> None:
    called: list[str] = []

    refresh_wallet_views(
        refresh_wallets=lambda: called.append("wallets"),
        refresh_operation_wallet_menu=lambda: called.append("ops"),
        refresh_transfer_wallet_menus=lambda: called.append("transfer"),
    )

    assert called == ["wallets", "ops", "transfer"]


def test_refresh_optional_view_and_should_refresh_charts() -> None:
    called: list[str] = []

    refresh_optional_view(lambda: called.append("one"))

    assert called == ["one"]
    assert should_refresh_charts(False) is True
    assert should_refresh_charts(True) is False


def test_owner_refresh_wrappers_delegate_to_expected_callbacks() -> None:
    called: list[str] = []
    reports_tab = SimpleNamespace(
        _refresh_summary_only=lambda: called.append("summary"),
        _refresh_operations_table=lambda: called.append("ops"),
        _refresh_monthly_table=lambda: called.append("monthly"),
    )
    owner = SimpleNamespace(
        records_tree=object(),
        _built_tabs={"infographics"},
        _analytics_bindings=SimpleNamespace(refresh=lambda: called.append("analytics")),
        _dashboard_bindings=SimpleNamespace(refresh=lambda: called.append("dashboard")),
        _budget_bindings=SimpleNamespace(refresh=lambda: called.append("budget")),
        _mandatory_bindings=SimpleNamespace(refresh=lambda: called.append("mandatory")),
        _debt_bindings=SimpleNamespace(refresh=lambda: called.append("debt")),
        _distribution_bindings=SimpleNamespace(refresh=lambda: called.append("distribution")),
        _settings_bindings=SimpleNamespace(refresh=lambda: called.append("settings")),
        _reports_tab=reports_tab,
        refresh_budgets=lambda: called.append("budgets"),
        refresh_all=lambda: called.append("all"),
        refresh_wallets=lambda: called.append("wallets"),
        refresh_operation_wallet_menu=lambda: called.append("ops_menu"),
        refresh_transfer_wallet_menus=lambda: called.append("transfer_menu"),
        _refresh_status_bar=lambda: called.append("status"),
        _refresh_list=lambda: called.append("list"),
        _refresh_charts=lambda: called.append("charts"),
    )

    refresh_owner_theme_surfaces(owner, refresh_tree_zebra=lambda: called.append("zebra"))
    refresh_owner_display_currency_views(owner)
    refresh_owner_wallet_views(owner)
    refresh_owner_budgets(owner)
    refresh_owner_all(owner)

    assert "status" in called
    assert "wallets" in called
    assert "summary" in called
    assert "budgets" in called
    assert "all" in called


def test_scroll_legend_canvas_scrolls_when_pointer_inside() -> None:
    class _Canvas:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        def yview_scroll(self, delta: int, units: str) -> None:
            self.calls.append((delta, units))

    class _Widget:
        def __init__(self, master=None) -> None:
            self.master = master

    canvas = _Canvas()
    event = SimpleNamespace(x_root=0, y_root=0, delta=120)

    handled = scroll_legend_canvas(
        legend_canvas=canvas,
        winfo_containing=lambda _x, _y: canvas,
        event=event,
    )

    assert handled is True
    assert canvas.calls == [(-1, "units")]
