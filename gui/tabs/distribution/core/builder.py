"""Distribution tab builder."""

# ruff: noqa: E501

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import ask_numeric_text, ask_text
from gui.ui_theme import get_palette

from ..support.actions import (
    add_item,
    add_subitem,
    delete_selected,
    edit_percent,
    rename_selected,
    toggle_fixed_row,
)
from ..support.prompts import DistributionActionUi
from ..support.results_section import (
    build_results_section,
    fit_results_columns,
    refresh_results,
    update_fix_button_state,
)
from ..support.structure_section import (
    bind_fixed_width_columns,
    build_structure_section,
    fit_structure_columns,
    refresh_structure,
)
from .contracts import DistributionTabBindings, DistributionTabContext


def build_distribution_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: DistributionTabContext,
) -> DistributionTabBindings:
    palette = get_palette()
    action_ui = DistributionActionUi(
        messagebox_module=messagebox,
        ask_text_fn=ask_text,
        ask_numeric_text_fn=ask_numeric_text,
    )

    def format_display_amount(amount: float, precision: int = 2) -> str:
        return context.controller.format_display_amount(amount, precision=precision)

    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(parent)
    content.grid(row=0, column=0, sticky="nsew", padx=10, pady=8)
    content.grid_columnconfigure(0, minsize=400, weight=0)
    content.grid_columnconfigure(1, weight=1)
    content.grid_rowconfigure(0, weight=1)

    left_frame = ttk.Frame(content, width=400, padding=(0, 0, 8, 0))
    left_frame.grid(row=0, column=0, sticky="nsew")
    left_frame.grid_columnconfigure(0, weight=1)
    left_frame.grid_rowconfigure(1, weight=1)

    right_frame = ttk.Frame(content)
    right_frame.grid(row=0, column=1, sticky="nsew")
    right_frame.grid_columnconfigure(0, weight=1)
    right_frame.grid_rowconfigure(1, weight=1)

    structure = build_structure_section(left_frame, palette=palette)
    results = build_results_section(right_frame, palette=palette)

    def _refresh_structure() -> None:
        refresh_structure(context, structure, palette=palette)

    def _refresh_results() -> None:
        refresh_results(
            context,
            results,
            palette=palette,
            format_display_amount=lambda value, precision=2: format_display_amount(
                value, precision
            ),
        )

    def _refresh_all() -> None:
        _refresh_structure()
        _refresh_results()

    ttk.Button(
        structure.buttons,
        text=tr("distribution.button.add_item", "+ Элемент"),
        command=lambda: add_item(
            context=context, parent=parent, refresh_all=_refresh_all, ui=action_ui
        ),
    ).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(
        structure.buttons,
        text=tr("distribution.button.add_subitem", "+ Подэлемент"),
        command=lambda: add_subitem(
            context=context,
            parent=parent,
            structure_tree=structure.structure_tree,
            refresh_all=_refresh_all,
            ui=action_ui,
        ),
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        structure.buttons,
        text=tr("distribution.button.edit_percent", "Изменить %"),
        command=lambda: edit_percent(
            context=context,
            parent=parent,
            structure_tree=structure.structure_tree,
            refresh_all=_refresh_all,
            ui=action_ui,
        ),
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        structure.buttons,
        text=tr("distribution.button.rename", "Переименовать"),
        command=lambda: rename_selected(
            context=context,
            parent=parent,
            structure_tree=structure.structure_tree,
            refresh_all=_refresh_all,
            ui=action_ui,
        ),
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        structure.buttons,
        text=tr("distribution.button.delete", "Удалить"),
        command=lambda: delete_selected(
            context=context,
            parent=parent,
            structure_tree=structure.structure_tree,
            refresh_all=_refresh_all,
            ui=action_ui,
        ),
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        results.toolbar,
        text=tr("distribution.button.refresh", "Обновить"),
        command=_refresh_all,
    ).pack(side=tk.LEFT, padx=(4, 0))
    results.fix_button.configure(
        command=lambda: toggle_fixed_row(
            context=context,
            parent=parent,
            results_tree=results.results_tree,
            refresh_results=_refresh_results,
            update_fix_button_state=lambda: update_fix_button_state(context, results),
            ui=action_ui,
        ),
        state=tk.DISABLED,
    )
    results.results_tree.bind(
        "<<TreeviewSelect>>", lambda _event: update_fix_button_state(context, results), add="+"
    )

    bind_fixed_width_columns(structure.structure_tree)
    structure.structure_tree.bind(
        "<Configure>", lambda event: fit_structure_columns(structure.structure_tree, event), add="+"
    )
    results.results_tree.bind(
        "<Configure>", lambda event: fit_results_columns(results.results_tree, event), add="+"
    )

    _refresh_all()
    return DistributionTabBindings(
        structure_tree=structure.structure_tree,
        validation_label=structure.validation_label,
        period_from_var=results.period_from_var,
        period_to_var=results.period_to_var,
        results_tree=results.results_tree,
        status_label=results.status_label,
        refresh=_refresh_all,
    )
