from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

from gui.ui_theme import (
    bootstrap_ui,
    enable_treeview_zebra,
    get_palette,
    get_theme,
    set_theme,
)


def test_set_theme_switches_runtime_palette() -> None:
    set_theme("dark")
    assert get_theme() == "dark"
    assert get_palette().name == "dark"

    set_theme("light")
    assert get_theme() == "light"
    assert get_palette().name == "light"


def test_bootstrap_ui_supports_light_and_dark() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        bootstrap_ui(root, "light")
        light_style = ttk.Style(root)
        assert light_style.lookup("TFrame", "background")

        bootstrap_ui(root, "dark")
        dark_style = ttk.Style(root)
        assert dark_style.lookup("StatusBar.TFrame", "background")
        assert get_theme() == "dark"
    finally:
        root.destroy()
        set_theme("light")


def test_bootstrap_ui_skips_combobox_popdown_theme_under_compat_popup_policy() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        combo = ttk.Combobox(root, values=["A", "B"], state="readonly")
        combo.pack()
        with (
            patch("gui.ui.theme_widgets.should_style_native_linux_popdown", return_value=False),
            patch("gui.ui.theme_widgets._configure_combobox_popdown") as configure_mock,
        ):
            bootstrap_ui(root, "light")

        configure_mock.assert_not_called()
    finally:
        root.destroy()
        set_theme("light")


def test_enable_treeview_zebra_cancels_pending_after_job_on_destroy() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        tree = ttk.Treeview(root, columns=("name",), show="headings")
        tree.heading("name", text="Name")
        tree.pack()
        enable_treeview_zebra(tree)

        assert tree.tk.call("after", "info")

        tree.destroy()

        assert not tree.tk.call("after", "info")
    finally:
        root.destroy()
        set_theme("light")
