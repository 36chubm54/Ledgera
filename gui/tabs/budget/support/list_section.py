from __future__ import annotations

import tkinter as tk

from domain.budget import BudgetResult, BudgetStatus, PaceStatus
from gui.ui_theme import get_palette

from .actions import _visual_budget_state


def _draw_progress_bars(canvas: tk.Canvas, results: list[BudgetResult]) -> None:
    palette = get_palette()
    pace_fill = {
        PaceStatus.ON_TRACK: palette.success,
        PaceStatus.OVERPACE: palette.warning,
        PaceStatus.OVERSPENT: palette.danger,
    }
    canvas.delete("all")
    canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    if not results:
        return

    width = max(canvas.winfo_width(), 400)
    bar_h = 12
    gap = 7
    pad_l = 115
    pad_r = 48
    bar_w = max(40, width - pad_l - pad_r)

    total_h = len(results) * (bar_h + gap) + gap
    canvas.configure(height=max(40, total_h))

    for index, result in enumerate(results):
        y = gap + index * (bar_h + gap)
        canvas.create_text(
            pad_l - 6,
            y + bar_h // 2,
            text=result.budget.category[:15],
            anchor="e",
            fill=palette.chart_text,
            font=("Segoe UI", 9),
        )
        canvas.create_rectangle(
            pad_l,
            y,
            pad_l + bar_w,
            y + bar_h,
            fill=palette.surface_alt,
            outline="",
        )

        fill_w = min(bar_w, max(0, int(bar_w * result.usage_pct / 100.0)))
        if fill_w > 0:
            visual_state = _visual_budget_state(result)
            if visual_state in {"future", "expired"}:
                fill_color = palette.text_muted
            else:
                fill_color = pace_fill.get(result.pace_status, palette.success)
            canvas.create_rectangle(
                pad_l,
                y,
                pad_l + fill_w,
                y + bar_h,
                fill=fill_color,
                outline="",
            )

        if result.status == BudgetStatus.ACTIVE:
            tx = pad_l + max(0, min(bar_w, int(bar_w * result.time_pct / 100.0)))
            canvas.create_line(tx, y - 1, tx, y + bar_h + 1, fill=palette.accent_blue, width=2)

        canvas.create_text(
            pad_l + bar_w + 6,
            y + bar_h // 2,
            text=f"{result.usage_pct:.0f}%",
            anchor="w",
            fill=palette.chart_text,
            font=("Segoe UI", 9),
        )
