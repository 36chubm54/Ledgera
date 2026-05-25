from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.ui_helpers import enable_treeview_column_autosize
from gui.ui_theme import PAD_SM, enable_treeview_zebra

from .forms import mandatory_date_text


def build_mandatory_actions_row(
    parent: tk.Misc,
    *,
    format_var: tk.StringVar,
    on_edit: Callable[[], None],
    on_add_to_records: Callable[[], None],
    on_delete: Callable[[], None],
    on_delete_all: Callable[[], None],
    on_refresh: Callable[[], None],
    on_import: Callable[[], None],
    on_export: Callable[[], None],
    pad_x: int,
    pad_y: int,
    row_index: int = 3,
) -> None:
    actions = ttk.Frame(parent)
    actions.grid(
        row=row_index,
        column=0,
        columnspan=2,
        sticky="ew",
        padx=pad_x,
        pady=(PAD_SM, pad_y),
    )
    for idx in range(4):
        actions.grid_columnconfigure(idx, weight=1)

    ttk.Button(actions, text=tr("common.edit", "Редактировать"), command=on_edit).grid(
        row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
    )
    ttk.Button(
        actions,
        text=tr("mandatory.add_to_records", "Добавить в записи"),
        command=on_add_to_records,
    ).grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 6))
    ttk.Button(actions, text=tr("common.delete", "Удалить"), command=on_delete).grid(
        row=0, column=2, sticky="ew", padx=6, pady=(0, 6)
    )
    ttk.Button(
        actions,
        text=tr("mandatory.delete_all", "Удалить все"),
        command=on_delete_all,
    ).grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=(0, 6))
    ttk.Button(actions, text=tr("common.refresh", "Обновить"), command=on_refresh).grid(
        row=1, column=0, sticky="ew", padx=(0, 6)
    )
    format_combo = ttk.Combobox(
        actions,
        textvariable=format_var,
        values=["CSV", "XLSX"],
        state="readonly",
    )
    format_combo.grid(row=1, column=1, sticky="ew", padx=6)
    enable_wayland_combobox_support(format_combo, bind_down=False)
    ttk.Button(actions, text=tr("common.import", "Импорт"), command=on_import).grid(
        row=1, column=2, sticky="ew", padx=6
    )
    ttk.Button(actions, text=tr("common.export", "Экспорт"), command=on_export).grid(
        row=1, column=3, sticky="ew", padx=(6, 0)
    )


def build_mandatory_tree(parent: tk.Misc) -> tuple[ttk.Treeview, ttk.Scrollbar, ttk.Scrollbar]:
    mand_tree = ttk.Treeview(
        parent,
        show="headings",
        selectmode="browse",
        columns=(
            "index",
            "amount",
            "currency",
            "kzt",
            "category",
            "description",
            "period",
            "date",
            "autopay",
        ),
    )
    enable_treeview_zebra(mand_tree)
    for col, text, width, minwidth, stretch, anchor in (
        ("index", "#", 40, 40, False, "e"),
        ("amount", tr("mandatory.amount", "Сумма"), 90, 90, False, "e"),
        ("currency", tr("mandatory.currency_short", "Вал."), 60, 60, False, "center"),
        ("kzt", "KZT", 90, 90, False, "e"),
        ("category", tr("mandatory.category", "Категория"), 120, 120, False, "w"),
        ("description", tr("mandatory.description", "Описание"), 200, 160, True, "w"),
        ("period", tr("mandatory.period", "Период"), 90, 80, False, "w"),
        ("date", tr("mandatory.date", "Дата"), 100, 100, False, "w"),
        ("autopay", tr("mandatory.autopay", "Автоплатеж"), 120, 100, False, "center"),
    ):
        mand_tree.heading(col, text=text)
        mand_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(mand_tree, columns=("category", "description"), max_width=360)
    mand_tree.grid(row=0, column=0, sticky="nsew", padx=PAD_SM, pady=PAD_SM)

    mand_yscroll = ttk.Scrollbar(parent, orient="vertical", command=mand_tree.yview)
    mand_yscroll.grid(row=0, column=1, sticky="ns", pady=PAD_SM)
    mand_tree.configure(yscrollcommand=mand_yscroll.set)

    mand_xscroll = ttk.Scrollbar(parent, orient="horizontal", command=mand_tree.xview)
    mand_xscroll.grid(row=1, column=0, sticky="ew", padx=PAD_SM, pady=(0, PAD_SM))
    mand_tree.configure(xscrollcommand=mand_xscroll.set)

    return mand_tree, mand_yscroll, mand_xscroll


def bind_mandatory_horizontal_scroll(
    mand_tree: ttk.Treeview,
    mand_xscroll: ttk.Scrollbar | None,
) -> None:
    def _mandatory_scroll_units(delta: int, *, multiplier: int = 12) -> int:
        if delta == 0:
            return 0
        base_units = max(1, abs(int(delta)) // 120)
        return base_units * multiplier

    def _scroll_mandatory_horizontally(direction: int, units: int) -> str:
        mand_tree.xview_scroll(direction * units, "units")
        return "break"

    def _on_mandatory_shift_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _mandatory_scroll_units(delta)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_mandatory_horizontally(direction, units)

    def _on_mandatory_shift_button4(_event: tk.Event) -> str:
        return _scroll_mandatory_horizontally(-1, 3)

    def _on_mandatory_shift_button5(_event: tk.Event) -> str:
        return _scroll_mandatory_horizontally(1, 3)

    for widget in (mand_tree, mand_xscroll):
        if widget is not None:
            widget.bind("<Shift-MouseWheel>", _on_mandatory_shift_mousewheel, add="+")
            widget.bind("<Shift-Button-4>", _on_mandatory_shift_button4, add="+")
            widget.bind("<Shift-Button-5>", _on_mandatory_shift_button5, add="+")


def populate_mandatory_tree(
    mand_tree: ttk.Treeview,
    *,
    context: Any,
    base_currency_code: str,
) -> None:
    mand_tree.heading("kzt", text=context.controller.get_display_currency_code())
    for iid in mand_tree.get_children():
        mand_tree.delete(iid)
    expenses = context.controller.load_mandatory_expenses()
    for idx, expense in enumerate(expenses):
        values = (
            str(idx),
            f"{float(expense.amount_original or 0.0):,.2f}",
            str(expense.currency or base_currency_code).upper(),
            context.controller.format_display_amount(float(expense.amount_base or 0.0)),
            str(expense.category or ""),
            str(expense.description or ""),
            str(expense.period or ""),
            mandatory_date_text(expense),
            "✓" if bool(expense.auto_pay) else "",
        )
        mand_tree.insert("", "end", iid=str(idx), values=values)
