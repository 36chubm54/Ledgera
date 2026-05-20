from __future__ import annotations

import os
import sys
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Literal

LinuxComboboxPolicy = Literal["native", "patched-native", "compat-popup"]


@dataclass(frozen=True, slots=True)
class GuiDisplayRuntime:
    platform: str
    session_type: str
    wayland_display: str
    x11_display: str
    is_linux: bool
    is_wayland_native: bool
    is_xwayland: bool


def detect_gui_display_runtime(environ: dict[str, str] | None = None) -> GuiDisplayRuntime:
    env = dict(os.environ if environ is None else environ)
    platform_name = sys.platform
    session_type = str(env.get("XDG_SESSION_TYPE", "") or "").strip().lower()
    wayland_display = str(env.get("WAYLAND_DISPLAY", "") or "").strip()
    x11_display = str(env.get("DISPLAY", "") or "").strip()
    is_linux = platform_name.startswith("linux")
    is_xwayland = is_linux and bool(x11_display) and session_type == "wayland"
    is_wayland_native = is_linux and bool(wayland_display) and not is_xwayland
    return GuiDisplayRuntime(
        platform=platform_name,
        session_type=session_type,
        wayland_display=wayland_display,
        x11_display=x11_display,
        is_linux=is_linux,
        is_wayland_native=is_wayland_native,
        is_xwayland=is_xwayland,
    )


def is_wayland_native_runtime(runtime: GuiDisplayRuntime | None = None) -> bool:
    resolved = runtime if runtime is not None else detect_gui_display_runtime()
    return resolved.is_wayland_native


def resolve_linux_combobox_policy(
    runtime: GuiDisplayRuntime | None = None,
    *,
    tk_windowingsystem: str | None = None,
) -> LinuxComboboxPolicy:
    resolved = runtime if runtime is not None else detect_gui_display_runtime()
    if not resolved.is_linux:
        return "native"
    normalized_windowing = str(tk_windowingsystem or "").strip().lower()
    if resolved.session_type == "wayland":
        return "compat-popup"
    if normalized_windowing and normalized_windowing != "x11":
        return "compat-popup"
    return "patched-native"


def should_use_linux_compat_popup(
    runtime: GuiDisplayRuntime | None = None,
    *,
    tk_windowingsystem: str | None = None,
) -> bool:
    return (
        resolve_linux_combobox_policy(
            runtime,
            tk_windowingsystem=tk_windowingsystem,
        )
        == "compat-popup"
    )


def should_style_native_linux_popdown(
    runtime: GuiDisplayRuntime | None = None,
    *,
    tk_windowingsystem: str | None = None,
) -> bool:
    return (
        resolve_linux_combobox_policy(
            runtime,
            tk_windowingsystem=tk_windowingsystem,
        )
        != "compat-popup"
    )


def _combobox_state(widget: ttk.Combobox) -> str:
    return str(widget.cget("state") or "").strip().lower()


def _tk_windowingsystem(widget: tk.Misc) -> str:
    try:
        return str(widget.tk.call("tk", "windowingsystem")).strip().lower()
    except tk.TclError:
        return ""


def install_linux_combobox_native_guards(
    root: tk.Misc,
    *,
    runtime: GuiDisplayRuntime | None = None,
) -> None:
    if (
        resolve_linux_combobox_policy(
            runtime,
            tk_windowingsystem=None if runtime is not None else _tk_windowingsystem(root),
        )
        != "patched-native"
    ):
        return
    if bool(getattr(root, "_linux_combobox_native_guards_installed", False)):
        return

    def _derive_owner_path(popdown_widget: tk.Misc) -> str | None:
        name = str(popdown_widget)
        if ".popdown" not in name:
            return None
        return name.rsplit(".popdown", 1)[0]

    def _unpost_for_owner(popdown_widget: tk.Misc) -> None:
        owner_path = _derive_owner_path(popdown_widget)
        if not owner_path:
            return
        try:
            exists = bool(int(popdown_widget.tk.call("winfo", "exists", owner_path)))
        except tk.TclError:
            exists = False
        if not exists:
            return
        try:
            popdown_widget.tk.call("ttk::combobox::Unpost", owner_path)
        except tk.TclError:
            return

    def _monitor_popdown(popdown_widget: tk.Misc) -> None:
        try:
            if not bool(int(popdown_widget.tk.call("winfo", "exists", str(popdown_widget)))):
                return
        except tk.TclError:
            return
        owner_path = _derive_owner_path(popdown_widget)
        if not owner_path:
            return
        try:
            owner_exists = bool(int(popdown_widget.tk.call("winfo", "exists", owner_path)))
        except tk.TclError:
            owner_exists = False
        if not owner_exists:
            return
        try:
            owner_mapped = bool(int(popdown_widget.tk.call("winfo", "ismapped", owner_path)))
        except tk.TclError:
            owner_mapped = False
        try:
            popdown_mapped = bool(
                int(popdown_widget.tk.call("winfo", "ismapped", str(popdown_widget)))
            )
        except tk.TclError:
            popdown_mapped = False
        if not owner_mapped and popdown_mapped:
            _unpost_for_owner(popdown_widget)
            return
        if popdown_mapped:
            popdown_widget.after(125, lambda: _monitor_popdown(popdown_widget))

    def _on_popdown_map(event: tk.Event[tk.Misc]) -> None:
        widget = event.widget
        try:
            widget.tk.call("wm", "attributes", str(widget), "-topmost", 0)
        except tk.TclError:
            pass
        widget.after_idle(lambda: _monitor_popdown(widget))

    root.bind_class("ComboboxPopdown", "<Map>", _on_popdown_map, add="+")
    setattr(root, "_linux_combobox_native_guards_installed", True)  # noqa: B010


class WaylandComboboxPopup:
    def __init__(
        self,
        widget: ttk.Combobox,
        *,
        bind_down: bool = True,
    ) -> None:
        self.widget = widget
        self.bind_down = bind_down
        self.popup: ttk.Frame | None = None
        self.listbox: tk.Listbox | None = None
        self.scrollbar: ttk.Scrollbar | None = None
        self.values: tuple[str, ...] = ()
        self._opening_popup = False
        self._focus_check_after_id: str | None = None
        self._bind_events()

    def _bind_events(self) -> None:
        self.widget.bind("<Button-1>", self._on_click, add="+")
        self.widget.bind("<Alt-Down>", self._on_alt_down, add="+")
        self.widget.bind("<F4>", self._on_alt_down, add="+")
        if self.bind_down:
            self.widget.bind("<Down>", self._on_down, add="+")
        self.widget.bind("<Escape>", self._on_escape, add="+")
        self.widget.bind("<Tab>", self._on_tab, add="+")
        self.widget.bind("<Destroy>", self._on_owner_destroy, add="+")

    def _combo_values(self) -> tuple[str, ...]:
        raw_values = self.widget.cget("values")
        if isinstance(raw_values, str):
            try:
                parsed = self.widget.tk.splitlist(raw_values)
            except tk.TclError:
                parsed = tuple(value for value in raw_values.split() if value)
            return tuple(str(value) for value in parsed if str(value))
        if isinstance(raw_values, tuple):
            return tuple(str(value) for value in raw_values if str(value))
        if isinstance(raw_values, list):
            return tuple(str(value) for value in raw_values if str(value))
        return ()

    def _is_readonly(self) -> bool:
        return _combobox_state(self.widget) == "readonly"

    def _is_normal(self) -> bool:
        return _combobox_state(self.widget) == "normal"

    def _supports_popup_fallback(self) -> bool:
        return _combobox_state(self.widget) in {"readonly", "normal"}

    def _clicked_arrow_zone(self, event: tk.Event | None) -> bool:
        if event is None:
            return False
        try:
            width = int(self.widget.winfo_width())
        except tk.TclError:
            return False
        arrow_zone_width = max(24, min(36, width // 5 if width > 0 else 24))
        event_x = int(getattr(event, "x", -1))
        return event_x >= max(width - arrow_zone_width, 0)

    def _contains_widget(self, widget: tk.Misc | None) -> bool:
        if widget is None:
            return False
        popup = self.popup
        if popup is not None and str(widget).startswith(str(popup)):
            return True
        return widget is self.widget

    def _current_index(self) -> int:
        current_value = str(self.widget.get() or "")
        try:
            return self.values.index(current_value)
        except ValueError:
            return 0

    def _popup_placement(self, *, height: int) -> tuple[int, int, int, int]:
        self.widget.update_idletasks()
        owner = self.widget.winfo_toplevel()
        owner.update_idletasks()
        root_x = self.widget.winfo_rootx() - owner.winfo_rootx()
        root_y = self.widget.winfo_rooty() - owner.winfo_rooty()
        width = max(int(self.widget.winfo_width()), 1)
        owner_width = owner.winfo_width()
        owner_height = owner.winfo_height()
        pos_x = min(max(root_x, 0), max(owner_width - width, 0))
        pos_y = root_y + self.widget.winfo_height() + 2
        if pos_y + height > owner_height:
            pos_y = max(root_y - height - 2, 0)
        return pos_x, pos_y, width, height

    def _cancel_focus_check(self) -> None:
        after_id = self._focus_check_after_id
        self._focus_check_after_id = None
        if not after_id:
            return
        try:
            self.widget.after_cancel(after_id)
        except tk.TclError:
            return

    def _release_focus(self) -> None:
        try:
            self.widget.focus_set()
        except tk.TclError:
            return

    def close_popup(self, *, restore_focus: bool = True) -> None:
        popup = self.popup
        self._cancel_focus_check()
        self.popup = None
        self.listbox = None
        self.scrollbar = None
        self.values = ()
        self._opening_popup = False
        if popup is None:
            return
        try:
            popup.place_forget()
            popup.destroy()
        except tk.TclError:
            pass
        if restore_focus:
            self.widget.after_idle(self._release_focus)

    def _select_active(self) -> str:
        listbox = self.listbox
        if listbox is None:
            return "break"
        selection = listbox.curselection()
        if not selection:
            return "break"
        index = int(selection[0])
        if index < 0 or index >= len(self.values):
            return "break"
        value = self.values[index]
        self.widget.set(value)
        self.widget.event_generate("<<ComboboxSelected>>")
        self.close_popup()
        return "break"

    def _move_selection(self, delta: int) -> str:
        listbox = self.listbox
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

    def _schedule_focus_check(self, delay_ms: int = 75) -> None:
        self._cancel_focus_check()
        self._focus_check_after_id = self.widget.after(delay_ms, self._check_focus)

    def _check_focus(self) -> None:
        self._focus_check_after_id = None
        if self.popup is None or self._opening_popup:
            return
        try:
            focus_widget = self.widget.winfo_toplevel().focus_get()
        except tk.TclError:
            focus_widget = None
        if not self._contains_widget(focus_widget):
            self.close_popup(restore_focus=False)

    def _close_if_focus_lost(self, _event: tk.Event | None = None) -> None:
        if self.popup is None or self._opening_popup:
            return
        self._schedule_focus_check()

    def _finish_open_popup(self) -> None:
        self._opening_popup = False
        if self.popup is None:
            return
        self._schedule_focus_check(125)

    def open_popup(self) -> str:
        if not self._supports_popup_fallback():
            return ""
        self.values = self._combo_values()
        if not self.values:
            self.close_popup(restore_focus=False)
            return "break"
        if self.popup is not None:
            self.close_popup(restore_focus=False)
            return "break"
        owner = self.widget.winfo_toplevel()
        popup = ttk.Frame(owner, padding=1, style="Card.TFrame")
        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(0, weight=1)
        frame = ttk.Frame(popup)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        listbox = tk.Listbox(
            frame,
            activestyle="none",
            borderwidth=0,
            exportselection=False,
            highlightthickness=0,
            selectmode=tk.SINGLE,
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar: ttk.Scrollbar | None = None
        for value in self.values:
            listbox.insert(tk.END, value)
        visible_rows = min(max(len(self.values), 1), 10)
        listbox.configure(height=visible_rows)
        if len(self.values) > visible_rows:
            scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            listbox.configure(yscrollcommand=scrollbar.set)
        current_index = self._current_index()
        listbox.selection_set(current_index)
        listbox.activate(current_index)
        listbox.see(current_index)

        self.popup = popup
        self.listbox = listbox
        self.scrollbar = scrollbar
        self._opening_popup = True

        popup.update_idletasks()
        pos_x, pos_y, width, height = self._popup_placement(height=popup.winfo_reqheight())
        popup.place(x=pos_x, y=pos_y, width=width, height=height)
        popup.lift()
        listbox.focus_set()
        popup.after_idle(self._finish_open_popup)

        listbox.bind("<Return>", lambda _event: self._select_active(), add="+")
        listbox.bind("<KP_Enter>", lambda _event: self._select_active(), add="+")
        listbox.bind("<Double-Button-1>", lambda _event: self._select_active(), add="+")
        listbox.bind("<ButtonRelease-1>", lambda _event: self._select_active(), add="+")
        listbox.bind("<Escape>", lambda _event: (self.close_popup(), "break")[1], add="+")
        listbox.bind(
            "<Tab>", lambda _event: (self.close_popup(restore_focus=False), None)[1], add="+"
        )
        listbox.bind("<Up>", lambda _event: self._move_selection(-1), add="+")
        listbox.bind("<Down>", lambda _event: self._move_selection(1), add="+")
        listbox.bind("<FocusOut>", self._close_if_focus_lost, add="+")
        popup.bind("<FocusOut>", self._close_if_focus_lost, add="+")
        popup.bind("<Destroy>", lambda _event: self.close_popup(restore_focus=False), add="+")
        return "break"

    def _on_click(self, _event: tk.Event | None = None) -> str | None:
        if not self._is_readonly():
            if self._is_normal() and self._clicked_arrow_zone(_event):
                return self.open_popup()
            return None
        return self.open_popup()

    def _on_alt_down(self, _event: tk.Event | None = None) -> str:
        return self.open_popup()

    def _on_down(self, _event: tk.Event | None = None) -> str:
        return self.open_popup()

    def _on_escape(self, _event: tk.Event | None = None) -> str | None:
        if self.popup is None:
            return None
        self.close_popup(restore_focus=False)
        return "break"

    def _on_tab(self, _event: tk.Event | None = None) -> str | None:
        if self.popup is None:
            return None
        self.close_popup(restore_focus=False)
        return None

    def _on_owner_destroy(self, _event: tk.Event | None = None) -> None:
        self.close_popup(restore_focus=False)


def enable_wayland_combobox_support(
    widget: ttk.Combobox,
    *,
    bind_down: bool = True,
    runtime: GuiDisplayRuntime | None = None,
) -> WaylandComboboxPopup | None:
    policy = resolve_linux_combobox_policy(
        runtime,
        tk_windowingsystem=None if runtime is not None else _tk_windowingsystem(widget),
    )
    if policy == "compat-popup":
        manager = WaylandComboboxPopup(widget, bind_down=bind_down)
        setattr(widget, "_wayland_popup_manager", manager)  # noqa: B010
        setattr(widget, "_linux_popup_manager", manager)  # noqa: B010
        return manager
    if policy == "patched-native":
        install_linux_combobox_native_guards(widget.winfo_toplevel(), runtime=runtime)
    return None
