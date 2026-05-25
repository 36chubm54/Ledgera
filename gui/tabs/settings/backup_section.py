from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, ttk
from typing import Any

from app_paths import get_backups_dir
from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_SM, PAD_XS, create_card_section

from .support.backup_support import start_backup_export, start_backup_import
from .support.wallets_support import MessageBoxLike


def build_backup_section(
    left_panel: tk.Frame | ttk.Frame,
    *,
    parent: tk.Frame | ttk.Frame,
    context: Any,
    refresh_wallets: Callable[[], None],
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 2,
) -> None:
    pad_x = PAD_SM
    pad_y = PAD_XS

    backup_card = create_card_section(left_panel, tr("settings.backup", "Резервная копия (JSON)"))
    backup_card.grid(row=row_index, column=0, sticky="ew")
    backup_frame = backup_card.winfo_children()[-1]
    backup_frame.grid_columnconfigure(0, weight=1)
    backup_frame.grid_columnconfigure(1, weight=1)

    def import_backup() -> None:
        backup_dir = get_backups_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        filepath = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title=tr("settings.backup.import.title", "Импорт полной копии"),
            initialdir=str(backup_dir),
        )
        if not filepath:
            return

        if not messagebox_module.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "settings.backup.import.confirm",
                "Это заменит все кошельки, записи, переводы, обязательные расходы, "
                "бюджеты и данные распределения.\n\n"
                "Импортируйте только резервные копии из доверенного источника. Продолжить?",
            ),
        ):
            return
        start_backup_import(
            context=context,
            filepath=filepath,
            messagebox_module=messagebox_module,
            refresh_wallets=refresh_wallets,
        )

    def export_backup() -> None:
        if not messagebox_module.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "settings.backup.export.warning",
                "Резервная копия будет сохранена как читаемый JSON-файл с финансовыми данными. "
                "Храните его только в доверенном месте. Продолжить?",
            ),
        ):
            return

        backup_dir = get_backups_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title=tr("settings.backup.export.title", "Экспорт полной копии"),
            initialdir=str(backup_dir),
        )
        if not filepath:
            return
        start_backup_export(
            context=context,
            filepath=filepath,
            messagebox_module=messagebox_module,
        )

    ttk.Button(
        backup_frame,
        text=tr("settings.backup.export.button", "Экспорт полной копии"),
        command=export_backup,
    ).grid(row=0, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    ttk.Button(
        backup_frame,
        text=tr("settings.backup.import.button", "Импорт полной копии"),
        command=import_backup,
    ).grid(row=0, column=1, sticky="ew", padx=pad_x, pady=pad_y)
