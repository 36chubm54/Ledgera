from __future__ import annotations

import tkinter as tk
from unittest.mock import patch

from gui.combobox_compat import GuiDisplayRuntime
from gui.status_bar_builder import build_status_bar


def _native_wayland_runtime() -> GuiDisplayRuntime:
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


def _packaged_wayland_runtime() -> GuiDisplayRuntime:
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


def _appimage_wayland_runtime() -> GuiDisplayRuntime:
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


class _Controller:
    def get_available_display_currencies(self) -> list[str]:
        return ["KZT", "USD", "EUR"]

    def get_display_currency(self) -> str:
        return "KZT"


class _Owner(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.controller = _Controller()

    def _on_online_toggle(self) -> None:
        return None

    def _on_display_currency_changed(self, _event: tk.Event | None = None) -> None:
        return None

    def _on_language_changed(self, _event: tk.Event | None = None) -> None:
        return None

    def _on_theme_changed(self, _event: tk.Event | None = None) -> None:
        return None


def test_status_bar_attaches_wayland_popup_support_to_readonly_combos() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with patch(
            "gui.status_bar_builder.enable_wayland_combobox_support",
            wraps=lambda widget: setattr(widget, "_compat_attached", True),
        ) as wrapped:
            result = build_status_bar(owner)

        assert wrapped.call_count == 3
        assert getattr(result.display_currency_combo, "_compat_attached", False) is True
        assert getattr(result.language_combo, "_compat_attached", False) is True
        assert getattr(result.theme_combo, "_compat_attached", False) is True
    finally:
        root.destroy()


def test_status_bar_real_wayland_manager_is_attached_under_native_wayland() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with patch(
            "gui.combobox_compat.detect_gui_display_runtime",
            return_value=_native_wayland_runtime(),
        ):
            result = build_status_bar(owner)

        assert hasattr(result.display_currency_combo, "_wayland_popup_manager")
        assert hasattr(result.language_combo, "_wayland_popup_manager")
        assert hasattr(result.theme_combo, "_wayland_popup_manager")
    finally:
        root.destroy()


def test_status_bar_keeps_packaged_linux_on_native_guard_path() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with (
            patch(
                "gui.combobox_compat.detect_gui_display_runtime",
                return_value=_packaged_wayland_runtime(),
            ),
            patch("gui.combobox_compat._tk_windowingsystem", return_value="x11"),
        ):
            result = build_status_bar(owner)

        assert not hasattr(result.display_currency_combo, "_wayland_popup_manager")
        assert not hasattr(result.language_combo, "_wayland_popup_manager")
        assert not hasattr(result.theme_combo, "_wayland_popup_manager")
        assert bool(getattr(root, "_linux_combobox_native_guards_installed", False)) is True
    finally:
        root.destroy()


def test_status_bar_keeps_appimage_linux_on_popup_manager_path() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with patch(
            "gui.combobox_compat.detect_gui_display_runtime",
            return_value=_appimage_wayland_runtime(),
        ):
            result = build_status_bar(owner)

        assert hasattr(result.display_currency_combo, "_wayland_popup_manager")
        assert hasattr(result.language_combo, "_wayland_popup_manager")
        assert hasattr(result.theme_combo, "_wayland_popup_manager")
    finally:
        root.destroy()
