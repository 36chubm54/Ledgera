from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import TclError, ttk
from typing import Any, Protocol

from gui.i18n import tr
from gui.tabs.infographics_tab import draw_expense_pie, update_pie_month_options
from gui.ui_theme import get_palette
from utils.charting import aggregate_daily_cashflow, aggregate_monthly_cashflow


class InfographicsOwner(Protocol):
    repository: Any
    controller: Any
    chart_month_menu: ttk.Combobox | None
    chart_month_var: tk.StringVar | None
    pie_month_menu: ttk.Combobox | None
    pie_month_var: tk.StringVar | None
    chart_year_menu: ttk.Combobox | None
    chart_year_var: tk.StringVar | None
    expense_pie_canvas: tk.Canvas | None
    expense_legend_canvas: tk.Canvas | None
    expense_legend_frame: tk.Frame | None
    daily_bar_canvas: tk.Canvas | None
    monthly_bar_canvas: tk.Canvas | None
    _chart_refresh_suspended: bool

    def winfo_containing(self, root_x: int, root_y: int) -> Any: ...


class ComboLike(Protocol):
    def __setitem__(self, key: str, value: object) -> None: ...


class StringVarLike(Protocol):
    def get(self) -> str: ...

    def set(self, value: str) -> None: ...


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


def derive_month_options(records: Any) -> list[str]:
    from utils.charting import extract_months

    months = extract_months(records)
    current_month = datetime.now().strftime("%Y-%m")
    if current_month not in months:
        months.append(current_month)
    return sorted(set(months))


def derive_year_options(records: Any) -> list[int]:
    from utils.charting import extract_years

    years = extract_years(records)
    current_year = datetime.now().year
    if current_year not in years:
        years.append(current_year)
    return sorted(set(years))


def draw_bar_chart(
    canvas: Any,
    labels: list[str],
    income_values: list[float],
    expense_values: list[float],
    max_labels: int,
) -> None:
    canvas.delete("all")
    palette = get_palette()
    try:
        canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    except TclError:
        pass
    width = max(canvas.winfo_width(), 300)
    height = max(canvas.winfo_height(), 220)

    max_income = max(income_values) if income_values else 0
    max_expense = max(expense_values) if expense_values else 0
    max_value = max(max_income, max_expense)

    if max_value <= 0:
        canvas.create_text(
            10,
            10,
            anchor="nw",
            text=tr("common.empty", "Нет данных для отображения"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return

    padding = {
        "left": 34 if width < 420 else 40,
        "right": 16 if width < 420 else 20,
        "top": 20,
        "bottom": 34 if height < 240 else 30,
    }
    chart_w = width - padding["left"] - padding["right"]
    chart_h = height - padding["top"] - padding["bottom"]
    zero_y = padding["top"] + chart_h / 2
    scale = (chart_h / 2 - 10) / max_value

    canvas.create_line(
        padding["left"],
        zero_y,
        padding["left"] + chart_w,
        zero_y,
        fill=palette.chart_axis,
    )

    group_width = chart_w / max(1, len(labels))
    bar_width = max(4, min(18, group_width * 0.28))

    for idx, label in enumerate(labels):
        x_center = padding["left"] + group_width * idx + group_width / 2
        income_h = income_values[idx] * scale
        expense_h = expense_values[idx] * scale
        x1 = x_center - bar_width / 2
        x2 = x_center + bar_width / 2

        canvas.create_rectangle(
            x1,
            zero_y - income_h,
            x2,
            zero_y,
            fill=palette.chart_income,
            outline="",
        )
        canvas.create_rectangle(
            x1,
            zero_y,
            x2,
            zero_y + expense_h,
            fill=palette.chart_expense,
            outline="",
        )

        label_capacity = max(
            3,
            min(max_labels, int(chart_w // 44) if chart_w > 0 else max_labels),
        )
        label_step = max(1, len(labels) // label_capacity)
        if idx % label_step == 0 or len(labels) <= label_capacity:
            canvas.create_text(
                x_center,
                padding["top"] + chart_h + 10,
                text=label,
                fill=palette.chart_empty,
                font=("Segoe UI", 9),
            )

    canvas.create_text(
        padding["left"],
        padding["top"] - 6,
        text=tr("operations.type.income", "Доход"),
        fill=palette.chart_income,
        anchor="sw",
        font=("Segoe UI", 9),
    )
    canvas.create_text(
        padding["left"] + 60,
        padding["top"] - 6,
        text=tr("operations.type.expense", "Расход"),
        fill=palette.chart_expense,
        anchor="sw",
        font=("Segoe UI", 9),
    )


def draw_daily_bars(
    chart_month_var: tk.StringVar | None,
    daily_bar_canvas: tk.Canvas | None,
    records: Any,
) -> None:
    if chart_month_var is None or daily_bar_canvas is None:
        return
    month_value = chart_month_var.get()
    if not month_value:
        return
    year, month = map(int, month_value.split("-"))
    income, expense = aggregate_daily_cashflow(records, year, month)
    labels = [str(idx + 1) for idx in range(len(income))]
    draw_bar_chart(daily_bar_canvas, labels, income, expense, max_labels=8)


def draw_monthly_bars(
    chart_year_var: tk.StringVar | None,
    monthly_bar_canvas: tk.Canvas | None,
    records: Any,
) -> None:
    if chart_year_var is None or monthly_bar_canvas is None:
        return
    year_value = chart_year_var.get()
    if not year_value:
        return
    year = int(year_value)
    income, expense = aggregate_monthly_cashflow(records, year)
    labels = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    draw_bar_chart(monthly_bar_canvas, labels, income, expense, 12)


def refresh_infographics_charts(
    owner: InfographicsOwner,
    *,
    records: list[Any],
    months: list[str],
    years: list[int],
    format_money: Any,
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


def refresh_owner_infographics(owner: Any, records: list[Any] | None = None) -> None:
    loaded_records: list[Any] = (
        records if records is not None else list(owner.repository.load_all())
    )
    refresh_infographics_charts(
        owner,
        records=loaded_records,
        months=derive_month_options(loaded_records),
        years=derive_year_options(loaded_records),
        format_money=lambda amount: owner.controller.format_display_money(amount, precision=2),
    )


def handle_chart_filter_change(owner: Any) -> bool:
    if owner._chart_refresh_suspended:
        return False
    refresh_owner_infographics(owner)
    return True


def scroll_owner_legend_canvas(owner: Any, event: Any) -> bool:
    legend_canvas = owner.expense_legend_canvas
    if legend_canvas is None:
        return False

    widget = owner.winfo_containing(event.x_root, event.y_root)
    while widget is not None:
        if widget == legend_canvas:
            delta = -1 if event.delta > 0 else 1
            legend_canvas.yview_scroll(delta, "units")
            return True
        widget = widget.master
    return False
