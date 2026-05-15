"""Refresh and option helpers for the infographics tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

from domain.records import Record
from utils.charting import extract_months, extract_years

from .bar_section import draw_daily_bars, draw_monthly_bars
from .contracts import (
    ComboLike,
    InfographicsRefreshOwner,
    MouseWheelEventLike,
    ScrollOwner,
    StringVarLike,
)
from .pie_section import draw_expense_pie, update_pie_month_options


def update_chart_month_options(
    chart_month_menu: ComboLike | None,
    chart_month_var: StringVarLike | None,
    months: list[str],
) -> None:
    if chart_month_menu is None or chart_month_var is None:
        return
    chart_month_menu["values"] = months
    if not chart_month_var.get() or chart_month_var.get() not in months:
        chart_month_var.set(months[-1] if months else "")


def update_chart_year_options(
    chart_year_menu: ComboLike | None,
    chart_year_var: StringVarLike | None,
    years: list[int],
) -> None:
    if chart_year_menu is None or chart_year_var is None:
        return
    chart_year_menu["values"] = [str(year) for year in years]
    if not chart_year_var.get() or int(chart_year_var.get()) not in years:
        chart_year_var.set(str(years[-1]) if years else "")


def derive_month_options(records: Sequence[object]) -> list[str]:
    months = extract_months(cast(Sequence[Record], records))
    current_month = datetime.now().strftime("%Y-%m")
    if current_month not in months:
        months.append(current_month)
    return sorted(set(months))


def derive_year_options(records: Sequence[object]) -> list[int]:
    years = extract_years(cast(Sequence[Record], records))
    current_year = datetime.now().year
    if current_year not in years:
        years.append(current_year)
    return sorted(set(years))


def refresh_infographics_charts(
    owner: InfographicsRefreshOwner,
    *,
    records: Sequence[object],
    months: list[str],
    years: list[int],
    format_money: Callable[[float], str],
) -> None:
    if (
        owner.chart_month_menu is None
        or owner.chart_month_var is None
        or owner.pie_month_menu is None
        or owner.pie_month_var is None
        or owner.chart_year_menu is None
        or owner.chart_year_var is None
    ):
        return
    owner._chart_refresh_suspended = True
    try:
        update_chart_month_options(owner.chart_month_menu, owner.chart_month_var, months)
        update_pie_month_options(owner.pie_month_menu, owner.pie_month_var, records)
        update_chart_year_options(owner.chart_year_menu, owner.chart_year_var, years)
    finally:
        owner._chart_refresh_suspended = False

    draw_expense_pie(
        pie_month_var=owner.pie_month_var,
        expense_pie_canvas=owner.expense_pie_canvas,
        expense_legend_canvas=owner.expense_legend_canvas,
        expense_legend_frame=owner.expense_legend_frame,
        records=records,
        format_money=format_money,
    )
    draw_daily_bars(owner.chart_month_var, owner.daily_bar_canvas, records)
    draw_monthly_bars(owner.chart_year_var, owner.monthly_bar_canvas, records)


def refresh_owner_infographics(
    owner: InfographicsRefreshOwner,
    records: Sequence[object] | None = None,
    *,
    load_fresh: bool = False,
) -> None:
    if records is not None:
        loaded_records = cast(list[object], list(records))
        owner._infographics_records_cache = loaded_records
    elif load_fresh or owner._infographics_records_cache is None:
        loaded_records = cast(list[object], list(owner.repository.load_all()))
        owner._infographics_records_cache = loaded_records
    else:
        loaded_records = owner._infographics_records_cache
    refresh_infographics_charts(
        owner,
        records=loaded_records,
        months=derive_month_options(loaded_records),
        years=derive_year_options(loaded_records),
        format_money=lambda amount: owner.controller.format_display_money(amount, precision=2),
    )


def handle_chart_filter_change(owner: InfographicsRefreshOwner) -> bool:
    if owner._chart_refresh_suspended:
        return False
    refresh_owner_infographics(owner, load_fresh=False)
    return True


def scroll_owner_legend_canvas(owner: ScrollOwner, event: MouseWheelEventLike) -> bool:
    legend_canvas = owner.expense_legend_canvas
    if legend_canvas is None:
        return False

    widget = owner.winfo_containing(event.x_root, event.y_root)
    while widget is not None:
        if widget == legend_canvas:
            delta = -1 if event.delta > 0 else 1
            legend_canvas.yview_scroll(delta, "units")
            return True
        widget = cast(tk.Misc | None, getattr(widget, "master", None))
    return False
