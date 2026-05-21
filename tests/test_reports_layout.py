from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

from gui.combobox_compat import GuiDisplayRuntime
from gui.tabs.reports.layout import build_reports_layout


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


def _packaged_x11_runtime() -> GuiDisplayRuntime:
    return GuiDisplayRuntime(
        platform="linux",
        session_type="x11",
        wayland_display="",
        x11_display=":0",
        is_linux=True,
        is_packaged=True,
        is_appimage=False,
        is_wayland_native=False,
        is_xwayland=False,
    )


class _Owner(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.period_start_var = tk.StringVar()
        self.period_end_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.tag_var = tk.StringVar()
        self.wallet_var = tk.StringVar()
        self.group_var = tk.BooleanVar(value=True)
        self.totals_mode_var = tk.StringVar(value="fixed")
        self._group_status_var = tk.StringVar()

    def _apply_group_ui_state(self) -> None:
        return None

    def _on_group_back(self) -> None:
        return None

    def _on_generate(self) -> None:
        return None

    def _export(self, _fmt: str) -> None:
        return None

    def _refresh_summary_only(self) -> None:
        return None


def test_reports_layout_uses_linux_custom_export_popup_for_appimage() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with patch(
            "gui.tabs.reports.layout.detect_gui_display_runtime",
            return_value=_appimage_wayland_runtime(),
        ):
            ui = build_reports_layout(owner)

        assert hasattr(ui.export_button, "_linux_export_popup_manager")
        assert str(ui.export_button.cget("menu")) == ""
    finally:
        root.destroy()


def test_reports_layout_keeps_native_export_menu_for_packaged_x11() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with (
            patch(
                "gui.tabs.reports.layout.detect_gui_display_runtime",
                return_value=_packaged_x11_runtime(),
            ),
            patch("gui.tabs.reports.layout._tk_windowingsystem", return_value="x11"),
        ):
            ui = build_reports_layout(owner)

        assert not hasattr(ui.export_button, "_linux_export_popup_manager")
        assert str(ui.export_button.cget("menu")) != ""
    finally:
        root.destroy()


def test_linux_export_popup_closes_when_application_focus_is_lost() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        owner = _Owner(root)
        owner.pack()

        with patch(
            "gui.tabs.reports.layout.detect_gui_display_runtime",
            return_value=_appimage_wayland_runtime(),
        ):
            ui = build_reports_layout(owner)

        manager = getattr(ui.export_button, "_linux_export_popup_manager")
        manager.open_popup()
        root.update()

        assert manager.popup is not None
        with patch.object(ui.export_button, "focus_displayof", return_value=None):
            manager._close_if_focus_still_lost()

        assert manager.popup is None
    finally:
        root.destroy()
