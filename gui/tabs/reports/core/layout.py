from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import cast

from gui.combobox_compat import (
    GuiDisplayRuntime,
    _tk_windowingsystem,
    detect_gui_display_runtime,
    should_use_linux_compat_popup,
)

from ..support.layout_body import build_reports_body
from ..support.layout_controls import build_reports_controls


@dataclass(slots=True)
class ReportsUiHandles:
    category_combo: ttk.Combobox
    wallet_menu: ttk.Combobox
    tag_combo: ttk.Combobox
    group_status_label: ttk.Label
    group_back_button: ttk.Button
    generate_button: ttk.Button
    export_button: ttk.Menubutton
    operations_container: ttk.Frame
    operations_tree: ttk.Treeview
    monthly_tree: ttk.Treeview
    summary_frame: tk.Misc
    summary_labels: dict[str, ttk.Label]
    summary_values: dict[str, ttk.Label]


class _LinuxExportPopupManager:
    def __init__(self, button: ttk.Menubutton, owner: object) -> None:
        self.button = button
        self.owner = owner
        self.popup: ttk.Frame | None = None
        self._focus_close_after_id: str | None = None
        self._focus_set_after_id: str | None = None

    def _cancel_focus_close(self) -> None:
        after_id = self._focus_close_after_id
        self._focus_close_after_id = None
        if after_id is None:
            return
        try:
            self.button.after_cancel(after_id)
        except tk.TclError:
            return

    def _cancel_focus_set(self) -> None:
        after_id = self._focus_set_after_id
        self._focus_set_after_id = None
        if after_id is None:
            return
        try:
            self.button.after_cancel(after_id)
        except tk.TclError:
            return

    def _focus_within_popup(self) -> bool:
        popup = self.popup
        if popup is None:
            return False
        widget = self.button.focus_displayof()
        if widget is None:
            return False
        return str(widget).startswith(str(popup))

    def _close_if_focus_lost(self, _event: object | None = None) -> None:
        self._cancel_focus_close()
        self._focus_close_after_id = self.button.after_idle(self._close_if_focus_still_lost)

    def _close_if_focus_still_lost(self) -> None:
        self._focus_close_after_id = None
        if self.popup is None:
            return
        focus_widget = self.button.focus_displayof()
        if focus_widget is self.button or self._focus_within_popup():
            return
        self.close_popup(restore_focus=False)

    def _popup_placement(self, *, height: int) -> tuple[int, int, int, int]:
        owner = cast(tk.Misc, self.button.nametowidget(str(self.button.winfo_toplevel())))
        owner.update_idletasks()
        self.button.update_idletasks()
        width = max(self.button.winfo_width(), self.button.winfo_reqwidth())
        x = self.button.winfo_rootx() - owner.winfo_rootx()
        y_below = self.button.winfo_rooty() - owner.winfo_rooty() + self.button.winfo_height()
        y_above = y_below - height - self.button.winfo_height()
        owner_height = max(owner.winfo_height(), owner.winfo_reqheight())
        y = y_below if y_below + height <= owner_height else max(0, y_above)
        owner_width = max(owner.winfo_width(), owner.winfo_reqwidth())
        x = max(0, min(x, max(0, owner_width - width)))
        return x, y, width, height

    def close_popup(self, *, restore_focus: bool = True) -> None:
        popup = self.popup
        self._cancel_focus_close()
        self._cancel_focus_set()
        self.popup = None
        if popup is None:
            return
        popup.place_forget()
        popup.destroy()
        if restore_focus and self.button.winfo_exists():
            self.button.focus_set()

    def _export(self, fmt: str) -> None:
        self.close_popup(restore_focus=False)
        export_method = getattr(self.owner, "_export", None)
        if callable(export_method):
            export_method(fmt)

    def open_popup(self) -> str:
        if str(self.button.cget("state")) == str(tk.DISABLED):
            return "break"
        if self.popup is not None:
            self.close_popup()
            return "break"

        owner = cast(tk.Misc, self.button.nametowidget(str(self.button.winfo_toplevel())))
        popup = ttk.Frame(owner, padding=1, style="Card.TFrame")
        popup.grid_columnconfigure(0, weight=1)

        entries = (
            ("CSV", "csv"),
            ("XLSX", "xlsx"),
            ("PDF", "pdf"),
        )
        first_button: ttk.Button | None = None
        for row_index, (label, fmt) in enumerate(entries):
            option_button = ttk.Button(
                popup,
                text=label,
                command=lambda selected=fmt: self._export(selected),
            )
            option_button.grid(row=row_index, column=0, sticky="ew")
            option_button.bind(
                "<Escape>",
                lambda _event: (self.close_popup(), "break")[1],
                add="+",
            )
            option_button.bind("<FocusOut>", self._close_if_focus_lost, add="+")
            if first_button is None:
                first_button = option_button

        self.popup = popup
        popup.update_idletasks()
        pos_x, pos_y, width, height = self._popup_placement(height=popup.winfo_reqheight())
        popup.place(x=pos_x, y=pos_y, width=width, height=height)
        popup.lift()
        popup.bind("<FocusOut>", self._close_if_focus_lost, add="+")
        popup.bind("<Escape>", lambda _event: (self.close_popup(), "break")[1], add="+")
        if first_button is not None:
            self._focus_set_after_id = popup.after(0, first_button.focus_set)
        return "break"

    def bind(self) -> None:
        self.button.bind("<Button-1>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Return>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<KP_Enter>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<space>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Down>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Alt-Down>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Escape>", lambda _event: (self.close_popup(), "break")[1], add="+")


def _should_use_linux_export_popup(runtime: GuiDisplayRuntime, widget: tk.Misc) -> bool:
    return should_use_linux_compat_popup(
        runtime,
        tk_windowingsystem=_tk_windowingsystem(widget),
    )


def build_reports_layout(owner) -> ReportsUiHandles:
    (
        category_combo,
        wallet_menu,
        tag_combo,
        group_status_label,
        group_back_button,
        generate_button,
        export_button,
    ) = build_reports_controls(
        owner,
        on_export_menu=lambda button: _configure_export_button(owner, button),
    )
    (
        operations_container,
        operations_tree,
        monthly_tree,
        summary_frame,
        summary_labels,
        summary_values,
    ) = build_reports_body(owner)

    return ReportsUiHandles(
        category_combo=category_combo,
        wallet_menu=wallet_menu,
        tag_combo=tag_combo,
        group_status_label=group_status_label,
        group_back_button=group_back_button,
        generate_button=generate_button,
        export_button=export_button,
        operations_container=operations_container,
        operations_tree=operations_tree,
        monthly_tree=monthly_tree,
        summary_frame=summary_frame,
        summary_labels=summary_labels,
        summary_values=summary_values,
    )


def _configure_export_button(owner, export_button: ttk.Menubutton) -> None:
    runtime = detect_gui_display_runtime()
    if _should_use_linux_export_popup(runtime, export_button):
        export_popup_manager = _LinuxExportPopupManager(export_button, owner)
        export_popup_manager.bind()
        setattr(export_button, "_linux_export_popup_manager", export_popup_manager)  # noqa: B010
        return
    export_menu = tk.Menu(export_button, tearoff=False)
    export_menu.add_command(label="CSV", command=lambda: owner._export("csv"))
    export_menu.add_command(label="XLSX", command=lambda: owner._export("xlsx"))
    export_menu.add_command(label="PDF", command=lambda: owner._export("pdf"))
    export_button["menu"] = export_menu
