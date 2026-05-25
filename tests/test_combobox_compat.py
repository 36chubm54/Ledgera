from __future__ import annotations

import logging
import tkinter as tk
from tkinter import TclError, ttk
from typing import Any, cast
from unittest.mock import patch

import pytest

from gui.combobox_compat import (
    GuiDisplayRuntime,
    WaylandComboboxPopup,
    detect_gui_display_runtime,
    enable_wayland_combobox_support,
    resolve_linux_combobox_policy,
)


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


def test_detect_gui_display_runtime_native_wayland() -> None:
    with patch("gui.combobox_compat.sys.platform", "linux"):
        runtime = detect_gui_display_runtime(
            {
                "XDG_SESSION_TYPE": "wayland",
                "WAYLAND_DISPLAY": "wayland-0",
            }
        )

    assert runtime.is_linux is True
    assert runtime.is_packaged is False
    assert runtime.is_appimage is False
    assert runtime.is_wayland_native is True
    assert runtime.is_xwayland is False


def test_detect_gui_display_runtime_xwayland() -> None:
    with patch("gui.combobox_compat.sys.platform", "linux"):
        runtime = detect_gui_display_runtime(
            {
                "XDG_SESSION_TYPE": "wayland",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": "wayland-0",
            }
        )

    assert runtime.is_linux is True
    assert runtime.is_packaged is False
    assert runtime.is_appimage is False
    assert runtime.is_wayland_native is False
    assert runtime.is_xwayland is True


def test_resolve_linux_combobox_policy_uses_compat_popup_for_wayland_sessions() -> None:
    assert resolve_linux_combobox_policy(_native_wayland_runtime()) == "compat-popup"
    assert (
        resolve_linux_combobox_policy(
            GuiDisplayRuntime(
                platform="linux",
                session_type="wayland",
                wayland_display="wayland-0",
                x11_display=":0",
                is_linux=True,
                is_packaged=False,
                is_appimage=False,
                is_wayland_native=False,
                is_xwayland=True,
            )
        )
        == "compat-popup"
    )


def test_resolve_linux_combobox_policy_prefers_native_guards_for_packaged_linux() -> None:
    assert resolve_linux_combobox_policy(_packaged_wayland_runtime()) == "patched-native"


def test_resolve_linux_combobox_policy_keeps_appimage_on_compat_popup() -> None:
    assert resolve_linux_combobox_policy(_appimage_wayland_runtime()) == "compat-popup"


def test_enable_wayland_combobox_support_skips_non_linux_runtime() -> None:
    try:
        root = tk.Tk()
    except TclError as error:
        pytest.skip(f"Tk runtime unavailable in this environment: {error}")
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["A", "B"], state="readonly")
        manager = enable_wayland_combobox_support(
            combo,
            runtime=GuiDisplayRuntime(
                platform="win32",
                session_type="",
                wayland_display="",
                x11_display="",
                is_linux=False,
                is_packaged=False,
                is_appimage=False,
                is_wayland_native=False,
                is_xwayland=False,
            ),
        )

        assert manager is None
        assert not hasattr(combo, "_wayland_popup_manager")
    finally:
        root.destroy()


def test_enable_wayland_combobox_support_installs_linux_native_guards_on_x11() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["A", "B"], state="readonly")
        manager = enable_wayland_combobox_support(
            combo,
            runtime=GuiDisplayRuntime(
                platform="linux",
                session_type="x11",
                wayland_display="",
                x11_display=":0",
                is_linux=True,
                is_packaged=False,
                is_appimage=False,
                is_wayland_native=False,
                is_xwayland=False,
            ),
        )

        assert manager is None
        assert bool(getattr(root, "_linux_combobox_native_guards_installed", False)) is True
    finally:
        root.destroy()


def test_wayland_popup_opens_and_applies_selection() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        variable = tk.StringVar(value="Alpha")
        combo = ttk.Combobox(
            root, textvariable=variable, values=["Alpha", "Beta"], state="readonly"
        )
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_native_wayland_runtime())
        assert manager is not None

        manager.open_popup()
        root.update()

        assert manager.popup is not None
        assert manager.listbox is not None
        manager.listbox.selection_clear(0, tk.END)
        manager.listbox.selection_set(1)
        manager.listbox.activate(1)
        manager._select_active()
        root.update()

        assert combo.get() == "Beta"
        assert manager.popup is None
    finally:
        root.destroy()


def test_wayland_popup_alt_down_opens_when_down_binding_disabled() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["One", "Two"], state="readonly")
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(
            combo,
            bind_down=False,
            runtime=_native_wayland_runtime(),
        )
        assert manager is not None

        manager.open_popup()
        root.update()

        assert manager.popup is not None
        manager.close_popup()
        root.update()
    finally:
        root.destroy()


def test_wayland_popup_support_is_enabled_for_xwayland_sessions() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["One", "Two"], state="readonly")
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(
            combo,
            runtime=GuiDisplayRuntime(
                platform="linux",
                session_type="wayland",
                wayland_display="wayland-0",
                x11_display=":0",
                is_linux=True,
                is_packaged=False,
                is_appimage=False,
                is_wayland_native=False,
                is_xwayland=True,
            ),
        )
        assert manager is not None
        assert hasattr(combo, "_linux_popup_manager")
    finally:
        root.destroy()


def test_packaged_linux_uses_native_guards_instead_of_popup_manager() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["One", "Two"], state="readonly")
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_packaged_wayland_runtime())

        assert manager is None
        assert not hasattr(combo, "_linux_popup_manager")
        assert bool(getattr(root, "_linux_combobox_native_guards_installed", False)) is True
    finally:
        root.destroy()


def test_appimage_linux_uses_popup_manager_instead_of_native_guards() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["One", "Two"], state="readonly")
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_appimage_wayland_runtime())

        assert manager is not None
        assert hasattr(combo, "_linux_popup_manager")
        assert not bool(getattr(root, "_linux_combobox_native_guards_installed", False))
    finally:
        root.destroy()


def test_wayland_popup_supports_normal_combobox_via_alt_down() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["Food", "Travel"], state="normal")
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_native_wayland_runtime())
        assert manager is not None

        manager.open_popup()
        root.update()

        assert manager.popup is not None
        assert manager.listbox is not None
        manager.listbox.selection_clear(0, tk.END)
        manager.listbox.selection_set(1)
        manager.listbox.activate(1)
        manager._select_active()
        root.update()

        assert combo.get() == "Travel"
    finally:
        root.destroy()


def test_wayland_popup_supports_normal_combobox_arrow_click_only() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["Food", "Travel"], state="normal", width=20)
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_native_wayland_runtime())
        assert manager is not None

        with patch.object(manager, "_clicked_arrow_zone", return_value=False):
            assert manager._on_click(None) is None
        assert manager.popup is None

        with patch.object(manager, "_clicked_arrow_zone", return_value=True):
            manager._on_click(None)
        root.update()
        assert manager.popup is not None
    finally:
        root.destroy()


def test_wayland_popup_preserves_values_with_spaces() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(
            root,
            values=["[1] Main Wallet (KZT)", "[2] Savings Wallet (USD)"],
            state="readonly",
        )
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_native_wayland_runtime())
        assert manager is not None

        manager.open_popup()
        root.update()

        assert manager.listbox is not None
        assert manager.listbox.get(0) == "[1] Main Wallet (KZT)"
        assert manager.listbox.get(1) == "[2] Savings Wallet (USD)"
    finally:
        root.destroy()


def test_wayland_popup_width_matches_combobox_width() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["RU", "EN"], state="readonly", width=4)
        combo.pack()
        root.update_idletasks()

        manager = enable_wayland_combobox_support(combo, runtime=_native_wayland_runtime())
        assert manager is not None

        manager.open_popup()
        root.update()

        assert manager.popup is not None
        assert manager.popup.winfo_width() == combo.winfo_width()
    finally:
        root.destroy()


def test_wayland_popup_height_tracks_item_count() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        short_combo = ttk.Combobox(root, values=["RU", "EN"], state="readonly", width=8)
        long_combo = ttk.Combobox(
            root,
            values=["One", "Two", "Three", "Four", "Five", "Six"],
            state="readonly",
            width=8,
        )
        short_combo.pack()
        long_combo.pack()
        root.update_idletasks()

        short_manager = enable_wayland_combobox_support(
            short_combo, runtime=_native_wayland_runtime()
        )
        long_manager = enable_wayland_combobox_support(
            long_combo, runtime=_native_wayland_runtime()
        )
        assert short_manager is not None
        assert long_manager is not None

        short_manager.open_popup()
        root.update()
        assert short_manager.popup is not None
        short_height = short_manager.popup.winfo_height()
        short_manager.close_popup()
        root.update()

        long_manager.open_popup()
        root.update()
        assert long_manager.popup is not None
        long_height = long_manager.popup.winfo_height()

        assert short_height < long_height
    finally:
        root.destroy()


def test_wayland_popup_close_logs_expected_cleanup_failure(caplog) -> None:
    class PopupStub:
        def place_forget(self) -> None:
            raise tk.TclError("popup already removed")

        def destroy(self) -> None:
            raise AssertionError("destroy should not run after place_forget failure")

    class WidgetStub:
        def after_idle(self, callback):
            callback()
            return "after-id"

        def after_cancel(self, _after_id: str) -> None:
            return None

        def focus_set(self) -> None:
            return None

    manager = cast(Any, WaylandComboboxPopup.__new__(WaylandComboboxPopup))
    manager.widget = WidgetStub()
    manager.bind_down = True
    manager.popup = PopupStub()
    manager.listbox = object()
    manager.scrollbar = object()
    manager.values = ("A",)
    manager._opening_popup = False
    manager._focus_check_after_id = None
    manager._finish_open_after_id = None
    manager._restore_focus_after_id = None

    caplog.set_level(logging.DEBUG)

    manager.close_popup()

    assert "Combobox popup cleanup skipped" in caplog.text
    assert "popup already removed" in caplog.text
