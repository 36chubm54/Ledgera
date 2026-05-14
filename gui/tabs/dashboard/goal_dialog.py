"""Goal creation dialog for the dashboard tab."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import center_dialog, show_error

from .actions import _goal_form_error, _prepare_goal_payload, base_currency_code, set_button_enabled
from .contracts import DashboardTabContext

logger = logging.getLogger(__name__)


def show_create_goal_dialog(
    parent: tk.Misc,
    *,
    context: DashboardTabContext,
    on_saved: Callable[[], None],
) -> None:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(tr("dashboard.goal.dialog.title", "Создание цели"))
    dialog.transient(parent.winfo_toplevel())
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    for column in (1, 3):
        content.grid_columnconfigure(column, weight=1)

    ttk.Label(
        content,
        text=tr("dashboard.goal.dialog.title", "Создание цели"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, columnspan=4, sticky="w")

    title_var = tk.StringVar()
    amount_var = tk.StringVar()
    currency_var = tk.StringVar(value=base_currency_code(context.controller))
    created_at_var = tk.StringVar(value=date.today().isoformat())
    target_date_var = tk.StringVar()
    description_var = tk.StringVar()

    ttk.Label(content, text=tr("dashboard.goal.field.title", "Название")).grid(
        row=1, column=0, sticky="w", pady=(10, 0)
    )
    title_entry = ttk.Entry(content, textvariable=title_var, width=28)
    title_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 10))

    ttk.Label(content, text=tr("dashboard.goal.field.amount", "Целевая сумма")).grid(
        row=1, column=2, sticky="w", pady=(10, 0)
    )
    amount_entry = ttk.Entry(content, textvariable=amount_var, width=16)
    amount_entry.grid(row=2, column=2, sticky="ew", padx=(0, 10))

    ttk.Label(content, text=tr("dashboard.goal.field.currency", "Валюта")).grid(
        row=1, column=3, sticky="w", pady=(10, 0)
    )
    currency_entry = ttk.Entry(content, textvariable=currency_var, width=8)
    currency_entry.grid(row=2, column=3, sticky="ew")

    ttk.Label(content, text=tr("dashboard.goal.field.created", "Дата создания")).grid(
        row=3, column=0, sticky="w", pady=(10, 0)
    )
    created_at_entry = ttk.Entry(content, textvariable=created_at_var, width=16)
    created_at_entry.grid(row=4, column=0, sticky="ew", padx=(0, 10))

    ttk.Label(content, text=tr("dashboard.goal.field.target", "Целевая дата")).grid(
        row=3, column=1, sticky="w", pady=(10, 0)
    )
    target_date_entry = ttk.Entry(content, textvariable=target_date_var, width=16)
    target_date_entry.grid(row=4, column=1, sticky="ew", padx=(0, 10))

    ttk.Label(content, text=tr("dashboard.goal.field.description", "Описание")).grid(
        row=3, column=2, columnspan=2, sticky="w", pady=(10, 0)
    )
    description_entry = ttk.Entry(content, textvariable=description_var)
    description_entry.grid(row=4, column=2, columnspan=2, sticky="ew")

    ttk.Label(
        content,
        text=tr(
            "dashboard.goal.dialog.hint",
            "Используйте формат ГГГГ-ММ-ДД. Целевую дату можно не заполнять.",
        ),
        foreground="#6b7280",
    ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
    form_status = ttk.Label(content, foreground="#b45309")
    form_status.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

    buttons = ttk.Frame(content)
    buttons.grid(row=7, column=0, columnspan=4, sticky="e", pady=(12, 0))

    def _close() -> None:
        dialog.destroy()

    def _validate_form(*_args) -> None:
        error = _goal_form_error(
            title=title_var.get(),
            target_amount=amount_var.get(),
            currency=currency_var.get(),
            created_at=created_at_var.get(),
            target_date=target_date_var.get(),
            description=description_var.get(),
        )
        form_status.config(text=error or "")
        set_button_enabled(save_button, error is None)

    def _save() -> None:
        try:
            payload = _prepare_goal_payload(
                title=title_var.get(),
                target_amount=amount_var.get(),
                currency=currency_var.get(),
                created_at=created_at_var.get(),
                target_date=target_date_var.get(),
                description=description_var.get(),
            )
            context.controller.create_goal(**payload)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DASH_GOAL_CREATE_FAILED", error)
            show_error(str(error), title=tr("common.error", "Ошибка"), parent=dialog)
            return
        dialog.destroy()
        on_saved()

    ttk.Button(buttons, text=tr("common.cancel", "Отмена"), command=_close).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    save_button = ttk.Button(
        buttons,
        text=tr("dashboard.create_goal", "Создать цель"),
        style="Primary.TButton",
        command=_save,
    )
    save_button.pack(side=tk.LEFT)

    for var in (
        title_var,
        amount_var,
        currency_var,
        created_at_var,
        target_date_var,
        description_var,
    ):
        var.trace_add("write", _validate_form)
    _validate_form()

    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.update_idletasks()

    center_dialog(dialog, parent, min_width=560, min_height=220)
    dialog.deiconify()
    dialog.grab_set()
    title_entry.focus_set()
    parent.wait_window(dialog)
