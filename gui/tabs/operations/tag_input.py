"""Shared tag input helpers for the operations tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from tkinter import ttk
from typing import Any

from gui.ui_theme import FONT_FAMILY, get_palette
from utils.tag_utils import MAX_TAGS_PER_RECORD, normalize_tag_name, parse_tag_string


def list_tags_safe(controller: Any) -> list[Any]:
    list_tags = getattr(controller, "list_tags", None)
    if not callable(list_tags):
        return []
    try:
        tags = list_tags()
        if not isinstance(tags, Iterable):
            return []
        return list(tags)
    except (ValueError, RuntimeError, TypeError):
        return []


def sorted_tags_by_popularity(controller: Any) -> list[Any]:
    tags = list_tags_safe(controller)
    return sorted(
        tags,
        key=lambda tag: (
            -int(getattr(tag, "usage_count", 0)),
            str(getattr(tag, "name", "")).casefold(),
        ),
    )


def split_tag_input(raw_value: str) -> tuple[tuple[str, ...], str]:
    parts = str(raw_value or "").split(",")
    committed = parse_tag_string(",".join(parts[:-1])) if len(parts) > 1 else ()
    fragment = parts[-1].strip() if parts else ""
    return committed, fragment


def attach_tag_autocomplete(
    *,
    owner: tk.Misc,
    combobox: ttk.Combobox,
    list_tags: Callable[[], Iterable[Any]],
    on_input_changed: Callable[[], None] | None = None,
) -> None:
    palette = get_palette()
    popup_state: dict[str, Any] = {"window": None, "listbox": None, "items": []}
    selection_state: dict[str, Any] = {"committed": (), "fragment": ""}

    def _remember_input_state(raw_value: str | None = None) -> tuple[tuple[str, ...], str]:
        committed, fragment = split_tag_input(combobox.get() if raw_value is None else raw_value)
        selection_state["committed"] = committed
        selection_state["fragment"] = fragment
        return committed, fragment

    def _build_suggestions(raw_value: str) -> list[Any]:
        committed, fragment = split_tag_input(raw_value)
        committed_set = set(committed)
        normalized_fragment = normalize_tag_name(fragment)
        suggestions: list[Any] = []
        for tag in list_tags():
            tag_name = str(getattr(tag, "name", "") or "")
            if not tag_name or tag_name in committed_set:
                continue
            if normalized_fragment and not tag_name.startswith(normalized_fragment):
                continue
            suggestions.append(tag)
        return suggestions

    def _hide_popup(_event: object | None = None) -> None:
        window = popup_state.get("window")
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
        popup_state["window"] = None
        popup_state["listbox"] = None
        popup_state["items"] = []

    def _notify_input_changed() -> None:
        if callable(on_input_changed):
            on_input_changed()

    def _apply_selection(
        tag_name: str,
        *,
        committed_override: tuple[str, ...] | None = None,
    ) -> None:
        committed = (
            tuple(committed_override)
            if committed_override is not None
            else tuple(selection_state.get("committed", ()) or ())
        )
        next_tags = [*committed, tag_name][:MAX_TAGS_PER_RECORD]
        text = ", ".join(next_tags)
        if len(next_tags) < MAX_TAGS_PER_RECORD:
            text = f"{text}, "
        combobox.delete(0, tk.END)
        combobox.insert(0, text)
        _remember_input_state(text)
        _notify_input_changed()
        _hide_popup()
        combobox.focus_set()
        combobox.icursor(tk.END)

    def _show_popup(*, focus_listbox: bool = False) -> None:
        _remember_input_state()
        suggestions = _build_suggestions(combobox.get())
        combobox["values"] = [tag.name for tag in suggestions]
        if not suggestions:
            _hide_popup()
            return
        _hide_popup()
        popup = tk.Toplevel(owner)
        popup.wm_overrideredirect(True)
        popup.configure(bg=palette.border_soft)
        popup.transient(owner.winfo_toplevel())
        x = combobox.winfo_rootx()
        y = combobox.winfo_rooty() + combobox.winfo_height() + 2
        width = max(combobox.winfo_width(), 220)
        popup.wm_geometry(f"{width}x160+{x}+{y}")
        listbox = tk.Listbox(
            popup,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=(FONT_FAMILY, 10),
            selectmode=tk.SINGLE,
            bg=palette.surface_elevated,
            fg=palette.text_primary,
            selectbackground=palette.accent_blue,
            selectforeground=palette.surface_elevated,
        )
        listbox.pack(fill="both", expand=True, padx=1, pady=1)
        for index, tag in enumerate(suggestions):
            listbox.insert(tk.END, f"#{tag.name}")
            listbox.itemconfig(
                index,
                fg=str(getattr(tag, "color", "") or palette.text_primary),
                bg=palette.surface_elevated,
            )
        listbox.selection_set(0)
        listbox.activate(0)
        popup_state["window"] = popup
        popup_state["listbox"] = listbox
        popup_state["items"] = suggestions

        def _confirm_selection(_event: tk.Event | None = None) -> str:
            selected = listbox.curselection()
            if not selected:
                return "break"
            chosen = suggestions[int(selected[0])]
            _apply_selection(str(getattr(chosen, "name", "") or ""))
            return "break"

        listbox.bind("<Return>", _confirm_selection, add="+")
        listbox.bind("<Double-Button-1>", _confirm_selection, add="+")
        listbox.bind("<ButtonRelease-1>", _confirm_selection, add="+")
        listbox.bind("<Escape>", lambda _event: (_hide_popup(), "break")[1], add="+")
        popup.bind("<FocusOut>", _hide_popup, add="+")
        if focus_listbox:
            popup.after(0, listbox.focus_set)

    def _prepare_native_dropdown() -> None:
        _remember_input_state()
        suggestions = _build_suggestions(combobox.get())
        combobox["values"] = [tag.name for tag in suggestions]

    def _on_key_release(event: tk.Event | None = None) -> None:
        if event is not None and event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
            return
        _remember_input_state()
        _notify_input_changed()
        _show_popup()

    def _on_down(_event: tk.Event | None = None) -> str:
        _show_popup(focus_listbox=True)
        listbox = popup_state.get("listbox")
        if listbox is not None:
            listbox.focus_set()
        return "break"

    def _on_combobox_selected(_event: tk.Event | None = None) -> str:
        chosen = normalize_tag_name(combobox.get())
        if not chosen:
            return "break"
        committed = tuple(selection_state.get("committed", ()) or ())
        if chosen in committed:
            _apply_selection(
                chosen,
                committed_override=tuple(tag for tag in committed if tag != chosen),
            )
        else:
            _apply_selection(chosen, committed_override=committed)
        return "break"

    combobox.configure(postcommand=_prepare_native_dropdown)
    combobox.bind("<KeyRelease>", _on_key_release, add="+")
    combobox.bind("<Down>", _on_down, add="+")
    combobox.bind("<<ComboboxSelected>>", _on_combobox_selected, add="+")
    combobox.bind("<Button-1>", lambda _event: combobox.after(0, _show_popup), add="+")
    combobox.bind("<FocusOut>", lambda _event: combobox.after(100, _hide_popup), add="+")
