"""Bulk asset snapshot dialog for the dashboard tab."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import center_dialog, show_error, show_info
from gui.ui_theme import get_palette

from ..core.contracts import DashboardTabContext
from .actions import (
    _bulk_snapshot_form_error,
    _prepare_bulk_snapshot_entries,
    minor_to_money_text,
    set_button_enabled,
)

logger = logging.getLogger(__name__)


def show_bulk_asset_snapshot_dialog(
    parent: tk.Misc,
    *,
    context: DashboardTabContext,
    on_saved: Callable[[], None],
) -> None:
    palette = get_palette()
    assets = list(context.controller.get_assets(active_only=True))
    if not assets:
        show_info(
            tr("dashboard.bulk.no_assets", "Нет активных активов для обновления."),
            title=tr("dashboard.bulk.title", "Массовое обновление"),
            parent=parent,
        )
        return

    latest_map = {
        int(snapshot.asset_id): snapshot
        for snapshot in context.controller.get_latest_asset_snapshots(active_only=True)
    }

    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(tr("dashboard.bulk.title", "Массовое обновление"))
    dialog.transient(parent.winfo_toplevel())
    dialog.minsize(900, 500)
    dialog.resizable(True, True)
    dialog.configure(background=palette.background)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(3, weight=1)

    ttk.Label(
        content,
        text=tr("dashboard.bulk.title", "Массовое обновление"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        content,
        text=tr(
            "dashboard.bulk.hint",
            "Заполняйте только те активы, которые нужно обновить. Пустые строки будут пропущены.",
        ),
        foreground=palette.text_muted,
    ).grid(row=1, column=0, sticky="w", pady=(4, 10))

    header = ttk.Frame(content)
    header.grid(row=2, column=0, sticky="ew")
    header.grid_columnconfigure(3, weight=1)

    ttk.Label(header, text=tr("dashboard.bulk.snapshot_date", "Дата снимка:")).grid(
        row=0, column=0, sticky="w"
    )
    snapshot_date_var = tk.StringVar(value=date.today().isoformat())
    snapshot_date_entry = ttk.Entry(header, width=14, textvariable=snapshot_date_var)
    snapshot_date_entry.grid(row=0, column=1, sticky="w", padx=(6, 16))

    ttk.Label(
        header,
        text=tr(
            "dashboard.bulk.snapshot_date_hint", "Эта дата применяется ко всем заполненным строкам."
        ),
        foreground=palette.text_muted,
    ).grid(row=0, column=2, sticky="w")

    table_frame = ttk.Frame(content)
    table_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(0, weight=1)

    canvas = tk.Canvas(
        table_frame,
        highlightthickness=0,
        bg=palette.surface,
        highlightbackground=palette.border_soft,
    )
    canvas.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(table_frame, orient="vertical", command=canvas.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scroll.set)

    rows = ttk.Frame(canvas, padding=(10, 10))
    window_id = canvas.create_window((0, 0), window=rows, anchor="nw")
    rows.grid_columnconfigure(0, minsize=190)
    rows.grid_columnconfigure(1, minsize=170)
    rows.grid_columnconfigure(2, minsize=90)
    rows.grid_columnconfigure(3, minsize=140)
    rows.grid_columnconfigure(4, weight=1, minsize=260)

    titles = [
        (tr("dashboard.asset", "Актив"), 0),
        (tr("dashboard.asset.current_value", "Текущее значение"), 1),
        (tr("common.currency_short", "Валюта"), 2),
        (tr("dashboard.asset.new_value", "Новое значение"), 3),
        (tr("common.note", "Примечание"), 4),
    ]
    for title, column in titles:
        ttk.Label(rows, text=title, font=("Segoe UI", 9, "bold")).grid(
            row=0,
            column=column,
            sticky="w",
            padx=(0, 12),
            pady=(0, 10),
        )

    value_vars: dict[int, tk.StringVar] = {}
    note_vars: dict[int, tk.StringVar] = {}

    for row_index, asset in enumerate(assets, start=1):
        visual_row = row_index * 2 - 1
        latest = latest_map.get(int(asset.id))
        current_text = tr("dashboard.asset.no_snapshot", "Снимка нет")
        initial_value = ""
        if latest is not None:
            current_text = f"{minor_to_money_text(int(latest.value_minor))} {latest.currency}"
            initial_value = minor_to_money_text(int(latest.value_minor))

        ttk.Label(rows, text=str(asset.name)).grid(
            row=visual_row,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=6,
        )
        ttk.Label(rows, text=current_text, foreground=palette.text_muted).grid(
            row=visual_row,
            column=1,
            sticky="w",
            padx=(0, 12),
            pady=6,
        )
        ttk.Label(rows, text=str(asset.currency)).grid(
            row=visual_row,
            column=2,
            sticky="w",
            padx=(0, 12),
            pady=6,
        )

        value_var = tk.StringVar(value=initial_value)
        note_var = tk.StringVar(value="")
        value_vars[int(asset.id)] = value_var
        note_vars[int(asset.id)] = note_var

        ttk.Entry(rows, width=16, textvariable=value_var).grid(
            row=visual_row,
            column=3,
            sticky="ew",
            padx=(0, 12),
            pady=6,
        )
        ttk.Entry(rows, textvariable=note_var).grid(
            row=visual_row,
            column=4,
            sticky="ew",
            pady=6,
        )

        ttk.Separator(rows, orient="horizontal").grid(
            row=visual_row + 1,
            column=0,
            columnspan=5,
            sticky="ew",
            pady=(0, 2),
        )

    def _sync_scrollregion(_event: tk.Event | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _resize_window(_event: tk.Event) -> None:
        canvas.itemconfigure(window_id, width=max(_event.width, 920))

    rows.bind("<Configure>", _sync_scrollregion)
    canvas.bind("<Configure>", _resize_window)

    ttk.Label(
        content,
        text=tr(
            "dashboard.bulk.tip",
            "Подсказка: пустые строки игнорируются, поэтому можно обновлять только те активы, "
            "которые вы изменяли.",
        ),
        foreground=palette.text_muted,
    ).grid(row=4, column=0, sticky="w", pady=(14, 0))

    buttons = ttk.Frame(content)
    buttons.grid(row=5, column=0, sticky="e", pady=(12, 0))
    form_status = ttk.Label(content, foreground=palette.warning)
    form_status.grid(row=5, column=0, sticky="w")

    def _close() -> None:
        dialog.destroy()

    def _validate_form(*_args) -> None:
        error = _bulk_snapshot_form_error(
            assets=assets,
            snapshot_date=snapshot_date_var.get(),
            value_by_asset_id={asset_id: var.get() for asset_id, var in value_vars.items()},
            note_by_asset_id={asset_id: var.get() for asset_id, var in note_vars.items()},
        )
        form_status.config(text=error or "")
        set_button_enabled(save_button, error is None)

    def _save() -> None:
        try:
            entries = _prepare_bulk_snapshot_entries(
                assets=assets,
                snapshot_date=snapshot_date_var.get(),
                value_by_asset_id={asset_id: var.get() for asset_id, var in value_vars.items()},
                note_by_asset_id={asset_id: var.get() for asset_id, var in note_vars.items()},
            )
            if not entries:
                raise ValueError(
                    tr(
                        "dashboard.bulk.error.empty",
                        "Заполните хотя бы одно значение для сохранения снимков.",
                    )
                )
            saved = context.controller.bulk_upsert_asset_snapshots(entries)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DASH_BULK_SNAPSHOT_SAVE_FAILED", error)
            show_error(
                str(error),
                title=tr("dashboard.bulk.error_title", "Ошибка массового обновления"),
                parent=dialog,
            )
            return

        show_info(
            tr("dashboard.bulk.saved", "Сохранено снимков: {count}.", count=len(saved)),
            title=tr("dashboard.bulk.title", "Массовое обновление"),
            parent=dialog,
        )
        dialog.destroy()
        on_saved()

    ttk.Button(buttons, text=tr("common.cancel", "Отмена"), command=_close).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    save_button = ttk.Button(
        buttons,
        text=tr("dashboard.bulk.save", "Сохранить снимки"),
        style="Primary.TButton",
        command=_save,
    )
    save_button.pack(side=tk.LEFT)

    snapshot_date_var.trace_add("write", _validate_form)
    for var in value_vars.values():
        var.trace_add("write", _validate_form)
    for var in note_vars.values():
        var.trace_add("write", _validate_form)
    _validate_form()

    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.update_idletasks()

    center_dialog(dialog, parent, min_width=760, min_height=420)
    dialog.deiconify()
    dialog.grab_set()
    snapshot_date_entry.focus_set()
    parent.wait_window(dialog)
