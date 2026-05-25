from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.tooltip import show_popup_tooltip
from gui.ui_helpers import enable_treeview_column_autosize
from gui.ui_theme import PAD_SM


def build_journal_tables(parent: ttk.Frame) -> tuple[ttk.Treeview, ttk.Treeview]:
    tables_frame = ttk.Frame(parent)
    tables_frame.grid(row=0, column=0, sticky="nsew", padx=PAD_SM, pady=PAD_SM)
    tables_frame.grid_rowconfigure(0, weight=1)
    tables_frame.grid_columnconfigure(0, weight=4)
    tables_frame.grid_columnconfigure(1, weight=1)

    records_tree = ttk.Treeview(
        tables_frame,
        show="headings",
        selectmode="browse",
        columns=("index", "date", "type", "category", "amount", "currency", "kzt", "wallets"),
    )
    for col, text, width, minwidth, stretch, anchor in (
        ("index", "#", 50, 50, False, "e"),
        ("date", tr("common.date_short", "Дата"), 100, 100, False, "w"),
        ("type", tr("common.type_short", "Тип"), 110, 110, False, "w"),
        ("category", tr("common.category_short", "Категория"), 180, 180, True, "w"),
        ("amount", tr("common.amount_short", "Сумма"), 90, 90, False, "e"),
        ("currency", tr("operations.currency_short", "Вал."), 60, 60, False, "center"),
        ("kzt", "KZT", 100, 90, False, "e"),
        ("wallets", tr("operations.wallets", "Кошельки"), 120, 110, False, "center"),
    ):
        records_tree.heading(col, text=text)
        records_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(records_tree, columns=("category",), max_width=360)
    records_tree.grid(row=0, column=0, sticky="nsew")

    tags_tree = ttk.Treeview(
        tables_frame,
        show="headings",
        selectmode="browse",
        columns=("tags",),
    )
    tags_tree.heading("tags", text=tr("common.tags_short", "Теги"))
    tags_tree.column("tags", width=180, minwidth=140, stretch=True, anchor="w")
    enable_treeview_column_autosize(tags_tree, columns=("tags",), max_width=420)
    tags_tree.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, 0))
    return records_tree, tags_tree


def bind_tags_tooltip(tags_tree: ttk.Treeview) -> None:
    tags_tooltip_window: tk.Toplevel | None = None
    tags_tooltip_text = {"value": ""}

    def _hide_tags_tooltip(_event: object | None = None) -> None:
        nonlocal tags_tooltip_window
        if tags_tooltip_window is not None:
            tags_tooltip_window.destroy()
            tags_tooltip_window = None
        tags_tooltip_text["value"] = ""

    def _show_tags_tooltip(event: tk.Event) -> None:
        nonlocal tags_tooltip_window
        row_id = tags_tree.identify_row(event.y)
        if not row_id:
            _hide_tags_tooltip()
            return
        values = tags_tree.item(row_id, "values")
        text = str(values[0] if values else "").strip()
        if not text:
            _hide_tags_tooltip()
            return
        if text == tags_tooltip_text["value"] and tags_tooltip_window is not None:
            return
        _hide_tags_tooltip()
        tags_tooltip_text["value"] = text
        tags_tooltip_window = show_popup_tooltip(
            owner=tags_tree,
            text=text,
            preferred_x=event.x_root + 12,
            preferred_y_bottom=event.y_root + 12,
            widget_top_y=event.y_root,
        )

    tags_tree.bind("<Motion>", _show_tags_tooltip, add="+")
    tags_tree.bind("<Leave>", _hide_tags_tooltip, add="+")


def wire_tree_scrollbars(
    *,
    list_frame: ttk.Frame,
    records_tree: ttk.Treeview,
    tags_tree: ttk.Treeview,
) -> None:
    y_scroll = ttk.Scrollbar(list_frame, orient="vertical")
    y_scroll.grid(row=0, column=1, sticky="ns", pady=PAD_SM)

    def _sync_yview(*args: object) -> None:
        records_tree.yview(*args)
        tags_tree.yview(*args)

    def _on_main_yview(first: float, last: float) -> None:
        y_scroll.set(first, last)
        tags_tree.yview_moveto(first)

    def _on_tags_yview(first: float, last: float) -> None:
        y_scroll.set(first, last)
        records_tree.yview_moveto(first)

    y_scroll.configure(command=_sync_yview)
    records_tree.configure(yscrollcommand=_on_main_yview)
    tags_tree.configure(yscrollcommand=_on_tags_yview)

    x_scroll = ttk.Scrollbar(list_frame, orient="horizontal", command=records_tree.xview)
    x_scroll.grid(row=1, column=0, sticky="ew", padx=PAD_SM, pady=(6, PAD_SM))
    records_tree.configure(xscrollcommand=x_scroll.set)


def wire_tree_selection_sync(records_tree: ttk.Treeview, tags_tree: ttk.Treeview) -> None:
    syncing_selection = {"value": False}

    def _sync_selection(source: ttk.Treeview, target: ttk.Treeview) -> None:
        if syncing_selection["value"]:
            return
        syncing_selection["value"] = True
        try:
            selection = source.selection()
            if not selection:
                target.selection_remove(target.selection())
                return
            iid = selection[0]
            if target.exists(iid) and target.selection() != (iid,):
                target.selection_set(iid)
                target.focus(iid)
                target.see(iid)
        finally:
            syncing_selection["value"] = False

    records_tree.bind("<<TreeviewSelect>>", lambda _event: _sync_selection(records_tree, tags_tree))
    tags_tree.bind("<<TreeviewSelect>>", lambda _event: _sync_selection(tags_tree, records_tree))


def build_journal_actions(
    *,
    parent: ttk.Frame,
    format_options: list[str],
    import_mode_label_var: tk.StringVar,
    import_mode_key_var: tk.StringVar,
    import_format_var: tk.StringVar,
    enable_combobox_support: Callable[..., Any],
    on_delete_selected: Callable[[], None],
    on_edit_selected: Callable[[], None],
    on_refresh_list: Callable[[], None],
    on_delete_all: Callable[[], None],
    on_import: Callable[[], None],
    on_export: Callable[[], None],
) -> None:
    import_mode_keys = [
        "operations.mode.replace",
        "operations.mode.current_rate",
        "operations.mode.legacy",
    ]
    import_mode_labels = [
        tr("operations.mode.replace", "Полная замена"),
        tr("operations.mode.current_rate", "По текущему курсу"),
        tr("operations.mode.legacy", "Наследуемый импорт"),
    ]

    actions_frame = ttk.Frame(parent)
    actions_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=6)
    actions_frame.grid_columnconfigure(0, weight=1)
    actions_frame.grid_columnconfigure(1, weight=1)

    primary_actions = ttk.Frame(actions_frame)
    primary_actions.grid(row=0, column=0, sticky="ew", pady=0, padx=(0, 6))
    import_actions = ttk.Frame(actions_frame)
    import_actions.grid(row=0, column=1, sticky="ew", pady=0, padx=(6, 0))
    for idx in range(4):
        primary_actions.grid_columnconfigure(idx, weight=1)
    for idx in range(6):
        import_actions.grid_columnconfigure(idx, weight=1)

    ttk.Button(
        primary_actions, text=tr("common.delete", "Удалить"), command=on_delete_selected
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    ttk.Button(
        primary_actions, text=tr("common.edit", "Редактировать"), command=on_edit_selected
    ).grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Button(
        primary_actions, text=tr("common.refresh", "Обновить"), command=on_refresh_list
    ).grid(row=0, column=2, sticky="ew", padx=6)
    ttk.Button(
        primary_actions, text=tr("operations.delete_all", "Удалить все"), command=on_delete_all
    ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

    ttk.Label(import_actions, text=tr("common.format", "Формат:")).grid(row=0, column=0, sticky="w")
    import_format_combo = ttk.Combobox(
        import_actions,
        textvariable=import_format_var,
        values=format_options,
        state="readonly",
    )
    import_format_combo.grid(row=0, column=1, sticky="ew", padx=(6, 8))
    enable_combobox_support(import_format_combo, bind_down=False)
    ttk.Label(import_actions, text=tr("common.mode", "Режим:")).grid(row=0, column=2, sticky="w")
    import_mode_combo = ttk.Combobox(
        import_actions,
        textvariable=import_mode_label_var,
        values=import_mode_labels,
        state="readonly",
    )
    import_mode_combo.grid(row=0, column=3, sticky="ew", padx=(6, 8))
    enable_combobox_support(import_mode_combo, bind_down=False)

    def _sync_import_mode_key(_event: object | None = None) -> None:
        idx = import_mode_combo.current()
        if idx < 0:
            idx = 0
        import_mode_key_var.set(import_mode_keys[idx])

    import_mode_combo.bind("<<ComboboxSelected>>", _sync_import_mode_key)
    _sync_import_mode_key()

    ttk.Button(import_actions, text=tr("operations.import", "Импорт"), command=on_import).grid(
        row=0, column=4, sticky="ew", padx=(0, 6)
    )
    ttk.Button(import_actions, text=tr("operations.export", "Экспорт"), command=on_export).grid(
        row=0, column=5, sticky="ew"
    )
