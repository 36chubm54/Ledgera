from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.shell.core.lifecycle import schedule_deferred_action
from gui.shell.core.setup import attach_tab_aliases
from gui.shell.core.startup import report_startup_auto_payments
from gui.shell.core.state import assign_status_bar_state
from gui.shell.windowing.window import activate_main_window
from gui.startup_coordinator import DeferredStartupCoordinator
from gui.status_bar_builder import build_status_bar
from gui.tab_lifecycle import TAB_ORDER, attach_tabs, create_tab_frames
from gui.ui_helpers import show_info
from gui.ui_theme import PAD_SM, PAD_XL, PAD_XS, get_palette


def build_owner_startup_coordinator(
    owner: Any, *, logger: logging.Logger
) -> DeferredStartupCoordinator:
    def _refresh_charts_deferred(records: list[Any] | None = None) -> None:
        schedule_deferred_action(
            owner._schedule_after_idle,
            "startup_refresh_charts",
            lambda: owner._refresh_charts(records=records),
        )

    def _refresh_budgets_deferred() -> None:
        schedule_deferred_action(
            owner._schedule_after_idle,
            "startup_refresh_budgets",
            owner._refresh_budgets,
        )

    def _refresh_all_deferred() -> None:
        schedule_deferred_action(
            owner._schedule_after_idle,
            "startup_refresh_all",
            owner._refresh_all,
        )

    return DeferredStartupCoordinator(
        controller=owner.controller,
        repository=owner.repository,
        run_background=owner._run_background,
        schedule_after_idle=owner._schedule_after_idle,
        schedule_after=owner._schedule_after,
        refresh_list=owner._refresh_list,
        refresh_charts=_refresh_charts_deferred,
        refresh_budgets=_refresh_budgets_deferred,
        refresh_all=_refresh_all_deferred,
        apply_saved_online_mode=owner._apply_saved_online_mode,
        show_auto_payment_message=lambda created_auto_payments: report_startup_auto_payments(
            created_auto_payments,
            logger=logger,
            format_money=lambda amount: owner.controller.format_display_money(amount),
            show_info_message=lambda message: show_info(
                message,
                title=tr("app.autopay.title", "Автоплатежи применены"),
            ),
        ),
        restore_keyboard_focus=lambda: activate_main_window(owner),
        set_busy=owner._set_busy,
        logger=logger,
    )


def initialize_owner_shell_layout(
    owner: Any, *, register_hotkeys_func: Callable[[Any], None]
) -> None:
    owner._status_bar = assign_status_bar_state(owner, build_status_bar(owner))
    owner._status_bar.grid(row=2, column=0, sticky="ew")

    notebook = ttk.Notebook(owner)
    notebook.grid(row=0, column=0, sticky="nsew")
    owner._notebook = notebook
    owner._notebook_underline = tk.Canvas(
        owner,
        height=3,
        highlightthickness=0,
        bd=0,
        bg=get_palette().background,
    )

    owner._tab_order = list(TAB_ORDER)
    owner._tab_widgets = create_tab_frames(notebook)
    attach_tab_aliases(owner, owner._tab_widgets)
    owner._tab_keys_by_widget = attach_tabs(notebook, owner._tab_widgets)
    notebook.bind("<<NotebookTabChanged>>", owner._on_tab_changed, add="+")
    notebook.bind("<Configure>", lambda _event: owner._schedule_notebook_underline(), add="+")
    owner.bind("<Configure>", lambda _event: owner._schedule_notebook_underline(), add="+")
    owner.bind_all("<MouseWheel>", owner._on_legend_mousewheel, add="+")

    owner._ensure_tab_built("infographics")
    owner._ensure_tab_built("operations")
    register_hotkeys_func(owner)


def initialize_owner_busy_overlay(owner: Any) -> None:
    owner._busy_frame = ttk.Frame(owner, style="Card.TFrame", padding=(PAD_XL, PAD_SM))
    owner._busy_frame.grid(row=1, column=0, sticky="ew", padx=PAD_XL, pady=(0, PAD_SM))
    owner._busy_frame.grid_columnconfigure(0, weight=1)
    owner._busy_message_var = tk.StringVar(
        value=tr("app.busy.startup", "Подготавливаем рабочее пространство...")
    )
    owner._busy_label = ttk.Label(
        owner._busy_frame,
        textvariable=owner._busy_message_var,
        style="Hint.TLabel",
        justify="left",
    )
    owner._busy_label.grid(row=0, column=0, sticky="w", pady=(0, PAD_XS))
    owner.progress = ttk.Progressbar(owner._busy_frame, mode="indeterminate")
    owner.progress.grid(row=1, column=0, sticky="ew")
    owner._busy_frame.grid_remove()
