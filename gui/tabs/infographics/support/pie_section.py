"""Pie chart helpers for the infographics tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from datetime import date, datetime
from tkinter import font as tkfont
from tkinter import ttk
from typing import Protocol, cast

from domain.records import Record
from gui.i18n import tr
from gui.ui_theme import get_palette
from utils.charting import aggregate_expenses_by_category, extract_months


class DatedValue(Protocol):
    date: date | str


def update_pie_month_options(
    pie_month_menu: ttk.Combobox | None,
    pie_month_var: tk.StringVar | None,
    records: Sequence[object],
) -> None:
    if pie_month_menu is None or pie_month_var is None:
        return
    months = extract_months(cast(Sequence[Record], records))
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
    records: Sequence[object],
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
    filtered: Sequence[object] = records
    all_time_label = tr("infographics.all_time", "Все время")
    if month_value and month_value != all_time_label:
        filtered = _filter_records_by_month(records, month_value)
    totals = aggregate_expenses_by_category(cast(Sequence[Record], filtered))
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
    reserved_width = amount_width + 34
    return max(72, safe_canvas_width - reserved_width)


def _filter_records_by_month(records: Sequence[object], month_value: str) -> list[object]:
    try:
        year, month = map(int, month_value.split("-"))
    except (TypeError, ValueError, AttributeError):
        return list(records)

    filtered: list[object] = []
    for record in records:
        try:
            record_date = cast(DatedValue, record).date
            if isinstance(record_date, date):
                dt = datetime.combine(record_date, datetime.min.time())
            else:
                dt = datetime.strptime(str(record_date), "%Y-%m-%d")
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
    for index in range(remaining):
        hue = (index * 360 / max(1, remaining)) % 360
        colors.append(f"#{_hsl_to_hex(hue, 70, 50)}")
    return colors


def _hsl_to_hex(hue: float, saturation: float, lightness: float) -> str:
    saturation /= 100
    lightness /= 100

    c = (1 - abs(2 * lightness - 1)) * saturation
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = lightness - c / 2

    if 0 <= hue < 60:
        red, green, blue = c, x, 0
    elif 60 <= hue < 120:
        red, green, blue = x, c, 0
    elif 120 <= hue < 180:
        red, green, blue = 0, c, x
    elif 180 <= hue < 240:
        red, green, blue = 0, x, c
    elif 240 <= hue < 300:
        red, green, blue = x, 0, c
    else:
        red, green, blue = c, 0, x

    red_i = int((red + m) * 255)
    green_i = int((green + m) * 255)
    blue_i = int((blue + m) * 255)
    return f"{red_i:02x}{green_i:02x}{blue_i:02x}"
