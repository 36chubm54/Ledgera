"""Journal and action area for the operations tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import cast

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL, create_card_section, enable_treeview_zebra

from ..support.journal_support import (
    bind_tags_tooltip,
    build_journal_actions,
    build_journal_tables,
    wire_tree_scrollbars,
    wire_tree_selection_sync,
)


@dataclass(slots=True)
class JournalSection:
    list_frame: ttk.Frame
    records_tree: ttk.Treeview
    tags_tree: ttk.Treeview
    import_mode_label_var: tk.StringVar
    import_mode_key_var: tk.StringVar
    import_format_var: tk.StringVar
    select_first: Callable[[], None]
    select_last: Callable[[], None]


def build_journal_section(
    parent: tk.Misc,
    *,
    format_options: list[str],
    on_delete_selected: Callable[[], None],
    on_edit_selected: Callable[[], None],
    on_refresh_list: Callable[[], None],
    on_delete_all: Callable[[], None],
    on_import: Callable[[], None],
    on_export: Callable[[], None],
) -> JournalSection:
    list_card = create_card_section(parent, tr("operations.journal", "Журнал операций"))
    list_card.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=PAD_LG)
    list_frame = cast(ttk.Frame, list_card.winfo_children()[-1])
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    records_tree, tags_tree = build_journal_tables(list_frame)
    enable_treeview_zebra(records_tree)
    enable_treeview_zebra(tags_tree)
    bind_tags_tooltip(tags_tree)
    wire_tree_scrollbars(
        list_frame=list_frame,
        records_tree=records_tree,
        tags_tree=tags_tree,
    )
    wire_tree_selection_sync(records_tree, tags_tree)

    def select_first_record() -> None:
        children = records_tree.get_children()
        if not children:
            return
        first = children[0]
        records_tree.selection_set(first)
        records_tree.focus(first)
        records_tree.see(first)

    def select_last_record() -> None:
        children = records_tree.get_children()
        if not children:
            return
        last = children[-1]
        records_tree.selection_set(last)
        records_tree.focus(last)
        records_tree.see(last)

    import_mode_label_var = tk.StringVar(value=tr("operations.mode.replace", "Полная замена"))
    import_mode_key_var = tk.StringVar(value="operations.mode.replace")
    import_format_var = tk.StringVar(value=format_options[0] if format_options else "")
    build_journal_actions(
        parent=list_frame,
        format_options=format_options,
        import_mode_label_var=import_mode_label_var,
        import_mode_key_var=import_mode_key_var,
        import_format_var=import_format_var,
        enable_combobox_support=enable_wayland_combobox_support,
        on_delete_selected=on_delete_selected,
        on_edit_selected=on_edit_selected,
        on_refresh_list=on_refresh_list,
        on_delete_all=on_delete_all,
        on_import=on_import,
        on_export=on_export,
    )

    return JournalSection(
        list_frame=list_frame,
        records_tree=records_tree,
        tags_tree=tags_tree,
        import_mode_label_var=import_mode_label_var,
        import_mode_key_var=import_mode_key_var,
        import_format_var=import_format_var,
        select_first=select_first_record,
        select_last=select_last_record,
    )
