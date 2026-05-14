"""Infographics tab — expense and income data aggregation and visualization"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL, create_card_section, get_palette
from utils.charting import aggregate_expenses_by_category, extract_months


@dataclass(slots=True)
class InfographicsTabBindings:
    pie_month_var: tk.StringVar
    pie_month_menu: ttk.Combobox
    chart_month_var: tk.StringVar
    chart_month_menu: ttk.Combobox
    chart_year_var: tk.StringVar
    chart_year_menu: ttk.Combobox
    expense_pie_canvas: tk.Canvas
    expense_legend_canvas: tk.Canvas
    expense_legend_frame: tk.Frame
    daily_bar_canvas: tk.Canvas
    monthly_bar_canvas: tk.Canvas


def update_pie_month_options(
    pie_month_menu: ttk.Combobox | None,
    pie_month_var: tk.StringVar | None,
    records: Any,
) -> None:
    if pie_month_menu is None or pie_month_var is None:
        return
    months = extract_months(records)
    current_month = datetime.now().strftime("%Y-%m")
    if current_month not in months:
        months.append(current_month)
    months = sorted(set(months))

    all_time_label = tr("infographics.all_time", "Все время")
    values = [all_time_label] + months
    pie_month_menu["values"] = values

    current_value = pie_month_var.get()
    if not current_value:
        pie_month_var.set(all_time_label)
        return
    if current_value != all_time_label and current_value not in months:
        pie_month_var.set(months[-1] if months else all_time_label)


def draw_expense_pie(
    *,
    pie_month_var: tk.StringVar | None,
    expense_pie_canvas: tk.Canvas | None,
    expense_legend_canvas: tk.Canvas | None,
    expense_legend_frame: tk.Frame | None,
    records: Any,
    format_money: Callable[[float], str] | None = None,
) -> None:
    if (
        pie_month_var is None
        or expense_pie_canvas is None
        or expense_legend_frame is None
        or expense_legend_canvas is None
    ):
        return
    palette = get_palette()
    try:
        expense_pie_canvas.configure(
            bg=palette.surface_elevated,
            highlightbackground=palette.border_soft,
        )
        expense_legend_canvas.configure(
            bg=palette.surface_elevated,
            highlightbackground=palette.border_soft,
        )
        expense_legend_frame.configure(bg=palette.surface_elevated)
    except tk.TclError:
        pass

    month_value = pie_month_var.get()
    filtered = records
    all_time_label = tr("infographics.all_time", "Все время")
    if month_value and month_value != all_time_label:
        filtered = _filter_records_by_month(records, month_value)
    totals = aggregate_expenses_by_category(filtered)
    data = [(key, value) for key, value in totals.items() if value > 0]
    data.sort(key=lambda item: item[1], reverse=True)
    grouped_other = len(data) > 10
    data = _group_minor_categories(data, max_slices=10)

    expense_pie_canvas.delete("all")
    for child in expense_legend_frame.winfo_children():
        child.destroy()

    if not data:
        expense_pie_canvas.create_text(
            10,
            10,
            anchor="nw",
            text=tr("common.empty", "Нет данных для отображения"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return

    width = max(expense_pie_canvas.winfo_width(), 220)
    height = max(expense_pie_canvas.winfo_height(), 220)
    usable_w = max(width - 32, 120)
    usable_h = max(height - 32, 120)
    radius = max(52, min(usable_w * 0.42, usable_h * 0.48))
    center_x = max(radius + 16, min(width * 0.42, width - radius - 16))
    center_y = height / 2
    x0 = center_x - radius
    y0 = center_y - radius
    x1 = center_x + radius
    y1 = center_y + radius

    colors = _generate_colors(len(data))

    total = sum(value for _, value in data)
    start = 90.0
    legend_font = tkfont.nametofont("TkDefaultFont").copy()
    legend_font.configure(size=8)
    amount_font = legend_font
    for index, (category, value) in enumerate(data):
        extent = (value / total) * 360
        color = (
            palette.chart_empty
            if grouped_other and index == len(data) - 1
            else colors[index % len(colors)]
        )
        expense_pie_canvas.create_arc(
            x0,
            y0,
            x1,
            y1,
            start=start,
            extent=-extent,
            fill=color,
            outline=palette.chart_outline,
        )
        start -= extent

        cleaned_category = _clean_category(category)
        legend_row = tk.Frame(expense_legend_frame, bg=palette.surface_elevated)
        legend_row.pack(fill="x", anchor="w", pady=1, padx=6)
        legend_row.grid_columnconfigure(1, weight=1)
        legend_row.grid_columnconfigure(2, weight=0)
        color_box = tk.Canvas(
            legend_row,
            width=10,
            height=10,
            highlightthickness=0,
            bg=palette.surface_elevated,
        )
        color_box.create_rectangle(0, 0, 10, 10, fill=color, outline=color)
        color_box.grid(row=0, column=0, sticky="nw", padx=(0, 6), pady=2)
        amount_text = (format_money or (lambda amount: f"{amount:.2f}"))(value)
        available_width = _legend_category_max_width(
            canvas_width=expense_legend_canvas.winfo_width(),
            amount_text=amount_text,
            amount_font=amount_font,
        )
        category_label = tk.Label(
            legend_row,
            text=_fit_legend_category(
                cleaned_category,
                font=legend_font,
                max_width=available_width,
            ),
            font=legend_font,
            anchor="w",
            bg=palette.surface_elevated,
            fg=palette.chart_text,
        )
        category_label.grid(row=0, column=1, sticky="ew")
        tk.Label(
            legend_row,
            text=amount_text,
            font=amount_font,
            justify="right",
            anchor="e",
            bg=palette.surface_elevated,
            fg=palette.chart_text,
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))


def _group_minor_categories(
    data: list[tuple[str, float]], max_slices: int
) -> list[tuple[str, float]]:
    if len(data) <= max_slices:
        return data

    major = data[: max_slices - 1]
    other_total = sum(value for _, value in data[max_slices - 1 :])
    major.append((tr("common.other", "Other"), other_total))
    return major


def _clean_category(category: str) -> str:
    if not category:
        return category
    cleaned = category.replace("\r", " ").replace("\n", " ")
    return " ".join(cleaned.split())


def _fit_legend_category(category: str, *, font: tkfont.Font, max_width: int) -> str:
    text = str(category or "")
    if not text:
        return text
    if font.measure(text) <= max_width:
        return text
    ellipsis = "..."
    ellipsis_width = font.measure(ellipsis)
    if ellipsis_width >= max_width:
        return ellipsis
    trimmed = text
    while trimmed and font.measure(trimmed) + ellipsis_width > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed.rstrip()}{ellipsis}"


def _legend_category_max_width(
    *, canvas_width: int, amount_text: str, amount_font: tkfont.Font
) -> int:
    safe_canvas_width = max(canvas_width, 120)
    amount_width = amount_font.measure(str(amount_text or ""))
    # Reserve space for color box, paddings, and a small breathing gap before the amount.
    reserved_width = amount_width + 34
    return max(72, safe_canvas_width - reserved_width)


def _filter_records_by_month(records: Any, month_value: str) -> list[Any]:
    try:
        year, month = map(int, month_value.split("-"))
    except (TypeError, ValueError, AttributeError):
        return records

    filtered: list[Any] = []
    for record in records:
        try:
            if isinstance(record.date, date):
                dt = datetime.combine(record.date, datetime.min.time())
            else:
                dt = datetime.strptime(record.date, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if dt.year == year and dt.month == month:
            filtered.append(record)
    return filtered


def _generate_colors(count: int) -> list[str]:
    if count <= 0:
        return []
    base_palette = list(get_palette().chart_series)

    if count <= len(base_palette):
        return base_palette[:count]

    colors = list(base_palette)
    remaining = count - len(colors)
    for idx in range(remaining):
        hue = (idx * 360 / max(1, remaining)) % 360
        colors.append(f"#{_hsl_to_hex(hue, 70, 50)}")
    return colors


def _hsl_to_hex(hue: float, saturation: float, lightness: float) -> str:
    saturation /= 100
    lightness /= 100

    c = (1 - abs(2 * lightness - 1)) * saturation
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = lightness - c / 2

    if 0 <= hue < 60:
        r, g, b = c, x, 0
    elif 60 <= hue < 120:
        r, g, b = x, c, 0
    elif 120 <= hue < 180:
        r, g, b = 0, c, x
    elif 180 <= hue < 240:
        r, g, b = 0, x, c
    elif 240 <= hue < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    red = int((r + m) * 255)
    green = int((g + m) * 255)
    blue = int((b + m) * 255)
    return f"{red:02x}{green:02x}{blue:02x}"


def build_infographics_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    on_chart_filter_change: Callable[..., None],
    on_refresh_charts: Callable[[], None],
    on_legend_mousewheel: Callable[[tk.Event], None],
    bind_all: Callable[[str, Callable[[tk.Event], None]], str],
    after: Callable[[int, Callable[[], None]], str],
    after_cancel: Callable[[str], None],
) -> InfographicsTabBindings:
    palette = get_palette()
    parent.grid_columnconfigure(0, weight=1, uniform="infographics_top")
    parent.grid_columnconfigure(1, weight=1, uniform="infographics_top")
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_rowconfigure(2, weight=1)

    pie_card = create_card_section(
        parent, tr("infographics.expenses_by_category", "Расходы по категориям")
    )
    pie_card.grid(row=1, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    pie_frame = pie_card.winfo_children()[-1]
    pie_frame.grid_columnconfigure(0, weight=2)
    pie_frame.grid_columnconfigure(1, weight=1)
    pie_frame.grid_rowconfigure(1, weight=1)

    pie_controls = ttk.Frame(pie_frame, style="CardBody.TFrame")
    pie_controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 0))
    pie_controls.grid_columnconfigure(1, weight=1)
    ttk.Label(
        pie_controls,
        text=tr("infographics.month", "Месяц:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")

    pie_month_var = tk.StringVar()
    pie_month_menu = ttk.Combobox(
        pie_controls,
        textvariable=pie_month_var,
        values=[],
        state="readonly",
    )
    pie_month_menu.grid(row=0, column=1, sticky="w", padx=(6, 0))
    pie_month_var.trace_add("write", on_chart_filter_change)

    daily_card = create_card_section(
        parent, tr("infographics.daily_cashflow", "Доходы и расходы по дням месяца")
    )
    daily_card.grid(row=1, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=PAD_LG)
    daily_frame = daily_card.winfo_children()[-1]
    daily_frame.grid_columnconfigure(0, weight=1)
    daily_frame.grid_rowconfigure(1, weight=1)

    monthly_card = create_card_section(
        parent, tr("infographics.monthly_cashflow", "Доходы и расходы по месяцам года")
    )
    monthly_card.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=PAD_XL, pady=(0, PAD_LG))
    monthly_frame = monthly_card.winfo_children()[-1]
    monthly_frame.grid_columnconfigure(0, weight=1)
    monthly_frame.grid_rowconfigure(1, weight=1)

    expense_pie_canvas = tk.Canvas(
        pie_frame,
        height=240,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    expense_pie_canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 4), pady=10)

    legend_container = ttk.Frame(pie_frame)
    legend_container.grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=10)
    legend_container.grid_columnconfigure(0, weight=1)
    legend_container.grid_rowconfigure(0, weight=1)
    expense_legend_canvas = tk.Canvas(
        legend_container,
        height=240,
        highlightthickness=0,
        bg=palette.surface_elevated,
    )
    expense_legend_canvas.grid(row=0, column=0, sticky="nsew")
    legend_scroll = ttk.Scrollbar(
        legend_container,
        orient="vertical",
        command=expense_legend_canvas.yview,
    )
    legend_scroll.grid(row=0, column=1, sticky="ns")
    expense_legend_canvas.configure(yscrollcommand=legend_scroll.set)

    expense_legend_frame = tk.Frame(expense_legend_canvas, bg=palette.surface_elevated)
    expense_legend_canvas.create_window(
        (0, 0),
        window=expense_legend_frame,
        anchor="nw",
        tags=("legend_window",),
    )

    def _update_legend_scroll(_event: object | None = None) -> None:
        expense_legend_canvas.configure(scrollregion=expense_legend_canvas.bbox("all"))
        bbox = expense_legend_canvas.bbox("all")
        if bbox:
            width = max(expense_legend_canvas.winfo_width(), bbox[2] - bbox[0])
            expense_legend_canvas.itemconfigure("legend_window", width=max(width - 10, 0))

    expense_legend_frame.bind("<Configure>", _update_legend_scroll)
    expense_legend_canvas.bind("<Configure>", _update_legend_scroll)
    expense_legend_canvas.bind("<MouseWheel>", on_legend_mousewheel)
    expense_legend_frame.bind("<MouseWheel>", on_legend_mousewheel)

    bind_all("<MouseWheel>", on_legend_mousewheel)

    daily_controls = ttk.Frame(daily_frame, style="CardBody.TFrame")
    daily_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
    daily_controls.grid_columnconfigure(1, weight=1)
    ttk.Label(
        daily_controls,
        text=tr("infographics.month", "Месяц:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")

    chart_month_var = tk.StringVar()
    chart_month_menu = ttk.Combobox(
        daily_controls,
        textvariable=chart_month_var,
        values=[],
        state="readonly",
    )
    chart_month_menu.grid(row=0, column=1, sticky="w", padx=(6, 0))
    chart_month_var.trace_add("write", on_chart_filter_change)

    daily_bar_canvas = tk.Canvas(
        daily_frame,
        height=220,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    daily_bar_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    monthly_controls = ttk.Frame(monthly_frame, style="CardBody.TFrame")
    monthly_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
    monthly_controls.grid_columnconfigure(1, weight=1)
    ttk.Label(
        monthly_controls,
        text=tr("infographics.year", "Год:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")

    chart_year_var = tk.StringVar()
    chart_year_menu = ttk.Combobox(
        monthly_controls,
        textvariable=chart_year_var,
        values=[],
        state="readonly",
    )
    chart_year_menu.grid(row=0, column=1, sticky="w", padx=(6, 0))
    chart_year_var.trace_add("write", on_chart_filter_change)

    monthly_bar_canvas = tk.Canvas(
        monthly_frame,
        height=220,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    monthly_bar_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    chart_redraw_job: str | None = None

    def _schedule_redraw(_event: object | None = None) -> None:
        nonlocal chart_redraw_job
        if chart_redraw_job is not None:
            try:
                after_cancel(chart_redraw_job)
            except (tk.TclError, RuntimeError):
                pass
        chart_redraw_job = after(120, on_refresh_charts)

    expense_pie_canvas.bind("<Configure>", _schedule_redraw)
    daily_bar_canvas.bind("<Configure>", _schedule_redraw)
    monthly_bar_canvas.bind("<Configure>", _schedule_redraw)

    return InfographicsTabBindings(
        pie_month_var=pie_month_var,
        pie_month_menu=pie_month_menu,
        chart_month_var=chart_month_var,
        chart_month_menu=chart_month_menu,
        chart_year_var=chart_year_var,
        chart_year_menu=chart_year_menu,
        expense_pie_canvas=expense_pie_canvas,
        expense_legend_canvas=expense_legend_canvas,
        expense_legend_frame=expense_legend_frame,
        daily_bar_canvas=daily_bar_canvas,
        monthly_bar_canvas=monthly_bar_canvas,
    )
