from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from gui.i18n import tr
from gui.ui_theme import get_palette


def _draw_net_worth_line(
    canvas: tk.Canvas,
    data: list,
    *,
    format_amount: Callable[[float], str] | None = None,
) -> None:
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

    y_label = format_amount or (lambda value: f"{value:,.0f}")
    canvas.create_text(
        pad["left"] - 4,
        pad["top"],
        text=y_label(float(max_v)),
        fill=palette.chart_empty,
        font=("Segoe UI", 8),
        anchor="e",
    )
    canvas.create_text(
        pad["left"] - 4,
        h - pad["bottom"],
        text=y_label(float(min_v)),
        fill=palette.chart_empty,
        font=("Segoe UI", 8),
        anchor="e",
    )


def _draw_breakdown_pie(
    canvas: tk.Canvas,
    data: list,
    *,
    format_amount: Callable[[float], str] | None = None,
) -> None:
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
    total = sum(float(getattr(item, "total_base", 0.0)) for item in data)
    if total <= 0:
        return

    rows = list(data)
    show_other_legend = False
    if len(rows) > 10:
        other_total = sum(float(getattr(item, "total_base", 0.0)) for item in rows[9:])
        rows = rows[:9]
        if other_total > 0:
            show_other_legend = True
            rows.append(
                {
                    "label": tr("common.other", "Прочие"),
                    "total_base": other_total,
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
            value = float(item.get("total_base", 0.0))
            color = str(item.get("color", "") or palette.chart_empty)
        else:
            value = float(getattr(item, "total_base", 0.0))
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
