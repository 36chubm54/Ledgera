from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk


@dataclass(slots=True)
class InlineActionButtons:
    save_button: ttk.Button
    cancel_button: ttk.Button


def bind_focus_navigation(
    widgets: list[tk.Misc],
    *,
    submit_action: Callable[[], None] | None = None,
    cancel_action: Callable[[], None] | None = None,
) -> None:
    def _focus_relative(index: int) -> str:
        widgets[index % len(widgets)].focus_set()
        return "break"

    for index, widget in enumerate(widgets):
        widget.bind("<Up>", lambda _event, i=index - 1: _focus_relative(i), add="+")
        widget.bind("<Down>", lambda _event, i=index + 1: _focus_relative(i), add="+")
        if isinstance(widget, ttk.Button):
            widget.bind("<Left>", lambda _event, i=index - 1: _focus_relative(i), add="+")
            widget.bind("<Right>", lambda _event, i=index + 1: _focus_relative(i), add="+")
            widget.bind("<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
        elif callable(submit_action):
            widget.bind("<Return>", lambda _event: (submit_action(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (submit_action(), "break")[1], add="+")

        if callable(cancel_action):
            widget.bind("<Escape>", lambda _event: (cancel_action(), "break")[1], add="+")


def build_inline_action_buttons(
    panel: ttk.Frame,
    *,
    row_index: int,
    on_save: Callable[[], None],
    on_cancel: Callable[[], None],
) -> InlineActionButtons:
    buttons = ttk.Frame(panel, style="InlinePanel.TFrame")
    buttons.grid(row=row_index, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)
    save_button = ttk.Button(
        buttons,
        text="Сохранить",
        style="Primary.TButton",
        command=on_save,
    )
    save_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    cancel_button = ttk.Button(
        buttons,
        text="Отмена",
        command=on_cancel,
    )
    cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    return InlineActionButtons(save_button=save_button, cancel_button=cancel_button)
