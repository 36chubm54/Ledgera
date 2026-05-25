"""Import preview dialog for the operations tab."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import VERTICAL, ttk
from typing import Any

from gui.i18n import tr
from gui.ui_helpers import center_dialog


def _bind_dialog_button_navigation(buttons: list[ttk.Button]) -> None:
    if len(buttons) < 2:
        return

    def _focus_button(index: int) -> str:
        buttons[index % len(buttons)].focus_set()
        return "break"

    for index, button in enumerate(buttons):
        button.bind("<Left>", lambda _event, i=index - 1: _focus_button(i), add="+")
        button.bind("<Right>", lambda _event, i=index + 1: _focus_button(i), add="+")
        button.bind("<Up>", lambda _event, i=index - 1: _focus_button(i), add="+")
        button.bind("<Down>", lambda _event, i=index + 1: _focus_button(i), add="+")


def _close_with_break(callback: Any) -> str:
    callback()
    return "break"


def _invoke_if_focused(widget: tk.Misc | None) -> bool:
    if widget is None:
        return False
    focus_widget = widget.winfo_toplevel().focus_get()
    if focus_widget is widget and hasattr(widget, "invoke"):
        widget.invoke()  # type: ignore[attr-defined]
        return True
    return False


def show_import_preview_dialog(
    parent: tk.Misc,
    *,
    filepath: str,
    policy_label: str,
    preview: Any,
    force: bool = False,
) -> bool:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(tr("operations.preview.title", "Предпросмотр импорта"))
    dialog.transient(parent.winfo_toplevel())
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    result = {"confirmed": False}
    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)

    ttk.Label(
        content,
        text=tr("operations.preview.title", "Предпросмотр импорта"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        content,
        text=tr("operations.preview.file", "Файл: {name}", name=Path(filepath).name),
    ).grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Label(
        content,
        text=tr("operations.preview.mode", "Режим: {mode}", mode=policy_label),
    ).grid(row=2, column=0, sticky="w")

    if force:
        ttk.Label(
            content,
            text=tr(
                "operations.preview.force",
                "Это снимок только для чтения. Принудительная замена включена.",
            ),
            foreground="#b45309",
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))
        stats_row = 4
    else:
        stats_row = 3

    stats = ttk.Frame(content)
    stats.grid(row=stats_row, column=0, sticky="ew", pady=(10, 0))
    stats.grid_columnconfigure(1, weight=1)
    ttk.Label(stats, text=tr("operations.preview.imported", "Записей к импорту:")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(stats, text=str(preview.imported)).grid(row=0, column=1, sticky="e")
    ttk.Label(stats, text=tr("operations.preview.skipped", "Пропущено строк:")).grid(
        row=1, column=0, sticky="w"
    )
    ttk.Label(stats, text=str(preview.skipped)).grid(row=1, column=1, sticky="e")
    ttk.Label(stats, text=tr("operations.preview.errors", "Ошибок:")).grid(
        row=2, column=0, sticky="w"
    )
    ttk.Label(stats, text=str(len(preview.errors))).grid(row=2, column=1, sticky="e")

    ttk.Label(content, text=tr("operations.preview.errors", "Ошибки:")).grid(
        row=stats_row + 1, column=0, sticky="w", pady=(10, 4)
    )
    errors_frame = ttk.Frame(content)
    errors_frame.grid(row=stats_row + 2, column=0, sticky="ew")
    errors_frame.grid_columnconfigure(0, weight=1)
    errors_tree = ttk.Treeview(
        errors_frame,
        show="tree",
        selectmode="none",
        height=min(max(len(preview.errors), 1), 5),
    )
    errors_tree.grid(row=0, column=0, sticky="nsew")
    errors_scroll = ttk.Scrollbar(errors_frame, orient=VERTICAL, command=errors_tree.yview)
    errors_scroll.grid(row=0, column=1, sticky="ns")
    errors_tree.config(yscrollcommand=errors_scroll.set)
    for error in preview.errors or [
        tr("operations.preview.no_errors", "Ошибок валидации не найдено.")
    ]:
        errors_tree.insert("", "end", text=error)

    buttons = ttk.Frame(content)
    buttons.grid(row=stats_row + 3, column=0, sticky="e", pady=(12, 0))

    def close() -> None:
        dialog.destroy()

    def proceed() -> None:
        result["confirmed"] = True
        dialog.destroy()

    action_buttons: list[ttk.Button] = []
    if preview.imported > 0:
        import_button = ttk.Button(
            buttons,
            text=tr("operations.import", "Импорт"),
            style="Primary.TButton",
            command=proceed,
        )
        import_button.pack(side=tk.LEFT)
        action_buttons.append(import_button)
    cancel_button = ttk.Button(buttons, text=tr("common.cancel", "Отмена"), command=close)
    cancel_button.pack(side=tk.LEFT, padx=(0, 8))
    action_buttons.append(cancel_button)
    _bind_dialog_button_navigation(action_buttons)

    def _handle_return() -> None:
        if _invoke_if_focused(cancel_button):
            return
        if preview.imported > 0 and _invoke_if_focused(action_buttons[0]):
            return
        if preview.imported > 0:
            proceed()
            return
        close()

    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Escape>", lambda _event: _close_with_break(close), add="+")
    dialog.bind("<Return>", lambda _event: _close_with_break(_handle_return), add="+")
    center_dialog(dialog, parent)
    dialog.deiconify()
    dialog.grab_set()
    if preview.imported > 0:
        action_buttons[0].focus_set()
    else:
        cancel_button.focus_set()
    parent.wait_window(dialog)
    return bool(result["confirmed"])
