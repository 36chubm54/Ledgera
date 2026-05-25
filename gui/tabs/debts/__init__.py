"""Debts tab subpackage."""

import tkinter as tk
from tkinter import ttk

from gui.ui_dialogs import messagebox_compat as messagebox

from .core.builder import build_debts_tab as _build_debts_tab
from .core.contracts import DebtsTabBindings, DebtsTabContext, refresh_debts_views
from .support.render import _draw_debt_progress, _segment_widths


def build_debts_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: DebtsTabContext,
) -> DebtsTabBindings:
    return _build_debts_tab(parent, context=context, messagebox_module=messagebox)


__all__ = [
    "DebtsTabBindings",
    "DebtsTabContext",
    "build_debts_tab",
    "refresh_debts_views",
    "_segment_widths",
    "_draw_debt_progress",
    "messagebox",
]
