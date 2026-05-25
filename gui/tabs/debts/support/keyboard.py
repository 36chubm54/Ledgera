from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

_CONTROL_MASK = 0x0004
_SHIFT_MASK = 0x0001
_LOCAL_CTRL_ALIASES: dict[str, tuple[str, ...]] = {
    "p": ("p", "z", "cyrillic_ze", "з"),
    "w": ("w", "ts", "cyrillic_tse", "ц"),
}
_LOCAL_CTRL_KEYCODES: dict[str, int] = {
    "p": 80,
    "w": 87,
}


def bind_control_shortcuts(widget: tk.Misc, handlers: dict[str, Callable[[], None]]) -> None:
    def _dispatch(event: tk.Event) -> str | None:
        state = int(getattr(event, "state", 0))
        if not state & _CONTROL_MASK or state & _SHIFT_MASK:
            return None
        keysym = str(getattr(event, "keysym", "") or "").strip().lower()
        char = str(getattr(event, "char", "") or "").strip().lower()
        keycode = getattr(event, "keycode", None)
        for letter, action in handlers.items():
            aliases = _LOCAL_CTRL_ALIASES.get(letter, (letter,))
            if keysym in aliases or char in aliases or keycode == _LOCAL_CTRL_KEYCODES.get(letter):
                action()
                return "break"
        return None

    widget.bind("<Control-KeyPress>", _dispatch, add="+")


def bind_focus_navigation(widgets: list[tk.Misc]) -> None:
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
        else:
            widget.bind("<Return>", lambda _event: "break", add="+")
            widget.bind("<KP_Enter>", lambda _event: "break", add="+")


def bind_submit_navigation(widgets: list[tk.Misc], action: Callable[[], None]) -> None:
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
        else:
            widget.bind("<Return>", lambda _event: (action(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (action(), "break")[1], add="+")
