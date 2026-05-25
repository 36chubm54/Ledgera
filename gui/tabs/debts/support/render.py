from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment
from gui.i18n import tr
from gui.ui_theme import get_palette


def _segment_widths(*, total: int, bar_w: int, paid: int, forgiven: int) -> tuple[int, int, int]:
    total = max(int(total), 1)
    bar_w = max(int(bar_w), 1)
    paid = max(0, int(paid))
    forgiven = max(0, int(forgiven))

    paid_w = int(bar_w * paid / total) if paid > 0 else 0
    forgiven_w = int(bar_w * forgiven / total) if forgiven > 0 else 0

    if paid > 0 and paid_w == 0:
        paid_w = 1
    if forgiven > 0 and forgiven_w == 0:
        forgiven_w = 1

    overflow = max(0, paid_w + forgiven_w - bar_w)
    while overflow > 0 and (paid_w > 1 or forgiven_w > 1):
        if paid_w >= forgiven_w and paid_w > 1:
            paid_w -= 1
        elif forgiven_w > 1:
            forgiven_w -= 1
        overflow -= 1

    open_w = max(0, bar_w - paid_w - forgiven_w)
    return paid_w, forgiven_w, open_w


def _draw_debt_progress(
    canvas: tk.Canvas,
    debt: Debt | None,
    payments: list[DebtPayment],
    *,
    format_amount: Callable[[float], str] | None = None,
) -> None:
    palette = get_palette()
    canvas.delete("all")
    width = max(canvas.winfo_width(), 420)
    height = max(canvas.winfo_height(), 70)
    canvas.configure(
        height=height,
        bg=palette.surface_elevated,
        highlightbackground=palette.border_soft,
    )
    if debt is None or debt.total_amount_minor <= 0:
        canvas.create_text(
            width // 2,
            height // 2,
            text=tr("debts.progress.empty", "Выберите долг, чтобы увидеть прогресс"),
            fill=palette.text_muted,
            font=("Segoe UI", 10),
        )
        return

    total = max(1, int(debt.total_amount_minor))
    remaining = int(debt.remaining_amount_minor)
    forgiven = sum(
        int(payment.principal_paid_minor)
        for payment in payments
        if payment.operation_type is DebtOperationType.DEBT_FORGIVE
    )
    paid = max(0, total - remaining - forgiven)
    paid = max(0, min(total, paid))
    forgiven = max(0, min(total - paid, forgiven))
    open_amount = max(0, total - paid - forgiven)

    x0 = 20
    y0 = 18
    bar_w = max(120, width - 40)
    bar_h = 22
    debt_color = palette.warning if debt.kind is DebtKind.DEBT else palette.accent_blue
    forgive_color = palette.text_muted
    track_color = palette.surface_alt
    paid_w, forgiven_w, open_w = _segment_widths(
        total=total,
        bar_w=bar_w,
        paid=paid,
        forgiven=forgiven,
    )

    canvas.create_rectangle(x0, y0, x0 + bar_w, y0 + bar_h, fill=track_color, outline="")
    current_x = x0
    for seg_w, amount, color, is_open_segment in (
        (paid_w, paid, debt_color, False),
        (forgiven_w, forgiven, forgive_color, False),
        (open_w, open_amount, palette.surface_elevated, True),
    ):
        if amount <= 0 or seg_w <= 0:
            continue
        if is_open_segment:
            canvas.create_rectangle(
                current_x,
                y0,
                x0 + bar_w,
                y0 + bar_h,
                fill=color,
                outline="",
            )
        else:
            canvas.create_rectangle(
                current_x,
                y0,
                current_x + seg_w,
                y0 + bar_h,
                fill=color,
                outline="",
            )
            current_x += seg_w

    canvas.create_rectangle(x0, y0, x0 + bar_w, y0 + bar_h, outline=palette.border_soft, width=1)
    canvas.create_text(
        x0,
        y0 + bar_h + 14,
        anchor="w",
        text=tr(
            "debts.progress.summary",
            "Погашено: {paid}   Списано: {forgiven}   Осталось: {remaining}",
            paid=(format_amount or (lambda value: f"{value:.2f}"))(paid / 100),
            forgiven=(format_amount or (lambda value: f"{value:.2f}"))(forgiven / 100),
            remaining=(format_amount or (lambda value: f"{value:.2f}"))(remaining / 100),
        ),
        fill=palette.chart_text,
        font=("Segoe UI", 9),
    )
