from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from tkinter import ttk
from typing import Any

from gui.combobox_compat import should_style_native_linux_popdown


def apply_widget_theme_overrides(
    root: tk.Misc,
    palette: Any,
    *,
    known_palettes: Iterable[Any],
    font_family: str,
    refresh_treeview_zebra: Any,
) -> None:
    _apply_canvas_theme(root, palette, known_palettes=known_palettes)
    _apply_treeview_theme(
        root,
        palette,
        font_family=font_family,
        refresh_treeview_zebra=refresh_treeview_zebra,
    )
    _apply_combobox_popdown_theme(root, palette)


def _apply_combobox_popdown_theme(root: tk.Misc, palette: Any) -> None:
    try:
        tk_windowingsystem = str(root.tk.call("tk", "windowingsystem")).strip().lower()
    except tk.TclError:
        tk_windowingsystem = ""
    if not should_style_native_linux_popdown(tk_windowingsystem=tk_windowingsystem):
        return
    for widget in _walk_widgets(root):
        if isinstance(widget, ttk.Combobox):
            _configure_combobox_popdown(widget, palette)


def _apply_treeview_theme(
    root: tk.Misc,
    palette: Any,
    *,
    font_family: str,
    refresh_treeview_zebra: Any,
) -> None:
    for widget in _walk_widgets(root):
        if isinstance(widget, ttk.Treeview):
            _configure_treeview_theme(
                widget,
                palette,
                font_family=font_family,
                refresh_treeview_zebra=refresh_treeview_zebra,
            )


def _apply_canvas_theme(
    root: tk.Misc,
    palette: Any,
    *,
    known_palettes: Iterable[Any],
) -> None:
    for widget in _walk_widgets(root):
        if isinstance(widget, tk.Canvas):
            _configure_canvas_theme(widget, palette, known_palettes=known_palettes)


def _walk_widgets(root: tk.Misc) -> list[tk.Misc]:
    widgets: list[tk.Misc] = []
    for child in root.winfo_children():
        widgets.append(child)
        widgets.extend(_walk_widgets(child))
    return widgets


def _configure_combobox_popdown(widget: ttk.Combobox, palette: Any) -> None:
    try:
        popdown = str(widget.tk.eval(f"ttk::combobox::PopdownWindow {widget}"))
        listbox = f"{popdown}.f.l"
        widget.tk.call(
            listbox,
            "configure",
            "-background",
            palette.surface_elevated,
            "-foreground",
            palette.text_primary,
            "-selectbackground",
            palette.accent_blue,
            "-selectforeground",
            palette.surface_elevated,
            "-highlightthickness",
            0,
            "-borderwidth",
            0,
        )
    except tk.TclError:
        return


def _remap_theme_color(
    color: str,
    palette: Any,
    *,
    known_palettes: Iterable[Any],
) -> str:
    value = str(color or "").strip().lower()
    if not value:
        return color
    for source_palette in known_palettes:
        if value == source_palette.background.lower():
            return palette.background
        if value == source_palette.surface.lower():
            return palette.surface
        if value == source_palette.surface_elevated.lower():
            return palette.surface_elevated
        if value == source_palette.surface_alt.lower():
            return palette.surface_alt
        if value == source_palette.surface_form.lower():
            return palette.surface_form
        if value == source_palette.border_soft.lower():
            return palette.border_soft
        if value == source_palette.border_section.lower():
            return palette.border_section
        if value == source_palette.row_alt.lower():
            return palette.row_alt
        if value == source_palette.inline_accent_bg.lower():
            return palette.inline_accent_bg
        if value == source_palette.success_tint.lower():
            return palette.success_tint
        if value == source_palette.warning_tint.lower():
            return palette.warning_tint
        if value == source_palette.danger_tint.lower():
            return palette.danger_tint
    return color


def _configure_canvas_theme(
    canvas: tk.Canvas,
    palette: Any,
    *,
    known_palettes: Iterable[Any],
) -> None:
    try:
        current_bg = str(canvas.cget("bg"))
        current_highlight = str(canvas.cget("highlightbackground"))
        current_border = str(canvas.cget("highlightcolor"))
        new_bg = _remap_theme_color(current_bg, palette, known_palettes=known_palettes)
        new_highlight = _remap_theme_color(
            current_highlight, palette, known_palettes=known_palettes
        )
        new_border = _remap_theme_color(current_border, palette, known_palettes=known_palettes)
        canvas.configure(
            bg=new_bg,
            highlightbackground=new_highlight,
            highlightcolor=new_border,
        )
    except tk.TclError:
        return


def _configure_treeview_theme(
    tree: ttk.Treeview,
    palette: Any,
    *,
    font_family: str,
    refresh_treeview_zebra: Any,
) -> None:
    try:
        tree.tag_configure("alt", background=palette.row_alt)
        tree.tag_configure("alt_selected", background=palette.surface_alt)
        tree.tag_configure("positive", foreground=palette.chart_income)
        tree.tag_configure("negative", foreground=palette.chart_expense)
        tree.tag_configure("overspent", foreground=palette.danger)
        tree.tag_configure("overpace", foreground=palette.warning)
        tree.tag_configure("on_track", foreground=palette.success)
        tree.tag_configure("future", foreground=palette.text_muted)
        tree.tag_configure("expired", foreground=palette.text_muted)
        tree.tag_configure("writeoff", foreground=palette.text_muted)
        tree.tag_configure(
            "group_header",
            foreground=palette.accent_blue,
            background=palette.surface_elevated,
            font=(font_family, 9, "bold"),
        )
        tree.tag_configure(
            "item",
            foreground=palette.text_primary,
            background=palette.surface_elevated,
        )
        tree.tag_configure(
            "subitem",
            foreground=palette.accent_blue,
            background=palette.surface_elevated,
        )
        tree.tag_configure(
            "neg_row", background=palette.danger_tint, foreground=palette.text_primary
        )
        tree.tag_configure(
            "pos_row",
            background=palette.success_tint,
            foreground=palette.text_primary,
        )
        tree.tag_configure(
            "warn_row",
            background=palette.warning_tint,
            foreground=palette.text_primary,
        )
        tree.tag_configure("odd_row", background=palette.row_alt, foreground=palette.text_primary)
        tree.tag_configure(
            "even_row",
            background=palette.surface_elevated,
            foreground=palette.text_primary,
        )
        refresh_treeview_zebra(tree)
    except tk.TclError:
        return
