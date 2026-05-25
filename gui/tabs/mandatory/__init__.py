"""Mandatory tab subpackage."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.ui_dialogs import messagebox_compat as messagebox

from .core.builder import build_mandatory_tab as _build_mandatory_tab
from .core.contracts import MandatoryTabBindings, MandatoryTabContext


def build_mandatory_tab(
    parent: tk.Frame | ttk.Frame,
    context: MandatoryTabContext,
    import_formats: dict[str, dict[str, str]],
) -> MandatoryTabBindings:
    return _build_mandatory_tab(
        parent,
        context,
        import_formats,
        messagebox_module=messagebox,
    )


__all__ = [
    "MandatoryTabBindings",
    "MandatoryTabContext",
    "build_mandatory_tab",
    "messagebox",
]
