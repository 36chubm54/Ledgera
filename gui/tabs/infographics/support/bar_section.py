"""Bar chart helpers for the infographics tab."""

from __future__ import annotations

from collections.abc import Sequence
from tkinter import Canvas, TclError
from typing import Protocol, cast

from domain.records import Record
from gui.i18n import tr
from gui.ui_theme import get_palette
from utils.charting import aggregate_daily_cashflow, aggregate_monthly_cashflow


class StringValueLike(Protocol):
    def get(self) -> str: ...


def draw_bar_chart(
    canvas: Canvas,
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

    for index, label in enumerate(labels):
        x_center = padding["left"] + group_width * index + group_width / 2
        income_h = income_values[index] * scale
        expense_h = expense_values[index] * scale
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
        if index % label_step == 0 or len(labels) <= label_capacity:
            canvas.create_text(
                x_center,
                padding["top"] + chart_h + 10,
                text=label,
                fill=palette.chart_empty,
                font=("Segoe UI", 9),
            )

    legend_y = max(6, padding["top"] - 14)
    canvas.create_text(
        padding["left"],
        legend_y,
        text=tr("operations.type.income", "Доход"),
        fill=palette.chart_income,
        anchor="nw",
        font=("Segoe UI", 9),
    )
    canvas.create_text(
        padding["left"] + 60,
        legend_y,
        text=tr("operations.type.expense", "Расход"),
        fill=palette.chart_expense,
        anchor="nw",
        font=("Segoe UI", 9),
    )


def draw_daily_bars(
    chart_month_var: StringValueLike | None,
    daily_bar_canvas: Canvas | None,
    records: Sequence[object],
) -> None:
    if chart_month_var is None or daily_bar_canvas is None:
        return
    month_value = chart_month_var.get()
    if not month_value:
        return
    year, month = map(int, month_value.split("-"))
    income, expense = aggregate_daily_cashflow(cast(Sequence[Record], records), year, month)
    labels = [str(index + 1) for index in range(len(income))]
    draw_bar_chart(daily_bar_canvas, labels, income, expense, max_labels=8)


def draw_monthly_bars(
    chart_year_var: StringValueLike | None,
    monthly_bar_canvas: Canvas | None,
    records: Sequence[object],
) -> None:
    if chart_year_var is None or monthly_bar_canvas is None:
        return
    year_value = chart_year_var.get()
    if not year_value:
        return
    year = int(year_value)
    income, expense = aggregate_monthly_cashflow(cast(Sequence[Record], records), year)
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    draw_bar_chart(monthly_bar_canvas, labels, income, expense, 12)
