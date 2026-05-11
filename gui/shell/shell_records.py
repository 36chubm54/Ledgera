from __future__ import annotations

import tkinter as tk
from tkinter import TclError, ttk
from typing import Any

from gui.record_colors import KIND_TO_FOREGROUND, foreground_for_kind
from gui.shell.shell_support import build_record_tree_values
from gui.tooltip import show_popup_tooltip
from utils.tag_utils import color_for_tag


def refresh_record_views(
    *,
    controller: Any,
    records_tree: ttk.Treeview,
    record_tags_tree: ttk.Treeview | None,
    records: list[Any] | None,
    display_currency_code: str,
    build_record_tree_values: Any,
    kind_to_foreground: dict[str, str],
    foreground_for_kind: Any,
    color_for_tag: Any,
) -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    records_tree.heading("kzt", text=display_currency_code)
    _clear_tree(records_tree)
    if record_tags_tree is not None:
        _clear_tree(record_tags_tree)
    for kind, color in kind_to_foreground.items():
        try:
            records_tree.tag_configure(kind, foreground=color)
        except TclError:
            pass

    list_items = (
        controller.build_record_list_items(records)
        if records is not None
        else controller.build_record_list_items()
    )
    tag_color_map = {
        str(getattr(tag, "name", "") or ""): str(getattr(tag, "color", "") or "")
        for tag in controller.list_tags()
    }

    repo_index_map: dict[str, int] = {}
    domain_id_map: dict[str, int] = {}
    description_map: dict[str, str] = {}
    for item in list_items:
        record_id = item.record_id
        repo_index_map[record_id] = item.repository_index
        if item.domain_record_id is not None:
            domain_id_map[record_id] = item.domain_record_id
        description_map[record_id] = str(getattr(item, "description_text", "") or "").strip()

        kind = str(getattr(item, "kind", "") or "").strip().lower()
        row_tags = (kind,) if foreground_for_kind(kind) else ()
        row_values = build_record_tree_values(item, kind)
        try:
            records_tree.insert("", "end", iid=record_id, values=row_values, tags=row_tags)
        except TclError:
            records_tree.insert("", "end", values=row_values, tags=row_tags)

        if record_tags_tree is None:
            continue
        tag_name = str(getattr(item, "tags_text", "") or "")
        tag_tree_tags: tuple[str, ...] = ()
        item_tags = tuple(getattr(item, "tags", ()) or ())
        if item_tags:
            first_tag = str(item_tags[0])
            tag_color = tag_color_map.get(first_tag) or color_for_tag(first_tag)
        else:
            tag_color = ""
        if tag_color:
            tag_style = f"tag_color_{tag_color.replace('#', '').lower()}"
            try:
                record_tags_tree.tag_configure(tag_style, foreground=tag_color)
            except TclError:
                pass
            tag_tree_tags = (tag_style,)
        try:
            record_tags_tree.insert(
                "",
                "end",
                iid=record_id,
                values=(tag_name,),
                tags=tag_tree_tags,
            )
        except TclError:
            record_tags_tree.insert("", "end", values=(tag_name,), tags=tag_tree_tags)

    return repo_index_map, domain_id_map, description_map


def refresh_owner_record_views(owner: Any, records: list[Any] | None = None) -> bool:
    if owner.records_tree is None:
        return False
    (
        owner._record_id_to_repo_index,
        owner._record_id_to_domain_id,
        owner._record_id_to_description,
    ) = refresh_record_views(
        controller=owner.controller,
        records_tree=owner.records_tree,
        record_tags_tree=owner.record_tags_tree,
        records=records,
        display_currency_code=owner.controller.get_display_currency_code(),
        build_record_tree_values=lambda item, kind: build_record_tree_values(
            item,
            kind,
            to_display_amount=lambda amount: owner.controller.to_display_amount(amount),
        ),
        kind_to_foreground=KIND_TO_FOREGROUND,
        foreground_for_kind=foreground_for_kind,
        color_for_tag=color_for_tag,
    )
    return True


def destroy_records_tooltip_window(tooltip_window: tk.Toplevel | None) -> None:
    if tooltip_window is None:
        return
    try:
        tooltip_window.destroy()
    except TclError:
        pass


def clear_records_tooltip_state(owner: Any) -> None:
    owner._records_tooltip_window = None
    owner._records_tooltip_text = ""


def hide_owner_records_tooltip(owner: Any, _event: object | None = None) -> None:
    destroy_records_tooltip_window(owner._records_tooltip_window)
    clear_records_tooltip_state(owner)


def tooltip_row_id(records_tree: ttk.Treeview | None, event: tk.Event) -> str:
    if records_tree is None:
        return ""
    return str(records_tree.identify_row(event.y) or "")


def tooltip_description_for_row(row_id: str, description_map: dict[str, str]) -> str:
    return description_map.get(str(row_id), "").strip()


def tooltip_state_matches(
    *,
    description: str,
    tooltip_text: str,
    tooltip_window: tk.Toplevel | None,
) -> bool:
    return bool(description) and description == tooltip_text and tooltip_window is not None


def show_records_tooltip_window(
    *,
    records_tree: ttk.Treeview | None,
    event: tk.Event,
    description: str,
) -> tk.Toplevel | None:
    if records_tree is None:
        return None
    return show_popup_tooltip(
        owner=records_tree,
        text=description,
        preferred_x=event.x_root + 12,
        preferred_y_bottom=event.y_root + 12,
        widget_top_y=event.y_root,
        wraplength=320,
    )


def process_records_tooltip_event(
    *,
    records_tree: ttk.Treeview | None,
    event: tk.Event,
    description_map: dict[str, str],
    tooltip_text: str,
    tooltip_window: tk.Toplevel | None,
    hide_tooltip: Any,
) -> tuple[str, tk.Toplevel | None]:
    if records_tree is None:
        return tooltip_text, tooltip_window
    row_id = tooltip_row_id(records_tree, event)
    if not row_id:
        hide_tooltip()
        return "", None
    description = tooltip_description_for_row(row_id, description_map)
    if not description:
        hide_tooltip()
        return "", None
    if tooltip_state_matches(
        description=description,
        tooltip_text=tooltip_text,
        tooltip_window=tooltip_window,
    ):
        return tooltip_text, tooltip_window

    hide_tooltip()
    return description, show_records_tooltip_window(
        records_tree=records_tree,
        event=event,
        description=description,
    )


def show_owner_records_tooltip(owner: Any, event: tk.Event) -> None:
    (
        owner._records_tooltip_text,
        owner._records_tooltip_window,
    ) = process_records_tooltip_event(
        records_tree=owner.records_tree,
        event=event,
        description_map=owner._record_id_to_description,
        tooltip_text=owner._records_tooltip_text,
        tooltip_window=owner._records_tooltip_window,
        hide_tooltip=lambda: hide_owner_records_tooltip(owner),
    )


def _clear_tree(tree: ttk.Treeview) -> None:
    for iid in tree.get_children():
        tree.delete(iid)
