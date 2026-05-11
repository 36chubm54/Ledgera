from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from gui.tabs.infographics_support import (
    derive_month_options,
    derive_year_options,
    draw_bar_chart,
    handle_chart_filter_change,
    refresh_owner_infographics,
    scroll_owner_legend_canvas,
    update_chart_month_options,
    update_chart_year_options,
)


@dataclass
class _Var:
    value: str = ""

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


@dataclass
class _Combo:
    values: tuple[str, ...] = ()

    def __setitem__(self, key: str, value) -> None:
        assert key == "values"
        self.values = tuple(value)


@dataclass
class _Canvas:
    deleted: list[object] = field(default_factory=list)
    configured: list[dict[str, object]] = field(default_factory=list)
    texts: list[tuple[tuple[object, ...], dict[str, object]]] = field(default_factory=list)

    def delete(self, item: object) -> None:
        self.deleted.append(item)

    def configure(self, **kwargs: object) -> None:
        self.configured.append(kwargs)

    def winfo_width(self) -> int:
        return 220

    def winfo_height(self) -> int:
        return 180

    def create_text(self, *args: object, **kwargs: object) -> object:
        self.texts.append((args, kwargs))
        return object()

    def create_line(self, *args: object, **kwargs: object) -> object:
        return object()

    def create_rectangle(self, *args: object, **kwargs: object) -> object:
        return object()


def test_update_chart_month_options_selects_latest_available_month() -> None:
    var = _Var()
    combo = _Combo()

    update_chart_month_options(combo, var, ["2026-01", "2026-05"])

    assert combo.values == ("2026-01", "2026-05")
    assert var.get() == "2026-05"


def test_update_chart_year_options_selects_latest_available_year() -> None:
    var = _Var()
    combo = _Combo()

    update_chart_year_options(combo, var, [2025, 2026])

    assert combo.values == ("2025", "2026")
    assert var.get() == "2026"


def test_draw_bar_chart_renders_empty_state() -> None:
    canvas = _Canvas()

    draw_bar_chart(canvas, ["A", "B"], [0.0, 0.0], [0.0, 0.0], max_labels=8)

    assert canvas.deleted == ["all"]
    assert canvas.texts


def test_derive_month_and_year_options_include_current_period() -> None:
    records = [
        SimpleNamespace(date="2026-01-01"),
        SimpleNamespace(date="2026-03-01"),
    ]

    months = derive_month_options(records)
    years = derive_year_options(records)

    assert "2026-01" in months
    assert "2026-03" in months
    assert 2026 in years


def test_refresh_owner_infographics_uses_repository_and_controller(monkeypatch) -> None:
    records = [SimpleNamespace(date="2026-05-01")]
    owner = SimpleNamespace(
        repository=SimpleNamespace(load_all=lambda: records),
        controller=SimpleNamespace(
            format_display_money=lambda amount, precision=2: f"{amount:.2f}"
        ),
        chart_month_menu=object(),
        chart_month_var=object(),
        pie_month_menu=object(),
        pie_month_var=object(),
        chart_year_menu=object(),
        chart_year_var=object(),
        expense_pie_canvas=None,
        expense_legend_canvas=None,
        expense_legend_frame=None,
        daily_bar_canvas=None,
        monthly_bar_canvas=None,
        _chart_refresh_suspended=False,
    )
    calls: list[tuple[object, dict[str, object]]] = []

    monkeypatch.setattr(
        "gui.tabs.infographics_support.refresh_infographics_charts",
        lambda owner_arg, **kwargs: calls.append((owner_arg, kwargs)),
    )

    refresh_owner_infographics(owner)

    assert calls
    assert calls[0][0] is owner
    assert calls[0][1]["records"] == records


def test_handle_chart_filter_change_and_scroll_owner_legend_canvas(monkeypatch) -> None:
    calls: list[str] = []

    class _LegendCanvas:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        def yview_scroll(self, delta: int, units: str) -> None:
            self.calls.append((delta, units))

    canvas = _LegendCanvas()
    owner = SimpleNamespace(
        _chart_refresh_suspended=False,
        repository=SimpleNamespace(load_all=lambda: []),
        controller=SimpleNamespace(
            format_display_money=lambda amount, precision=2: f"{amount:.2f}"
        ),
        chart_month_menu=None,
        chart_month_var=None,
        pie_month_menu=None,
        pie_month_var=None,
        chart_year_menu=None,
        chart_year_var=None,
        expense_pie_canvas=None,
        expense_legend_canvas=canvas,
        expense_legend_frame=None,
        daily_bar_canvas=None,
        monthly_bar_canvas=None,
        winfo_containing=lambda _x, _y: canvas,
    )

    monkeypatch.setattr(
        "gui.tabs.infographics_support.refresh_owner_infographics",
        lambda _owner, records=None: calls.append("refresh"),
    )
    assert handle_chart_filter_change(owner) is True

    event = SimpleNamespace(x_root=0, y_root=0, delta=120)
    assert scroll_owner_legend_canvas(owner, event) is True
    assert canvas.calls == [(-1, "units")]
