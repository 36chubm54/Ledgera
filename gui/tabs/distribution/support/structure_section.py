from __future__ import annotations

import logging
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from tkinter import ttk

from domain.distribution import DistributionItem
from gui.i18n import tr

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DistributionStructureSection:
    structure_tree: ttk.Treeview
    validation_label: ttk.Label
    buttons: ttk.Frame


def build_structure_section(parent, *, palette) -> DistributionStructureSection:
    ttk.Label(
        parent,
        text=tr("distribution.structure.title", "Структура распределения"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w", padx=8, pady=(0, 6))

    structure_wrap = ttk.Frame(parent)
    structure_wrap.grid(row=1, column=0, sticky="nsew", padx=8)
    structure_wrap.grid_columnconfigure(0, weight=1)
    structure_wrap.grid_rowconfigure(0, weight=1)

    structure_tree = ttk.Treeview(
        structure_wrap,
        columns=("pct", "group"),
        show="tree headings",
        height=18,
    )
    structure_tree.heading("#0", text=tr("common.name", "Название"))
    structure_tree.heading("pct", text="%")
    structure_tree.heading("group", text=tr("common.group", "Группа"))
    structure_tree.column("#0", width=240, anchor="w", stretch=False)
    structure_tree.column("pct", width=70, anchor="center", stretch=False)
    structure_tree.column("group", width=180, minwidth=160, anchor="w", stretch=True)
    structure_tree.tag_configure(
        "group_header",
        foreground=palette.accent_blue,
        font=("Segoe UI", 9, "bold"),
    )
    structure_tree.tag_configure("item", foreground=palette.text_primary)
    structure_tree.tag_configure("subitem", foreground=palette.accent_blue)
    structure_tree.grid(row=0, column=0, sticky="nsew")

    structure_scroll = ttk.Scrollbar(
        structure_wrap,
        orient="vertical",
        command=structure_tree.yview,
    )
    structure_scroll.grid(row=0, column=1, sticky="ns")
    structure_tree.configure(yscrollcommand=structure_scroll.set)

    validation_label = ttk.Label(parent, text="", justify=tk.LEFT)
    validation_label.grid(row=2, column=0, sticky="w", padx=8, pady=(6, 2))

    buttons = ttk.Frame(parent)
    buttons.grid(row=3, column=0, sticky="w", padx=8, pady=(4, 0))

    return DistributionStructureSection(
        structure_tree=structure_tree,
        validation_label=validation_label,
        buttons=buttons,
    )


def fit_structure_columns(structure_tree: ttk.Treeview, _event: tk.Event | None = None) -> None:
    total_width = max(structure_tree.winfo_width(), 0)
    if total_width <= 1:
        return
    name_width = 240
    pct_width = 70
    slack = 6
    group_width = max(160, total_width - name_width - pct_width - slack)
    structure_tree.column("#0", width=name_width, minwidth=name_width, stretch=False)
    structure_tree.column("pct", width=pct_width, minwidth=pct_width, stretch=False)
    structure_tree.column("group", width=group_width, minwidth=160, anchor="w", stretch=False)


def bind_fixed_width_columns(tree: ttk.Treeview) -> None:
    def _block_separator_resize(event: tk.Event) -> str | None:
        tree = event.widget if isinstance(event.widget, ttk.Treeview) else None
        if tree is None:
            return None
        region = tree.identify_region(event.x, event.y)
        if region == "separator":
            return "break"
        return None

    tree.bind("<Button-1>", _block_separator_resize, add="+")


def selected_item_id(structure_tree: ttk.Treeview) -> int | None:
    selection = structure_tree.selection()
    if not selection:
        return None
    iid = selection[0]
    if iid.startswith("item_"):
        return int(iid.split("_", 1)[1])
    if iid.startswith("sub_"):
        parent_iid = structure_tree.parent(iid)
        if parent_iid.startswith("item_"):
            return int(parent_iid.split("_", 1)[1])
    return None


def refresh_validation(context, validation_label: ttk.Label, *, palette) -> None:
    errors = context.controller.validate_distribution()
    if not errors:
        validation_label.config(
            text=tr(
                "distribution.validation.ok",
                "Структура корректна: верхний уровень и подэлементы суммарно дают 100.00%",
            ),
            foreground=palette.success,
        )
        return
    validation_label.config(
        text="\n".join(f"- {error.message}" for error in errors),
        foreground=palette.danger,
    )


def refresh_structure(context, section: DistributionStructureSection, *, palette) -> None:
    section.structure_tree.delete(*section.structure_tree.get_children())
    try:
        items = context.controller.get_distribution_items()
    except (ValueError, TypeError, RuntimeError, tk.TclError) as exc:
        logger.warning("Failed to refresh distribution structure: %s", exc)
        section.validation_label.config(text=str(exc), foreground=palette.danger)
        return

    grouped: dict[str, list[DistributionItem]] = defaultdict(list)
    for item in items:
        grouped[item.group_name or tr("common.ungrouped", "Без группы")].append(item)

    for group_name in sorted(grouped, key=str.casefold):
        group_items = grouped[group_name]
        parent_iid = ""
        if len(group_items) > 1 or group_name != tr("common.ungrouped", "Без группы"):
            parent_iid = section.structure_tree.insert(
                "",
                "end",
                text=group_name,
                values=("", ""),
                tags=("group_header",),
                open=True,
            )
        for item in group_items:
            item_node = section.structure_tree.insert(
                parent_iid,
                "end",
                iid=f"item_{item.id}",
                text=item.name,
                values=(f"{item.pct:.2f}%", item.group_name or ""),
                tags=("item",),
                open=True,
            )
            for subitem in context.controller.get_distribution_subitems(item.id):
                section.structure_tree.insert(
                    item_node,
                    "end",
                    iid=f"sub_{subitem.id}",
                    text=subitem.name,
                    values=(f"{subitem.pct:.2f}%", ""),
                    tags=("subitem",),
                )

    fit_structure_columns(section.structure_tree)
    refresh_validation(context, section.validation_label, palette=palette)
