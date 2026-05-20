from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

from gui.tabs.operations.tag_input import attach_tag_autocomplete


class _Tag:
    def __init__(self, name: str, color: str = "#4caf50") -> None:
        self.name = name
        self.color = color


def _linux_runtime() -> object:
    from gui.combobox_compat import GuiDisplayRuntime

    return GuiDisplayRuntime(
        platform="linux",
        session_type="wayland",
        wayland_display="wayland-0",
        x11_display="",
        is_linux=True,
        is_packaged=False,
        is_appimage=False,
        is_wayland_native=True,
        is_xwayland=False,
    )


def _packaged_linux_runtime() -> object:
    from gui.combobox_compat import GuiDisplayRuntime

    return GuiDisplayRuntime(
        platform="linux",
        session_type="wayland",
        wayland_display="wayland-0",
        x11_display=":0",
        is_linux=True,
        is_packaged=True,
        is_appimage=False,
        is_wayland_native=False,
        is_xwayland=True,
    )


def _appimage_linux_runtime() -> object:
    from gui.combobox_compat import GuiDisplayRuntime

    return GuiDisplayRuntime(
        platform="linux",
        session_type="wayland",
        wayland_display="wayland-0",
        x11_display=":0",
        is_linux=True,
        is_packaged=True,
        is_appimage=True,
        is_wayland_native=False,
        is_xwayland=True,
    )


def _windows_runtime() -> object:
    from gui.combobox_compat import GuiDisplayRuntime

    return GuiDisplayRuntime(
        platform="win32",
        session_type="",
        wayland_display="",
        x11_display="",
        is_linux=False,
        is_packaged=False,
        is_appimage=False,
        is_wayland_native=False,
        is_xwayland=False,
    )


def test_attach_tag_autocomplete_uses_native_combobox_outside_linux() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, state="normal")
        combo.pack()
        with patch(
            "gui.tabs.operations.tag_input.detect_gui_display_runtime",
            return_value=_windows_runtime(),
        ):
            attach_tag_autocomplete(
                owner=root,
                combobox=combo,
                list_tags=lambda: [_Tag("kursach"), _Tag("copy")],
            )

        assert combo.bind("<Alt-Down>") == ""
        assert combo.bind("<F4>") == ""
    finally:
        root.destroy()


def test_attach_tag_autocomplete_binds_linux_custom_popup_keys() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, state="normal")
        combo.pack()
        with patch(
            "gui.tabs.operations.tag_input.detect_gui_display_runtime",
            return_value=_linux_runtime(),
        ):
            attach_tag_autocomplete(
                owner=root,
                combobox=combo,
                list_tags=lambda: [_Tag("kursach"), _Tag("copy")],
            )

        assert combo.bind("<Alt-Down>") != ""
        assert combo.bind("<F4>") != ""
    finally:
        root.destroy()


def test_attach_tag_autocomplete_keeps_packaged_linux_on_native_combobox_path() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, state="normal")
        combo.pack()
        with patch(
            "gui.tabs.operations.tag_input.detect_gui_display_runtime",
            return_value=_packaged_linux_runtime(),
        ):
            attach_tag_autocomplete(
                owner=root,
                combobox=combo,
                list_tags=lambda: [_Tag("kursach"), _Tag("copy")],
            )

        assert combo.bind("<Alt-Down>") == ""
        assert combo.bind("<F4>") == ""
    finally:
        root.destroy()


def test_attach_tag_autocomplete_keeps_appimage_linux_on_custom_popup_path() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, state="normal")
        combo.pack()
        with patch(
            "gui.tabs.operations.tag_input.detect_gui_display_runtime",
            return_value=_appimage_linux_runtime(),
        ):
            attach_tag_autocomplete(
                owner=root,
                combobox=combo,
                list_tags=lambda: [_Tag("kursach"), _Tag("copy")],
            )

        assert combo.bind("<Alt-Down>") != ""
        assert combo.bind("<F4>") != ""
    finally:
        root.destroy()
