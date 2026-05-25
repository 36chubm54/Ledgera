"""Shared tag input helpers for the operations tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from tkinter import ttk
from typing import Any, Protocol

from gui.combobox_compat import detect_gui_display_runtime
from gui.ui_theme import FONT_FAMILY, get_palette
from utils.records.tags import MAX_TAGS_PER_RECORD, normalize_tag_name, parse_tag_string


class TagController(Protocol):
    def list_tags(self) -> Sequence[object]: ...


def list_tags_safe(controller: TagController) -> list[Any]:
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


def sorted_tags_by_popularity(controller: TagController) -> list[Any]:
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
    runtime = detect_gui_display_runtime()
    use_linux_custom_popup = runtime.is_linux and (runtime.is_appimage or not runtime.is_packaged)
    popup_state: dict[str, Any] = {"window": None, "listbox": None, "items": []}
    selection_state: dict[str, Any] = {"committed": (), "fragment": ""}
    focus_check_after_id: dict[str, str | None] = {"value": None}

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

    def _cancel_focus_check() -> None:
        after_id = focus_check_after_id["value"]
        focus_check_after_id["value"] = None
        if not after_id:
            return
        try:
            combobox.after_cancel(after_id)
        except tk.TclError:
            return

    def _contains_widget(widget: tk.Misc | None) -> bool:
        if widget is None:
            return False
        window = popup_state.get("window")
        if window is not None and str(widget).startswith(str(window)):
            return True
        return widget is combobox

    def _check_focus() -> None:
        focus_check_after_id["value"] = None
        window = popup_state.get("window")
        if window is None:
            return
        try:
            focus_widget = combobox.winfo_toplevel().focus_get()
        except tk.TclError:
            focus_widget = None
        if not _contains_widget(focus_widget):
            _hide_popup()

    def _schedule_focus_check(delay_ms: int = 75) -> None:
        _cancel_focus_check()
        focus_check_after_id["value"] = combobox.after(delay_ms, _check_focus)

    def _popup_placement(*, height: int) -> tuple[int, int, int, int]:
        combobox.update_idletasks()
        owner_window = combobox.winfo_toplevel()
        owner_window.update_idletasks()
        root_x = combobox.winfo_rootx() - owner_window.winfo_rootx()
        root_y = combobox.winfo_rooty() - owner_window.winfo_rooty()
        width = max(int(combobox.winfo_width()), 1)
        owner_width = owner_window.winfo_width()
        owner_height = owner_window.winfo_height()
        pos_x = min(max(root_x, 0), max(owner_width - width, 0))
        pos_y = root_y + combobox.winfo_height() + 2
        if pos_y + height > owner_height:
            pos_y = max(root_y - height - 2, 0)
        return pos_x, pos_y, width, height

    def _clicked_arrow_zone(event: tk.Event | None) -> bool:
        if event is None:
            return False
        try:
            width = int(combobox.winfo_width())
        except tk.TclError:
            return False
        arrow_zone_width = max(24, min(36, width // 5 if width > 0 else 24))
        event_x = int(getattr(event, "x", -1))
        return event_x >= max(width - arrow_zone_width, 0)

    def _hide_popup(_event: object | None = None) -> None:
        _cancel_focus_check()
        window = popup_state.get("window")
        if window is not None:
            try:
                window.place_forget()
                window.destroy()
            except tk.TclError:
                pass
        popup_state["window"] = None
        popup_state["listbox"] = None
        popup_state["items"] = []

    def _render_suggestions(listbox: tk.Listbox, suggestions: list[Any]) -> None:
        listbox.delete(0, tk.END)
        for index, tag in enumerate(suggestions):
            listbox.insert(tk.END, f"#{tag.name}")
            listbox.itemconfig(
                index,
                fg=str(getattr(tag, "color", "") or palette.text_primary),
                bg=palette.surface_elevated,
            )
        if suggestions:
            listbox.selection_set(0)
            listbox.activate(0)

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
        popup = popup_state.get("window")
        listbox = popup_state.get("listbox")
        if popup is None or listbox is None:
            owner_window = owner.winfo_toplevel()
            popup = ttk.Frame(owner_window, padding=1, style="Card.TFrame")
            popup.grid_columnconfigure(0, weight=1)
            popup.grid_rowconfigure(0, weight=1)
            listbox = tk.Listbox(
                popup,
                activestyle="none",
                borderwidth=0,
                exportselection=False,
                highlightthickness=0,
                font=(FONT_FAMILY, 10),
                selectmode=tk.SINGLE,
                bg=palette.surface_elevated,
                fg=palette.text_primary,
                selectbackground=palette.accent_blue,
                selectforeground=palette.surface_elevated,
            )
            listbox.pack(fill="both", expand=True, padx=1, pady=1)
            popup_state["window"] = popup
            popup_state["listbox"] = listbox

            def _confirm_selection(_event: tk.Event | None = None) -> str:
                selected = listbox.curselection()
                if not selected:
                    return "break"
                items = popup_state.get("items", [])
                if not items:
                    return "break"
                chosen = items[int(selected[0])]
                _apply_selection(str(getattr(chosen, "name", "") or ""))
                return "break"

            listbox.bind("<Return>", _confirm_selection, add="+")
            listbox.bind("<Double-Button-1>", _confirm_selection, add="+")
            listbox.bind("<ButtonRelease-1>", _confirm_selection, add="+")
            listbox.bind("<ButtonPress-1>", lambda _event: _cancel_focus_check(), add="+")
            listbox.bind("<Escape>", lambda _event: (_hide_popup(), "break")[1], add="+")
            listbox.bind("<FocusOut>", lambda _event: _schedule_focus_check(), add="+")
            popup.bind("<FocusOut>", lambda _event: _schedule_focus_check(), add="+")

        listbox.configure(height=min(max(len(suggestions), 1), 10))
        _render_suggestions(listbox, suggestions)
        popup_state["items"] = suggestions

        popup.update_idletasks()
        pos_x, pos_y, width, height = _popup_placement(height=popup.winfo_reqheight())
        popup.place(x=pos_x, y=pos_y, width=width, height=height)
        popup.lift()
        if focus_listbox:
            popup.after(0, listbox.focus_set)
        else:
            _schedule_focus_check(125)

    def _prepare_native_dropdown() -> None:
        _remember_input_state()
        suggestions = _build_suggestions(combobox.get())
        combobox["values"] = [tag.name for tag in suggestions]

    def _move_selection(delta: int) -> str:
        listbox = popup_state.get("listbox")
        if listbox is None:
            return "break"
        size = listbox.size()
        if size <= 0:
            return "break"
        current = listbox.curselection()
        index = int(current[0]) if current else 0
        next_index = (index + delta) % size
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(next_index)
        listbox.activate(next_index)
        listbox.see(next_index)
        return "break"

    def _on_key_release(event: tk.Event | None = None) -> None:
        if event is not None and event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
            return
        _remember_input_state()
        _notify_input_changed()
        _show_popup()

    def _on_down(_event: tk.Event | None = None) -> str:
        if popup_state.get("listbox") is not None:
            return _move_selection(1)
        _show_popup(focus_listbox=True)
        listbox = popup_state.get("listbox")
        if listbox is not None:
            listbox.focus_set()
        return "break"

    def _on_up(_event: tk.Event | None = None) -> str:
        if popup_state.get("listbox") is None:
            return "break"
        return _move_selection(-1)

    def _on_return(_event: tk.Event | None = None) -> str | None:
        listbox = popup_state.get("listbox")
        if listbox is None:
            return None
        selected = listbox.curselection()
        if not selected:
            return "break"
        chosen = popup_state.get("items", [])[int(selected[0])]
        _apply_selection(str(getattr(chosen, "name", "") or ""))
        return "break"

    def _on_escape(_event: tk.Event | None = None) -> str | None:
        if popup_state.get("window") is None:
            return None
        _hide_popup()
        return "break"

    def _on_click(event: tk.Event | None = None) -> str | None:
        _cancel_focus_check()
        if not _clicked_arrow_zone(event):
            return None
        combobox.after(0, lambda: _show_popup(focus_listbox=True))
        return "break"

    def _on_alt_down(_event: tk.Event | None = None) -> str:
        _cancel_focus_check()
        _show_popup(focus_listbox=True)
        return "break"

    def _on_destroy(_event: tk.Event | None = None) -> None:
        _cancel_focus_check()
        _hide_popup()

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

    if not use_linux_custom_popup:

        def _on_native_key_release(event: tk.Event | None = None) -> None:
            if event is not None and event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
                return
            _remember_input_state()
            _notify_input_changed()
            _prepare_native_dropdown()

        combobox.bind("<KeyRelease>", _on_native_key_release, add="+")
        combobox.bind("<<ComboboxSelected>>", _on_combobox_selected, add="+")
        return

    combobox.bind("<KeyRelease>", _on_key_release, add="+")
    combobox.bind("<Down>", _on_down, add="+")
    combobox.bind("<Up>", _on_up, add="+")
    combobox.bind("<Alt-Down>", _on_alt_down, add="+")
    combobox.bind("<F4>", _on_alt_down, add="+")
    combobox.bind("<Return>", _on_return, add="+")
    combobox.bind("<KP_Enter>", _on_return, add="+")
    combobox.bind("<Escape>", _on_escape, add="+")
    combobox.bind("<<ComboboxSelected>>", _on_combobox_selected, add="+")
    combobox.bind("<Button-1>", _on_click, add="+")
    combobox.bind("<FocusOut>", lambda _event: _schedule_focus_check(125), add="+")
    combobox.bind("<Destroy>", _on_destroy, add="+")
