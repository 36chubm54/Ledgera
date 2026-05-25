from __future__ import annotations

import tkinter as tk

# ruff: noqa: E501
from collections.abc import Callable
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any

from domain.debt import Debt, DebtKind, DebtPayment
from gui.i18n import tr
from gui.ui_helpers import attach_treeview_scrollbars, enable_treeview_column_autosize
from gui.ui_theme import create_card_section, enable_treeview_zebra

from .render import _draw_debt_progress


@dataclass(slots=True)
class DebtsHistorySection:
    debt_tree: ttk.Treeview
    history_tree: ttk.Treeview
    progress_canvas: tk.Canvas
    status_label: ttk.Label
    current_debt: Debt | None = None
    current_payments: list[DebtPayment] = field(default_factory=list)


def build_history_section(parent_right, parent_left, *, palette) -> DebtsHistorySection:
    debt_tree = ttk.Treeview(
        parent_right,
        show="headings",
        columns=("id", "contact", "kind", "total", "remaining", "status", "created"),
        height=10,
    )
    enable_treeview_zebra(debt_tree)
    for col, label, width, anchor in (
        ("id", "#", 45, "e"),
        ("contact", tr("debts.contact_short", "Контакт"), 140, "w"),
        ("kind", tr("common.type_short", "Тип"), 80, "center"),
        ("total", tr("debts.total", "Сумма"), 125, "e"),
        ("remaining", tr("debts.remaining", "Остаток"), 140, "e"),
        ("status", tr("common.status", "Статус"), 85, "center"),
        ("created", tr("debts.created", "Создан"), 95, "center"),
    ):
        debt_tree.heading(col, text=label)
        debt_tree.column(col, width=width, minwidth=width, anchor=anchor, stretch=col == "contact")  # type: ignore[arg-type]
    enable_treeview_column_autosize(debt_tree, columns=("contact",), max_width=320)
    debt_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(parent_right, debt_tree, row=0, column=0, horizontal=True)

    progress_canvas = tk.Canvas(
        parent_right,
        height=72,
        bg=palette.surface_elevated,
        highlightthickness=0,
        highlightbackground=palette.border_soft,
    )
    progress_canvas.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 8))

    history_card = create_card_section(parent_right, tr("common.history", "История"))
    history_card.grid(row=3, column=0, columnspan=2, sticky="nsew")
    history_frame = history_card.winfo_children()[-1]
    history_frame.grid_columnconfigure(0, weight=1)
    history_frame.grid_rowconfigure(0, weight=1)

    history_tree = ttk.Treeview(
        history_frame,
        show="headings",
        columns=("date", "operation", "amount", "write_off", "record"),
        height=8,
    )
    enable_treeview_zebra(history_tree)
    for col, label, width, anchor in (
        ("date", tr("common.date_short", "Дата"), 95, "center"),
        ("operation", tr("common.operation", "Операция"), 100, "w"),
        ("amount", tr("common.amount_short", "Сумма"), 125, "e"),
        ("write_off", tr("debts.write_off_short", "Списание"), 100, "center"),
        ("record", tr("debts.record_id", "ID записи"), 100, "center"),
    ):
        history_tree.heading(col, text=label)
        history_tree.column(
            col,
            width=width,
            minwidth=width,
            anchor=anchor,  # type: ignore[arg-type]
            stretch=col == "operation",
        )
    enable_treeview_column_autosize(history_tree, columns=("operation",), max_width=320)
    history_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(history_frame, history_tree, row=0, column=0, horizontal=True)
    history_tree.tag_configure("writeoff", foreground=palette.text_muted)

    status_label = ttk.Label(parent_left, text="")
    status_label.grid(row=2, column=0, sticky="w", pady=(8, 0))

    return DebtsHistorySection(
        debt_tree=debt_tree,
        history_tree=history_tree,
        progress_canvas=progress_canvas,
        status_label=status_label,
    )


def selected_debt(context, debt_tree: ttk.Treeview) -> Debt | None:
    selection = debt_tree.selection()
    if not selection:
        return None
    debt_id = int(selection[0])
    return next((item for item in context.controller.get_debts() if int(item.id) == debt_id), None)


def redraw_progress(
    section: DebtsHistorySection, *, format_display_amount: Callable[[float, int], str]
) -> None:
    _draw_debt_progress(
        section.progress_canvas,
        section.current_debt,
        section.current_payments,
        format_amount=(
            None if section.current_debt is None else lambda value: format_display_amount(value, 2)
        ),
    )


def refresh_history(
    context,
    section: DebtsHistorySection,
    *,
    format_display_amount: Callable[[float, int], str],
) -> None:
    section.history_tree.delete(*section.history_tree.get_children())
    debt = selected_debt(context, section.debt_tree)
    if debt is None:
        section.current_debt = None
        section.current_payments = []
        _draw_debt_progress(section.progress_canvas, None, [], format_amount=None)
        return
    history = context.controller.get_debt_history(debt.id)
    section.current_debt = debt
    section.current_payments = history
    for payment in history:
        tag = ("writeoff",) if payment.is_write_off else ()
        section.history_tree.insert(
            "",
            "end",
            values=(
                payment.payment_date,
                payment.operation_type.value,
                format_display_amount(payment.principal_paid_minor / 100, 2),
                tr("common.yes", "Да") if payment.is_write_off else tr("common.no", "Нет"),
                "" if payment.record_id is None else str(payment.record_id),
            ),
            tags=tag,
        )
    section.progress_canvas.after(
        20, lambda: redraw_progress(section, format_display_amount=format_display_amount)
    )


def refresh_status_label(context, status_label: ttk.Label) -> None:
    debts = context.controller.get_debts()
    status_label.config(
        text=tr(
            "debts.status.summary",
            "{open_count} открыто / {total_count} всего",
            open_count=len(context.controller.get_open_debts()),
            total_count=len(debts),
        )
    )


def refresh_debt_tree(
    context,
    section: DebtsHistorySection,
    *,
    format_display_amount: Callable[[float, int], str],
) -> None:
    debts = context.controller.get_debts()
    current_selection = section.debt_tree.selection()
    section.debt_tree.delete(*section.debt_tree.get_children())
    section.debt_tree.heading(
        "total",
        text=f"{tr('debts.total', 'Сумма')} ({context.controller.get_display_currency_code()})",
    )
    section.debt_tree.heading(
        "remaining",
        text=f"{tr('debts.remaining', 'Остаток')} ({context.controller.get_display_currency_code()})",
    )
    section.history_tree.heading(
        "amount",
        text=f"{tr('common.amount_short', 'Сумма')} ({context.controller.get_display_currency_code()})",
    )

    def _display_kind(kind: DebtKind) -> str:
        return {
            DebtKind.DEBT: tr("debts.kind.debt", "Долг"),
            DebtKind.LOAN: tr("debts.kind.loan", "Заем"),
        }.get(kind, str(kind.value))

    def _display_status(status: Any) -> str:
        raw = str(getattr(status, "value", status))
        return {
            "open": tr("debts.status.open", "Открыт"),
            "closed": tr("debts.status.closed", "Закрыт"),
        }.get(raw, raw)

    for debt in debts:
        section.debt_tree.insert(
            "",
            "end",
            iid=str(debt.id),
            values=(
                debt.id,
                debt.contact_name,
                _display_kind(debt.kind),
                format_display_amount(debt.total_amount_minor / 100, 2),
                format_display_amount(debt.remaining_amount_minor / 100, 2),
                _display_status(debt.status),
                debt.created_at,
            ),
        )
    if current_selection and section.debt_tree.exists(current_selection[0]):
        section.debt_tree.selection_set(current_selection[0])
    elif debts:
        section.debt_tree.selection_set(str(debts[0].id))
    refresh_status_label(context, section.status_label)
    refresh_history(context, section, format_display_amount=format_display_amount)
