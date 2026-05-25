from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import cast

from gui.i18n import tr
from gui.record_colors import KIND_TO_FOREGROUND
from gui.ui_helpers import attach_treeview_scrollbars, enable_treeview_column_autosize
from gui.ui_theme import PAD_LG, create_card_section, enable_treeview_zebra


def build_reports_body(
    owner: tk.Misc,
) -> tuple[
    ttk.Frame, ttk.Treeview, ttk.Treeview, tk.Misc, dict[str, ttk.Label], dict[str, ttk.Label]
]:
    body = ttk.PanedWindow(owner, orient=tk.HORIZONTAL, style="Reports.TPanedwindow")
    body.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

    left = ttk.Frame(body)
    left.grid_rowconfigure(1, weight=1)
    left.grid_columnconfigure(0, weight=1)
    body.add(left, weight=3)

    right = ttk.Frame(body)
    right.grid_rowconfigure(0, weight=1)
    right.grid_columnconfigure(0, weight=1)
    body.add(right, weight=2)

    summary_card = create_card_section(left, tr("common.summary", "Сводка"))
    summary_card.grid(row=0, column=0, sticky="ew")
    summary_frame = summary_card.winfo_children()[-1]
    summary_frame.grid_columnconfigure(1, weight=1)
    summary_labels: dict[str, ttk.Label] = {}
    summary_values: dict[str, ttk.Label] = {}
    for row_index, (label_key, label_text) in enumerate(
        [
            (
                "net_worth_fixed",
                tr("reports.summary.net_worth_fixed", "Чистый капитал (исторический):"),
            ),
            (
                "net_worth_current",
                tr("reports.summary.net_worth_current", "Чистый капитал (текущий):"),
            ),
            ("initial_balance", tr("reports.summary.initial_balance", "Начальный баланс:")),
            ("records_total", tr("reports.summary.records_total", "Сумма операций:")),
            ("final_balance", tr("reports.summary.final_balance", "Итоговый баланс:")),
            ("fx_difference", tr("reports.summary.fx_difference", "Курсовая разница:")),
        ]
    ):
        label_widget = ttk.Label(summary_frame, text=label_text, style="CardText.TLabel")
        label_widget.grid(row=row_index, column=0, sticky="w")
        value_label = ttk.Label(summary_frame, text="—", style="CardText.TLabel")
        value_label.grid(row=row_index, column=1, sticky="e")
        summary_labels[label_key] = label_widget
        summary_values[label_key] = value_label

    operations_card = create_card_section(left, tr("tab.operations", "Операции"))
    operations_card.grid(row=1, column=0, sticky="nsew", pady=(PAD_LG, 0))
    operations_container = cast(ttk.Frame, operations_card.winfo_children()[-1])
    operations_container.grid_rowconfigure(0, weight=1)
    operations_container.grid_columnconfigure(0, weight=1)

    operations_tree = ttk.Treeview(
        operations_container,
        columns=("date", "type", "category", "tags", "amount"),
        show="headings",
        selectmode="browse",
    )
    enable_treeview_zebra(operations_tree)
    operations_tree.heading("date", text=tr("common.date_short", "Дата"))
    operations_tree.heading("type", text=tr("common.type_short", "Тип"))
    operations_tree.heading("category", text=tr("common.category_short", "Категория"))
    operations_tree.heading("tags", text=tr("common.tags_short", "Теги"))
    operations_tree.heading("amount", text=tr("common.amount_short", "Сумма"))
    operations_tree.column("date", width=100, minwidth=100, stretch=False, anchor="w")
    operations_tree.column("type", width=200, minwidth=200, stretch=False, anchor="w")
    operations_tree.column("category", width=260, minwidth=220, stretch=False, anchor="w")
    operations_tree.column("tags", width=220, minwidth=160, stretch=True, anchor="w")
    operations_tree.column("amount", width=100, minwidth=100, anchor="e")
    enable_treeview_column_autosize(
        operations_tree,
        columns=("category", "tags"),
        max_width=420,
    )
    operations_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(
        operations_container,
        operations_tree,
        row=0,
        column=0,
        horizontal=False,
    )
    for kind, color in KIND_TO_FOREGROUND.items():
        try:
            operations_tree.tag_configure(kind, foreground=color)
        except tk.TclError:
            pass

    monthly_card = create_card_section(
        right,
        tr("reports.monthly_summary", "Помесячная сводка"),
        body_padding=(4, 4, 4, 4),
    )
    monthly_card.grid(row=0, column=0, sticky="nsew")
    monthly_frame = monthly_card.winfo_children()[-1]
    monthly_frame.grid_rowconfigure(0, weight=1)
    monthly_frame.grid_columnconfigure(0, weight=1)

    monthly_tree = ttk.Treeview(
        monthly_frame,
        columns=("month", "income", "expense"),
        show="headings",
        selectmode="none",
        height=12,
    )
    enable_treeview_zebra(monthly_tree)
    monthly_tree.heading("month", text=tr("common.month", "Месяц"))
    monthly_tree.heading("income", text=tr("reports.income", "Доход"))
    monthly_tree.heading("expense", text=tr("reports.expense", "Расход"))
    monthly_tree.column("month", width=50, minwidth=50, anchor="w")
    monthly_tree.column("income", width=90, minwidth=90, anchor="e")
    monthly_tree.column("expense", width=90, minwidth=90, anchor="e")
    monthly_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(
        monthly_frame,
        monthly_tree,
        row=0,
        column=0,
        horizontal=False,
        padx=0,
        pady=0,
    )

    _bind_fixed_width_columns(operations_tree)
    _bind_fixed_width_columns(monthly_tree)
    return (
        operations_container,
        operations_tree,
        monthly_tree,
        summary_frame,
        summary_labels,
        summary_values,
    )


def _block_separator_resize(event: tk.Event) -> str | None:
    if isinstance(event.widget, ttk.Treeview):
        region = event.widget.identify_region(event.x, event.y)
        if region == "separator":
            return "break"
    return None


def _bind_fixed_width_columns(tree: ttk.Treeview) -> None:
    tree.bind("<Button-1>", _block_separator_resize, add="+")
