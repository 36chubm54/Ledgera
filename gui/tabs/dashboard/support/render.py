"""Render helpers for dashboard charts and goal cards."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from domain.dashboard import DashboardAllocationSlice, DashboardTrendPoint
from domain.goal import GoalProgress
from gui.i18n import tr
from gui.ui_theme import get_palette


def _draw_trend(
    canvas: tk.Canvas,
    data: list[DashboardTrendPoint],
    *,
    format_amount: Callable[[float], str] | None = None,
) -> None:
    canvas.delete("all")
    palette = get_palette()
    canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    width = max(canvas.winfo_width(), 320)
    height = max(canvas.winfo_height(), 200)
    pad = {"left": 54, "right": 18, "top": 20, "bottom": 34}

    if not data:
        canvas.create_text(
            width // 2,
            height // 2,
            text=tr("dashboard.trend.empty", "Пока нет данных по динамике"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return

    values = [float(point.balance) for point in data]
    min_value = min(values)
    max_value = max(values)
    span = max_value - min_value
    padding_value = max(span * 0.08, abs(max_value or min_value or 1.0) * 0.02, 1.0)
    chart_min = min_value - padding_value
    chart_max = max_value + padding_value
    chart_span = (chart_max - chart_min) or 1.0

    def to_xy(index: int, value: float) -> tuple[float, float]:
        x = pad["left"] + (width - pad["left"] - pad["right"]) * index / max(1, len(data) - 1)
        y = pad["top"] + (height - pad["top"] - pad["bottom"]) * (
            1 - (value - chart_min) / chart_span
        )
        return x, y

    canvas.create_rectangle(
        pad["left"],
        pad["top"],
        width - pad["right"],
        height - pad["bottom"],
        outline=palette.border_soft,
        width=1,
    )
    canvas.create_line(
        pad["left"],
        height - pad["bottom"],
        width - pad["right"],
        height - pad["bottom"],
        fill=palette.chart_axis,
        width=1,
    )

    if chart_min < 0 < chart_max:
        _, zero_y = to_xy(0, 0.0)
        canvas.create_line(
            pad["left"],
            zero_y,
            width - pad["right"],
            zero_y,
            fill=palette.chart_grid,
            dash=(4, 4),
        )

    for index in range(len(values) - 1):
        x1, y1 = to_xy(index, values[index])
        x2, y2 = to_xy(index + 1, values[index + 1])
        canvas.create_line(x1, y1, x2, y2, fill=palette.accent_blue, width=3, smooth=True)

    for index, point in enumerate(data):
        x, y = to_xy(index, float(point.balance))
        canvas.create_oval(
            x - 3,
            y - 3,
            x + 3,
            y + 3,
            fill=palette.accent_blue,
            outline=palette.chart_outline,
            width=1,
        )

    step = max(1, len(data) // 5)
    for index, point in enumerate(data):
        if index % step == 0 or index == len(data) - 1:
            x, _ = to_xy(index, float(point.balance))
            canvas.create_text(
                x,
                height - pad["bottom"] + 12,
                text=str(point.month),
                fill=palette.chart_empty,
                font=("Segoe UI", 8),
            )

    y_label = format_amount or (lambda value: f"{value:,.0f}")
    canvas.create_text(
        pad["left"] - 6,
        pad["top"],
        text=y_label(float(max_value)),
        fill=palette.chart_empty,
        font=("Segoe UI", 8),
        anchor="e",
    )
    canvas.create_text(
        pad["left"] - 6,
        height - pad["bottom"],
        text=y_label(float(min_value)),
        fill=palette.chart_empty,
        font=("Segoe UI", 8),
        anchor="e",
    )


def _draw_allocation(
    canvas: tk.Canvas,
    data: list[DashboardAllocationSlice],
    *,
    format_money: Callable[[float], str] | None = None,
) -> None:
    canvas.delete("all")
    palette = get_palette()
    canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    width = max(canvas.winfo_width(), 280)
    height = max(canvas.winfo_height(), 220)
    center_x = width * 0.35
    center_y = height * 0.48
    radius = min(width * 0.23, height * 0.34)
    inner_radius = radius * 0.58

    if not data:
        canvas.create_text(
            width // 2,
            height // 2,
            text=tr("dashboard.allocation.empty_assets", "Активы пока не добавлены"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return

    total = sum(float(item.amount_base) for item in data)
    if total <= 0:
        canvas.create_text(
            width // 2,
            height // 2,
            text=tr("dashboard.allocation.empty", "Нет данных для структуры активов"),
            fill=palette.chart_empty,
            font=("Segoe UI", 11),
        )
        return

    money_text = format_money or (lambda value: f"{value:,.0f}")
    start_angle = 90.0
    for index, item in enumerate(data):
        amount = float(item.amount_base)
        sweep = amount / total * 360.0
        color = palette.chart_series[index % len(palette.chart_series)]
        canvas.create_arc(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            start=start_angle,
            extent=-sweep,
            fill=color,
            outline=palette.chart_outline,
            width=2,
        )
        start_angle -= sweep

    canvas.create_oval(
        center_x - inner_radius,
        center_y - inner_radius,
        center_x + inner_radius,
        center_y + inner_radius,
        fill=palette.surface_elevated,
        outline=palette.surface_elevated,
    )
    canvas.create_text(
        center_x,
        center_y - 8,
        text=tr("dashboard.assets", "Активы"),
        fill=palette.chart_empty,
        font=("Segoe UI", 9),
    )
    canvas.create_text(
        center_x,
        center_y + 12,
        text=money_text(total),
        fill=palette.chart_text,
        font=("Segoe UI", 10, "bold"),
    )

    legend_x = width * 0.62
    legend_y = 30
    for index, item in enumerate(data[:6]):
        y = legend_y + index * 28
        color = palette.chart_series[index % len(palette.chart_series)]
        canvas.create_rectangle(legend_x, y, legend_x + 12, y + 12, fill=color, outline="")
        canvas.create_text(
            legend_x + 18,
            y + 1,
            anchor="nw",
            text=str(item.category).title(),
            fill=palette.chart_text,
            font=("Segoe UI", 9, "bold"),
        )
        canvas.create_text(
            legend_x + 18,
            y + 14,
            anchor="nw",
            text=f"{item.share_pct:.1f}% • {money_text(item.amount_base)}",
            fill=palette.chart_empty,
            font=("Segoe UI", 8),
        )


def _render_goals(container: ttk.Frame, goals: list[GoalProgress]) -> None:
    _render_goals_with_actions(container, goals, on_toggle_completed=None)


def _render_goals_with_actions(
    container: ttk.Frame,
    goals: list[GoalProgress],
    *,
    on_toggle_completed: Callable[[GoalProgress], None] | None,
    on_delete_goal: Callable[[GoalProgress], None] | None = None,
) -> None:
    for child in container.winfo_children():
        child.destroy()

    if not goals:
        empty = ttk.Label(
            container,
            text=tr("dashboard.goals.empty", "Цели пока не добавлены"),
            foreground="#6b7280",
        )
        empty.grid(row=0, column=0, sticky="w", padx=6, pady=6)
        return

    container.grid_columnconfigure(0, weight=1)
    for index, item in enumerate(goals):
        card = ttk.Frame(container, padding=(10, 10))
        card.grid(row=index, column=0, sticky="ew", padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)

        title = str(item.goal.title)
        status = (
            tr("dashboard.goal.completed", "Завершена")
            if item.is_completed
            else f"{item.progress_pct:.1f}%"
        )
        ttk.Label(card, text=title, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=status, foreground="#059669" if item.is_completed else "#2563eb").grid(
            row=0,
            column=1,
            sticky="e",
            padx=(12, 0),
        )

        details = f"{item.current_amount:,.2f} / {item.target_amount:,.2f} {item.goal.currency}"
        ttk.Label(card, text=details, foreground="#6b7280").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(4, 6),
        )

        progress = ttk.Progressbar(card, mode="determinate", maximum=100.0)
        progress.grid(row=2, column=0, columnspan=2, sticky="ew")
        progress["value"] = max(0.0, min(100.0, float(item.progress_pct)))

        if on_toggle_completed is not None:
            action_text = (
                tr("dashboard.goal.reopen", "Открыть снова")
                if item.is_completed
                else tr("dashboard.goal.complete", "Завершить")
            )
            ttk.Button(
                card,
                text=action_text,
                command=lambda goal_progress=item: on_toggle_completed(goal_progress),
            ).grid(row=0, column=2, sticky="e", padx=(12, 0))
        if on_delete_goal is not None:
            ttk.Button(
                card,
                text=tr("dashboard.goal.delete", "Удалить"),
                command=lambda goal_progress=item: on_delete_goal(goal_progress),
            ).grid(row=0, column=3, sticky="e", padx=(8, 0))

        if item.goal.target_date:
            ttk.Label(
                card,
                text=tr(
                    "dashboard.goal.target_date", "Целевая дата: {date}", date=item.goal.target_date
                ),
                foreground="#6b7280",
            ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
