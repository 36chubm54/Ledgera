"""Analytics tab — Dashboard, Category Breakdown, Monthly Report."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk
from typing import Any, Protocol, cast

from gui.i18n import tr
from gui.tooltip import Tooltip
from gui.ui_helpers import attach_treeview_scrollbars, show_error
from gui.ui_theme import (
    PAD_LG,
    PAD_SM,
    PAD_XL,
    create_card_section,
    enable_treeview_zebra,
    get_palette,
)
from utils.tag_utils import display_tag_name

logger = logging.getLogger(__name__)


class AnalyticsTabContext(Protocol):
    controller: Any

    def after(self, ms: int, func: Callable[[], None]) -> str: ...

    def after_cancel(self, id: str) -> None: ...


@dataclass(slots=True)
class AnalyticsTabBindings:
    period_from_entry: ttk.Entry
    period_to_entry: ttk.Entry
    net_worth_label: ttk.Label
    savings_rate_label: ttk.Label
    burn_rate_label: ttk.Label
    spending_tree: ttk.Treeview
    income_tree: ttk.Treeview
    category_canvas: tk.Canvas
    monthly_tree: ttk.Treeview
    timeline_canvas: tk.Canvas
    refresh: Callable[[], None]
    toggle_tag_mode: Callable[[], None]


def _draw_net_worth_line(canvas: tk.Canvas, data: list) -> None:
    canvas.delete("all")
    palette = get_palette()
    canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    if not data:
        canvas.create_text(
            10,
            10,
            anchor="nw",
            text=tr("common.empty_short", "Нет данных"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return

    w = max(canvas.winfo_width(), 300)
    h = max(canvas.winfo_height(), 160)
    pad = {"left": 60, "right": 20, "top": 16, "bottom": 28}

    values = [float(getattr(item, "balance", 0.0)) for item in data]
    min_v, max_v = min(values), max(values)
    span = (max_v - min_v) or 1.0

    def to_xy(i: int, v: float) -> tuple[float, float]:
        x = pad["left"] + (w - pad["left"] - pad["right"]) * i / max(1, len(data) - 1)
        y = pad["top"] + (h - pad["top"] - pad["bottom"]) * (1 - (v - min_v) / span)
        return x, y

    if min_v < 0 < max_v:
        _, y0 = to_xy(0, 0.0)
        canvas.create_line(
            pad["left"],
            y0,
            w - pad["right"],
            y0,
            fill=palette.chart_grid,
            dash=(4, 4),
        )

    for i in range(len(values) - 1):
        x1, y1 = to_xy(i, values[i])
        x2, y2 = to_xy(i + 1, values[i + 1])
        canvas.create_line(x1, y1, x2, y2, fill=palette.accent_blue, width=2)

    for i, item in enumerate(data):
        x, y = to_xy(i, float(getattr(item, "balance", 0.0)))
        canvas.create_oval(
            x - 3,
            y - 3,
            x + 3,
            y + 3,
            fill=palette.accent_blue,
            outline=palette.chart_outline,
            width=1,
        )

    step = max(1, len(data) // 6)
    for i, item in enumerate(data):
        if i % step == 0 or i == len(data) - 1:
            x, _ = to_xy(i, values[i])
            canvas.create_text(
                x,
                h - pad["bottom"] + 10,
                text=str(getattr(item, "month", "")),
                fill=palette.chart_empty,
                font=("Segoe UI", 8),
            )

    canvas.create_text(
        pad["left"] - 4,
        pad["top"],
        text=f"{max_v:,.0f}",
        fill=palette.chart_empty,
        font=("Segoe UI", 8),
        anchor="e",
    )
    canvas.create_text(
        pad["left"] - 4,
        h - pad["bottom"],
        text=f"{min_v:,.0f}",
        fill=palette.chart_empty,
        font=("Segoe UI", 8),
        anchor="e",
    )


def _draw_breakdown_pie(canvas: tk.Canvas, data: list) -> None:
    """Draw a pie chart for category or tag breakdown data."""
    canvas.delete("all")
    palette = get_palette()
    canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    if not data:
        canvas.create_text(
            10,
            10,
            anchor="nw",
            text=tr("common.empty_short", "Нет данных"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return
    total = sum(float(getattr(item, "total_kzt", 0.0)) for item in data)
    if total <= 0:
        return

    rows = list(data)
    show_other_legend = False
    if len(rows) > 10:
        other_total = sum(float(getattr(item, "total_kzt", 0.0)) for item in rows[9:])
        rows = rows[:9]
        if other_total > 0:
            show_other_legend = True
            rows.append(
                {
                    "label": tr("common.other", "Прочие"),
                    "total_kzt": other_total,
                    "color": palette.chart_empty,
                }
            )

    w = max(canvas.winfo_width(), 200)
    h = max(canvas.winfo_height(), 200)
    margin = 10
    cx, cy = w // 2, h // 2
    r = min(cx, cy) - margin

    angle = 90.0
    for i, item in enumerate(rows):
        if isinstance(item, dict):
            value = float(item.get("total_kzt", 0.0))
            color = str(item.get("color", "") or palette.chart_empty)
        else:
            value = float(getattr(item, "total_kzt", 0.0))
            color = str(
                getattr(item, "color", "") or palette.chart_series[i % len(palette.chart_series)]
            )
        sweep = value / total * 360.0
        if sweep >= 359.9:
            canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                fill=color,
                outline=palette.chart_outline,
                width=1,
            )
            break
        canvas.create_arc(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            start=angle,
            extent=-sweep,
            fill=color,
            outline=palette.chart_outline,
            width=1,
        )
        angle -= sweep

    if show_other_legend:
        legend_y = h - 14
        canvas.create_rectangle(
            12,
            legend_y - 8,
            24,
            legend_y + 4,
            fill=palette.chart_empty,
            outline=palette.chart_outline,
            width=1,
        )
        canvas.create_text(
            30,
            legend_y - 2,
            anchor="w",
            text=tr("analytics.other_expenses", "Прочие расходы"),
            fill=palette.text_primary,
            font=("Segoe UI", 8),
        )


def build_analytics_tab(
    parent: tk.Frame | ttk.Frame,
    context: AnalyticsTabContext,
) -> AnalyticsTabBindings:
    palette = get_palette()
    parent.grid_columnconfigure(0, weight=1, uniform="analytics_columns")
    parent.grid_columnconfigure(1, weight=1, uniform="analytics_columns")
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_rowconfigure(2, weight=2)

    top = ttk.Frame(parent)
    top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=PAD_XL, pady=(PAD_LG, PAD_SM))
    top.grid_columnconfigure(5, weight=1)

    ttk.Label(top, text=tr("analytics.from", "С даты:")).grid(row=0, column=0, sticky="w")
    period_from_entry = ttk.Entry(top, width=12)
    period_from_entry.grid(row=0, column=1, sticky="w", padx=(6, 14))

    ttk.Label(top, text=tr("analytics.to", "По дату:")).grid(row=0, column=2, sticky="w")
    period_to_entry = ttk.Entry(top, width=12)
    period_to_entry.grid(row=0, column=3, sticky="w", padx=(6, 14))

    refresh_button = ttk.Button(top, text=tr("analytics.refresh", "Обновить"))
    refresh_button.grid(row=0, column=4, sticky="w")

    breakdown_by_tags_var = tk.BooleanVar(value=False)
    breakdown_by_tags_check = ttk.Checkbutton(
        top,
        text=tr("analytics.breakdown_by_tags", "Разбивка по тегам"),
        variable=breakdown_by_tags_var,
    )
    breakdown_by_tags_check.grid(row=0, column=5, sticky="e")

    default_start = datetime.now().strftime("%Y-01-01")
    default_end = datetime.now().strftime("%Y-%m-%d")
    period_from_entry.insert(0, default_start)
    period_to_entry.insert(0, default_end)

    dashboard_card = create_card_section(parent, tr("analytics.summary", "Сводка"))
    dashboard_card.grid(
        row=1, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=(PAD_SM, PAD_LG)
    )
    dashboard_frame = dashboard_card.winfo_children()[-1]
    dashboard_frame.grid_columnconfigure(0, weight=1)

    dashboard_row = ttk.Frame(dashboard_frame, padding=(10, 10))
    dashboard_row.grid(row=0, column=0, sticky="ew")
    dashboard_row.grid_columnconfigure(0, weight=1)
    dashboard_row.grid_columnconfigure(1, weight=1)
    dashboard_row.grid_columnconfigure(2, weight=1)

    dashboard_left = ttk.Frame(dashboard_row)
    dashboard_left.grid(row=0, column=0, sticky="nsew")
    for i in range(4):
        dashboard_left.grid_rowconfigure(i, weight=0)
    dashboard_left.grid_rowconfigure(3, weight=1)
    dashboard_left.grid_columnconfigure(3, weight=1)
    dashboard_right = ttk.Frame(dashboard_row)
    dashboard_right.grid(row=0, column=1, sticky="nw", padx=(24, 0))

    font = ("Segoe UI", 12, "bold")
    net_worth_label = ttk.Label(
        dashboard_left,
        text=tr("analytics.net_worth", "Чистый капитал:  {amount} KZT", amount="—"),
        font=font,
    )
    net_worth_label.grid(row=0, column=0, sticky="w")

    savings_rate_label = ttk.Label(
        dashboard_left,
        text=tr("analytics.savings_rate", "Норма сбережений: —"),
        font=font,
    )
    savings_rate_label.grid(row=1, column=0, sticky="w")

    burn_rate_label = ttk.Label(
        dashboard_left,
        text=tr("analytics.burn_rate", "Темп расходов: —"),
        font=font,
    )
    burn_rate_label.grid(row=2, column=0, sticky="w")

    tooltip_label = ttk.Label(dashboard_left, text="ⓘ", font=("Segoe UI", 10))
    tooltip_label.config(foreground=palette.text_muted)
    tooltip_label.grid(row=3, column=0, sticky="sw")

    Tooltip(
        tooltip_label,
        tr(
            "analytics.tooltip",
            "Норма сбережений = денежный поток / доход * 100%."
            "\nТемп расходов = общие расходы / число дней в периоде."
            "\nСредний доход в месяц считается по всем месяцам."
            "\nДоход за год — сумма доходов за выбранный год."
            "\nДоход за год (USD) — тот же доход после конвертации."
            "\nСредние расходы в месяц считаются по всем месяцам."
            "\nРасход за год — сумма расходов за выбранный год."
            "\nСтоимость дня, часа и минуты рассчитывается из текущего темпа расходов.",
        ),
    )

    avg_monthly_income_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.avg_income", "Средний доход в месяц: —"),
        font=font,
    )
    avg_monthly_income_label.grid(row=0, column=0, sticky="w")

    avg_monthly_expenses_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.avg_expenses", "Средние расходы в месяц: —"),
        font=font,
    )
    avg_monthly_expenses_label.grid(row=1, column=0, sticky="w")

    year_income_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.year_income", "Доход за год: —"),
        font=font,
    )
    year_income_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

    year_income_usd_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.year_income_usd", "Доход за год (USD): —"),
        font=font,
    )
    year_income_usd_label.grid(row=3, column=0, sticky="w")

    year_expense_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.year_expense", "Расход за год: —"),
        font=font,
    )
    year_expense_label.grid(row=4, column=0, sticky="w")

    day_cost_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.cost_day", "Стоимость дня: —"),
        font=font,
    )
    day_cost_label.grid(row=5, column=0, sticky="w", pady=(10, 0))

    hour_cost_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.cost_hour", "Стоимость часа: —"),
        font=font,
    )
    hour_cost_label.grid(row=6, column=0, sticky="w")

    minute_cost_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.cost_minute", "Стоимость минуты: —"),
        font=font,
    )
    minute_cost_label.grid(row=7, column=0, sticky="w")

    timeline_card = create_card_section(parent, tr("analytics.timeline", "Динамика капитала"))
    timeline_card.grid(row=1, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=(PAD_SM, PAD_LG))
    timeline_frame = timeline_card.winfo_children()[-1]
    timeline_frame.grid_columnconfigure(0, weight=1)
    timeline_frame.grid_rowconfigure(0, weight=1)
    timeline_canvas = tk.Canvas(
        timeline_frame,
        height=180,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    timeline_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    breakdown_card = create_card_section(
        parent, tr("analytics.breakdown", "Разбивка по категориям")
    )
    breakdown_card.grid(row=2, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=(0, PAD_LG))
    breakdown_frame = cast(ttk.Frame, breakdown_card.winfo_children()[-1])
    breakdown_title_label = cast(ttk.Label, breakdown_card.winfo_children()[0])
    breakdown_frame.grid_columnconfigure(0, weight=3)
    breakdown_frame.grid_columnconfigure(1, weight=2, minsize=240)
    breakdown_frame.grid_rowconfigure(0, weight=1)

    breakdown_left = ttk.Frame(breakdown_frame, padding=(10, 10))
    breakdown_left.grid(row=0, column=0, sticky="nsew")
    breakdown_left.grid_columnconfigure(0, weight=1)

    category_breakdown_frame = ttk.Frame(breakdown_left)
    category_breakdown_frame.grid(row=0, column=0, sticky="nsew")
    category_breakdown_frame.grid_columnconfigure(0, weight=1)

    ttk.Label(
        category_breakdown_frame,
        text=tr("analytics.expenses", "Расходы"),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="w")
    spending_tree = ttk.Treeview(
        category_breakdown_frame,
        columns=("category", "total", "count"),
        show="headings",
        height=4,
    )
    enable_treeview_zebra(spending_tree)
    spending_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 14))
    spending_tree.heading("category", text=tr("analytics.category", "Категория"))
    spending_tree.heading("total", text=tr("analytics.total_kzt", "Сумма KZT"))
    spending_tree.heading("count", text=tr("common.count_short", "#"))
    spending_tree.column("category", width=200, minwidth=200)
    spending_tree.column("total", width=120, minwidth=120, anchor="e")
    spending_tree.column("count", width=60, minwidth=60, anchor="center")
    attach_treeview_scrollbars(
        category_breakdown_frame, spending_tree, row=1, column=0, horizontal=False, pady=0
    )

    ttk.Label(
        category_breakdown_frame,
        text=tr("analytics.income", "Доходы"),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=2, column=0, sticky="w")
    income_tree = ttk.Treeview(
        category_breakdown_frame,
        columns=("category", "total", "count"),
        show="headings",
        height=4,
    )
    enable_treeview_zebra(income_tree)
    income_tree.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
    income_tree.heading("category", text=tr("analytics.category", "Категория"))
    income_tree.heading("total", text=tr("analytics.total_kzt", "Сумма KZT"))
    income_tree.heading("count", text=tr("common.count_short", "#"))
    income_tree.column("category", width=200, minwidth=200)
    income_tree.column("total", width=120, minwidth=120, anchor="e")
    income_tree.column("count", width=60, minwidth=60, anchor="center")
    attach_treeview_scrollbars(
        category_breakdown_frame, income_tree, row=3, column=0, horizontal=False, pady=0
    )

    tag_breakdown_frame = ttk.Frame(breakdown_left)
    tag_breakdown_frame.grid(row=0, column=0, sticky="nsew")
    tag_breakdown_frame.grid_columnconfigure(0, weight=1)
    tag_breakdown_frame.grid_rowconfigure(1, weight=1)

    ttk.Label(
        tag_breakdown_frame,
        text=tr("analytics.tags_expenses", "Теги расходов"),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="w")
    tag_tree = ttk.Treeview(
        tag_breakdown_frame,
        columns=("tag", "total", "count"),
        show="headings",
        height=9,
    )
    enable_treeview_zebra(tag_tree)
    tag_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
    tag_tree.heading("tag", text=tr("common.tags", "Теги"))
    tag_tree.heading("total", text=tr("analytics.total_kzt", "Сумма KZT"))
    tag_tree.heading("count", text=tr("common.count_short", "#"))
    tag_tree.column("tag", width=100, minwidth=100)
    tag_tree.column("total", width=90, minwidth=90, anchor="e")
    tag_tree.column("count", width=50, minwidth=50, anchor="center")
    attach_treeview_scrollbars(
        tag_breakdown_frame, tag_tree, row=1, column=0, horizontal=False, pady=0
    )
    ttk.Label(
        tag_breakdown_frame,
        text=tr(
            "analytics.tags_split_hint",
            "Суммы по тегам не складываются в общий итог: одна запись может одновременно входить в несколько тегов.",  # noqa: E501
        ),
    ).grid(row=2, column=0, sticky="w", pady=(8, 0))
    tag_breakdown_frame.grid_remove()

    breakdown_right = ttk.Frame(breakdown_frame, padding=(0, 10, 10, 10))
    breakdown_right.grid(row=0, column=1, sticky="nsew")
    breakdown_right.grid_propagate(False)
    breakdown_right.grid_columnconfigure(0, weight=1)
    breakdown_right.grid_rowconfigure(0, weight=1)
    category_canvas = tk.Canvas(
        breakdown_right,
        width=220,
        height=220,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    category_canvas.grid(row=0, column=0, sticky="nsew")

    monthly_card = create_card_section(parent, tr("analytics.monthly_report", "Помесячный отчет"))
    monthly_card.grid(row=2, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=(0, PAD_LG))
    monthly_frame = monthly_card.winfo_children()[-1]
    monthly_frame.grid_columnconfigure(0, weight=1)
    monthly_frame.grid_rowconfigure(0, weight=1)

    monthly_container = ttk.Frame(monthly_frame, padding=(10, 10))
    monthly_container.grid(row=0, column=0, sticky="nsew")
    monthly_container.grid_columnconfigure(0, weight=1)
    monthly_container.grid_rowconfigure(0, weight=1)

    monthly_tree = ttk.Treeview(
        monthly_container,
        columns=("month", "income", "expenses", "cashflow", "savings"),
        show="headings",
        height=10,
    )
    enable_treeview_zebra(monthly_tree)
    monthly_tree.grid(row=0, column=0, sticky="nsew")
    monthly_tree.heading("month", text=tr("common.month", "Месяц"))
    monthly_tree.heading("income", text=tr("analytics.income", "Доходы"))
    monthly_tree.heading("expenses", text=tr("analytics.expenses", "Расходы"))
    monthly_tree.heading("cashflow", text=tr("analytics.cashflow", "Денежный поток"))
    monthly_tree.heading("savings", text=tr("analytics.savings_pct", "Сбережения %"))
    monthly_tree.column("month", width=80, minwidth=80)
    monthly_tree.column("income", width=120, minwidth=120, anchor="e")
    monthly_tree.column("expenses", width=120, minwidth=120, anchor="e")
    monthly_tree.column("cashflow", width=120, minwidth=120, anchor="e")
    monthly_tree.column("savings", width=70, minwidth=70, anchor="e")

    monthly_tree.tag_configure("positive", foreground=palette.chart_income)
    monthly_tree.tag_configure("negative", foreground=palette.chart_expense)

    attach_treeview_scrollbars(monthly_container, monthly_tree, row=0, column=0, horizontal=True)

    last_timeline_data: list = []
    last_breakdown_data: list = []
    redraw_job: str | None = None

    def _apply_breakdown_mode() -> None:
        is_tags_mode = bool(breakdown_by_tags_var.get())
        if is_tags_mode:
            breakdown_frame.grid_columnconfigure(0, weight=3)
            breakdown_frame.grid_columnconfigure(1, weight=2, minsize=240)
            category_canvas.configure(width=220, height=220)
            category_breakdown_frame.grid_remove()
            tag_breakdown_frame.grid()
            breakdown_title_label.configure(
                text=tr("analytics.breakdown_tags", "Покрытие расходов тегами")
            )
        else:
            breakdown_frame.grid_columnconfigure(0, weight=3)
            breakdown_frame.grid_columnconfigure(1, weight=2, minsize=240)
            category_canvas.configure(width=220, height=220)
            tag_breakdown_frame.grid_remove()
            category_breakdown_frame.grid()
            breakdown_title_label.configure(
                text=tr("analytics.breakdown", "Разбивка по категориям")
            )

    def _schedule_redraw() -> None:
        nonlocal redraw_job
        if redraw_job is not None:
            try:
                context.after_cancel(redraw_job)
            except (tk.TclError, RuntimeError):
                pass
        redraw_job = context.after(120, _redraw_canvases)

    def _redraw_canvases() -> None:
        nonlocal redraw_job
        redraw_job = None
        _draw_net_worth_line(timeline_canvas, last_timeline_data)
        _draw_breakdown_pie(category_canvas, last_breakdown_data)

    def _refresh_analytics() -> None:
        nonlocal last_timeline_data, last_breakdown_data
        start = period_from_entry.get().strip() or default_start
        end = period_to_entry.get().strip() or default_end

        try:
            from domain.validation import ensure_not_future, parse_ymd

            parsed_start = parse_ymd(start)
            parsed_end = parse_ymd(end)
            ensure_not_future(parsed_start)
            ensure_not_future(parsed_end)
            if parsed_start > parsed_end:
                raise ValueError(
                    tr(
                        "analytics.error.period_order",
                        "Начальная дата должна быть не позже конечной.",
                    )
                )

            start = parsed_start.isoformat()
            end = parsed_end.isoformat()

            net_worth = float(context.controller.get_total_balance(date=end))
            savings_rate = float(context.controller.get_savings_rate(start, end))
            burn_rate = float(context.controller.get_burn_rate(start, end))
            year = int(parsed_end.year)
            avg_monthly_income = float(
                context.controller.get_average_monthly_income(year, up_to_date=end)
            )
            year_income = float(context.controller.get_year_income(year, up_to_date=end))
            year_income_usd = float(context.controller.convert_kzt_to_usd(year_income))
            year_expense = float(context.controller.get_year_expense(year, up_to_date=end))
            avg_monthly_expenses = float(
                context.controller.get_average_monthly_expenses(start, end)
            )
            day_cost, hour_cost, minute_cost = context.controller.get_time_costs(start, end)

            net_worth_label.config(
                text=tr(
                    "analytics.net_worth",
                    "Чистый капитал:  {amount} KZT",
                    amount=f"{net_worth:,.0f}",
                )
            )
            savings_rate_label.config(
                text=tr(
                    "analytics.savings_rate_value",
                    "Норма сбережений:  {value}%",
                    value=f"{savings_rate:.1f}",
                ),
                foreground=palette.chart_income if savings_rate >= 0 else palette.chart_expense,
            )
            burn_rate_label.config(
                text=tr(
                    "analytics.burn_rate_value",
                    "Темп расходов:  {value} KZT/день",
                    value=f"{burn_rate:,.0f}",
                )
            )
            avg_monthly_income_label.config(
                text=tr(
                    "analytics.avg_income_value",
                    "Средний доход в месяц ({year}):  {value} KZT",
                    year=year,
                    value=f"{avg_monthly_income:,.0f}",
                )
            )
            year_income_label.config(
                text=tr(
                    "analytics.year_income_value",
                    "Доход за {year} год:  {value} KZT",
                    year=year,
                    value=f"{year_income:,.0f}",
                )
            )
            year_income_usd_label.config(
                text=tr(
                    "analytics.year_income_usd_value",
                    "Доход за {year} год (USD):  {value}",
                    year=year,
                    value=f"{year_income_usd:,.2f}",
                )
            )
            avg_monthly_expenses_label.config(
                text=tr(
                    "analytics.avg_expenses_value",
                    "Средние расходы в месяц:  {value} KZT",
                    value=f"{avg_monthly_expenses:,.0f}",
                )
            )
            year_expense_label.config(
                text=tr(
                    "analytics.year_expense_value",
                    "Расход за {year} год:  {value} KZT",
                    year=year,
                    value=f"{year_expense:,.0f}",
                )
            )
            day_cost_label.config(
                text=tr(
                    "analytics.cost_day_value",
                    "Стоимость дня:  {value} KZT",
                    value=f"{float(day_cost):,.0f}",
                )
            )
            hour_cost_label.config(
                text=tr(
                    "analytics.cost_hour_value",
                    "Стоимость часа:  {value} KZT",
                    value=f"{float(hour_cost):,.2f}",
                )
            )
            minute_cost_label.config(
                text=tr(
                    "analytics.cost_minute_value",
                    "Стоимость минуты:  {value} KZT",
                    value=f"{float(minute_cost):,.2f}",
                )
            )

            timeline_data = context.controller.get_net_worth_timeline()
            last_timeline_data = list(timeline_data) if timeline_data else []
            _draw_net_worth_line(timeline_canvas, last_timeline_data)

            is_tags_mode = bool(breakdown_by_tags_var.get())
            _apply_breakdown_mode()

            spending_data = context.controller.get_spending_by_category(start, end)
            spending_tree.delete(*spending_tree.get_children())
            for item in spending_data:
                spending_tree.insert(
                    "",
                    "end",
                    values=(
                        getattr(item, "category", ""),
                        f"{float(getattr(item, 'total_kzt', 0.0)):,.0f}",
                        int(getattr(item, "record_count", 0)),
                    ),
                )

            income_data = context.controller.get_income_by_category(start, end)
            income_tree.delete(*income_tree.get_children())
            for item in income_data:
                income_tree.insert(
                    "",
                    "end",
                    values=(
                        getattr(item, "category", ""),
                        f"{float(getattr(item, 'total_kzt', 0.0)):,.0f}",
                        int(getattr(item, "record_count", 0)),
                    ),
                )

            tag_data = context.controller.get_spending_by_tag(start, end)
            tag_tree.delete(*tag_tree.get_children())
            for item in tag_data:
                row_tag = ""
                row_color = str(getattr(item, "color", "") or "")
                if row_color:
                    row_tag = f"tag_{row_color.replace('#', '').lower()}"
                    tag_tree.tag_configure(row_tag, foreground=row_color)
                tag_tree.insert(
                    "",
                    "end",
                    values=(
                        display_tag_name(getattr(item, "tag", "")),
                        f"{float(getattr(item, 'total_kzt', 0.0)):,.0f}",
                        int(getattr(item, "record_count", 0)),
                    ),
                    tags=((row_tag,) if row_tag else ()),
                )

            last_breakdown_data = list(tag_data) if is_tags_mode else list(spending_data)
            _draw_breakdown_pie(category_canvas, last_breakdown_data)

            monthly_data = context.controller.get_monthly_summary(start_date=start, end_date=end)
            monthly_tree.delete(*monthly_tree.get_children())
            for item in monthly_data:
                cashflow = float(getattr(item, "cashflow", 0.0))
                tag = "positive" if cashflow >= 0 else "negative"
                monthly_tree.insert(
                    "",
                    "end",
                    values=(
                        getattr(item, "month", ""),
                        f"{float(getattr(item, 'income', 0.0)):,.0f}",
                        f"{float(getattr(item, 'expenses', 0.0)):,.0f}",
                        f"{cashflow:,.0f}",
                        f"{float(getattr(item, 'savings_rate', 0.0)):.1f}%",
                    ),
                    tags=(tag,),
                )
        except (ValueError, TypeError, RuntimeError, tk.TclError) as error:
            logger.warning("Analytics refresh error: %s", error)
            if isinstance(error, ValueError):
                show_error(
                    tr(
                        "analytics.error.invalid_period",
                        "{error}\n\nИспользуйте формат YYYY-MM-DD и убедитесь, "
                        "что даты не из будущего.",
                        error=error,
                    ),
                    title=tr("analytics.error.invalid_period_title", "Некорректный период"),
                )

    refresh_button.configure(command=_refresh_analytics)
    breakdown_by_tags_check.configure(command=_refresh_analytics)

    def _toggle_tag_mode() -> None:
        breakdown_by_tags_var.set(not bool(breakdown_by_tags_var.get()))
        _refresh_analytics()

    def _bind_enter_refresh(entry: ttk.Entry) -> None:
        entry.bind("<Return>", lambda _event: _refresh_analytics())

    _bind_enter_refresh(period_from_entry)
    _bind_enter_refresh(period_to_entry)

    timeline_canvas.bind("<Configure>", lambda _event: _schedule_redraw())
    category_canvas.bind("<Configure>", lambda _event: _schedule_redraw())

    _refresh_analytics()

    return AnalyticsTabBindings(
        period_from_entry=period_from_entry,
        period_to_entry=period_to_entry,
        net_worth_label=net_worth_label,
        savings_rate_label=savings_rate_label,
        burn_rate_label=burn_rate_label,
        spending_tree=spending_tree,
        income_tree=income_tree,
        category_canvas=category_canvas,
        monthly_tree=monthly_tree,
        timeline_canvas=timeline_canvas,
        refresh=_refresh_analytics,
        toggle_tag_mode=_toggle_tag_mode,
    )
