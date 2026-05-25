"""Settings tab subpackage."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.tabs.wallet_manager import show_wallet_manager_dialog
from gui.ui_dialogs import messagebox_compat as messagebox

from .core.builder import build_settings_tab as _build_settings_tab
from .core.contracts import SettingsTabBindings, SettingsTabContext


def build_settings_tab(
    parent: tk.Frame | ttk.Frame,
    context: SettingsTabContext,
) -> SettingsTabBindings:
    return _build_settings_tab(
        parent,
        context,
        messagebox_module=messagebox,
        wallet_manager_dialog=show_wallet_manager_dialog,
    )


__all__ = [
    "SettingsTabBindings",
    "SettingsTabContext",
    "build_settings_tab",
    "messagebox",
    "show_wallet_manager_dialog",
]
