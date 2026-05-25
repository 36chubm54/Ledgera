from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Literal


def create_card_section(
    parent: tk.Misc,
    title: str,
    *,
    pad_md: int,
    body_padding: tuple[int, int, int, int] = (12, 12, 12, 12),
) -> ttk.Frame:
    card = ttk.Frame(parent, style="Card.TFrame", padding=body_padding)
    card.grid_columnconfigure(0, weight=1)
    ttk.Label(card, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="ew")
    ttk.Separator(card, orient=tk.HORIZONTAL, style="SectionDivider.TSeparator").grid(
        row=1, column=0, sticky="ew", pady=(0, pad_md)
    )
    body = ttk.Frame(card, style="CardBody.TFrame")
    body.grid(row=2, column=0, sticky="nsew")
    card.grid_rowconfigure(2, weight=1)
    body.grid_columnconfigure(0, weight=1)
    return card


def _sync_treeview_row_tags(tree: ttk.Treeview) -> None:
    selection = set(tree.selection())
    for index, iid in enumerate(tree.get_children("")):
        current_tags = tuple(str(tag) for tag in tree.item(iid, "tags"))
        base_tags = tuple(tag for tag in current_tags if tag not in {"alt", "alt_selected"})
        zebra_tag = "alt_selected" if iid in selection and index % 2 else "alt" if index % 2 else ""
        tree.item(iid, tags=base_tags + (zebra_tag,)) if zebra_tag else tree.item(
            iid, tags=base_tags
        )


def refresh_treeview_zebra(tree: ttk.Treeview, *, get_palette: Any) -> None:
    palette = get_palette()
    tree.tag_configure("alt", background=palette.row_alt)
    tree.tag_configure("alt_selected", background=palette.surface_alt)
    _sync_treeview_row_tags(tree)


def _schedule_treeview_zebra_refresh(tree: ttk.Treeview) -> None:
    if bool(getattr(tree, "_zebra_refresh_pending", False)):
        return
    setattr(tree, "_zebra_refresh_pending", True)  # noqa: B010

    def _run() -> None:
        setattr(tree, "_zebra_refresh_pending", False)  # noqa: B010
        setattr(tree, "_zebra_refresh_after_id", None)  # noqa: B010
        if bool(tree.winfo_exists()):
            _sync_treeview_row_tags(tree)

    setattr(tree, "_zebra_refresh_after_id", tree.after_idle(_run))  # noqa: B010


def enable_treeview_zebra(tree: ttk.Treeview, *, get_palette: Any) -> ttk.Treeview:
    if bool(getattr(tree, "_zebra_enabled", False)):
        refresh_treeview_zebra(tree, get_palette=get_palette)
        return tree

    palette = get_palette()
    tree.tag_configure("alt", background=palette.row_alt)
    tree.tag_configure("alt_selected", background=palette.surface_alt)
    original_insert = tree.insert
    original_delete = tree.delete
    original_move = tree.move

    def _insert(
        parent: str, index: int | Literal["end"], iid: str | int | None = None, **kw: Any
    ) -> str:
        item_id = original_insert(parent, index, iid=iid, **kw)
        _schedule_treeview_zebra_refresh(tree)
        return item_id

    def _delete(*items: str) -> None:
        original_delete(*items)
        _schedule_treeview_zebra_refresh(tree)

    def _move(item: str, parent: str, index: int | Literal["end"]) -> None:
        original_move(item, parent, index)
        _schedule_treeview_zebra_refresh(tree)

    def _cancel_pending_refresh(_event: tk.Event | None = None) -> None:
        setattr(tree, "_zebra_refresh_pending", False)  # noqa: B010
        after_id = getattr(tree, "_zebra_refresh_after_id", None)
        setattr(tree, "_zebra_refresh_after_id", None)  # noqa: B010
        if after_id is None:
            return
        try:
            tree.after_cancel(str(after_id))
        except tk.TclError:
            return

    tree.insert = _insert  # type: ignore[assignment]
    tree.delete = _delete  # type: ignore[assignment]
    tree.move = _move  # type: ignore[assignment]
    tree.bind("<<TreeviewSelect>>", lambda _event: _schedule_treeview_zebra_refresh(tree), add="+")
    tree.bind("<Destroy>", _cancel_pending_refresh, add="+")
    setattr(tree, "_zebra_enabled", True)  # noqa: B010
    _schedule_treeview_zebra_refresh(tree)
    return tree
