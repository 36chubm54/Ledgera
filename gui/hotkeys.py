"""Hotkey system for FinancialApp."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.ui_helpers import center_dialog, enable_treeview_column_autosize

_CONTROL_MASK = 0x0004
_SHIFT_MASK = 0x0001

_LATIN_CYRILLIC_ALIASES: dict[str, tuple[str, ...]] = {
    "i": ("i", "sh", "cyrillic_sha", "ш"),
    "e": ("e", "u", "cyrillic_u", "у"),
    "g": ("g", "p", "cyrillic_pe", "п"),
    "c": ("c", "s", "cyrillic_es", "с"),
    "x": ("x", "ch", "cyrillic_che", "ч"),
    "p": ("p", "z", "cyrillic_ze", "з"),
    "r": ("r", "k", "cyrillic_ka", "к"),
    "t": ("t", "cyrillic_ie", "е"),
    "w": ("w", "ts", "cyrillic_tse", "ц"),
}

_LETTER_KEYCODES: dict[str, int] = {
    "c": 67,
    "e": 69,
    "g": 71,
    "i": 73,
    "p": 80,
    "r": 82,
    "t": 84,
    "w": 87,
    "x": 88,
}


def _active_tab(app: Any) -> str | None:
    """Return the active tab key or None."""
    notebook = getattr(app, "_notebook", None)
    tab_keys = getattr(app, "_tab_keys_by_widget", None)
    if notebook is None or not isinstance(tab_keys, dict):
        return None
    try:
        selected = notebook.select()
    except tk.TclError:
        return None
    return tab_keys.get(str(selected))


def _focus_widget(app: Any) -> Any | None:
    focus_get = getattr(app, "focus_get", None)
    if not callable(focus_get):
        return None
    try:
        return focus_get()
    except tk.TclError:
        return None


def _focus_is_entry(app: Any) -> bool:
    """Return True when focus is on a text input widget."""
    widget = _focus_widget(app)
    return isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text))


def _focus_is_combo_or_text(app: Any) -> bool:
    """Return True when Enter should remain local to the focused widget."""
    widget = _focus_widget(app)
    return isinstance(widget, (ttk.Combobox, tk.Text))


def _operations_inline_editor_active(app: Any) -> bool:
    bindings = getattr(app, "_operations_bindings", None)
    checker = getattr(bindings, "inline_editor_active", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception:
        return False


def _focus_in_shell(app: Any) -> bool:
    """Return True when shortcuts should target the main application shell."""
    try:
        grab_widget = app.grab_current()
    except Exception:
        grab_widget = None
    if grab_widget is not None:
        try:
            if grab_widget.winfo_toplevel() != app.winfo_toplevel():
                return False
        except Exception:
            return False

    widget = _focus_widget(app)
    if widget is None:
        return True

    toplevel = getattr(widget, "winfo_toplevel", None)
    if not callable(toplevel):
        return True
    try:
        return toplevel() == app.winfo_toplevel()
    except Exception:
        return False


def _call_action(action: Callable[[], Any] | None) -> bool:
    if not callable(action):
        return False
    action()
    return True


def _has_control(event: Any) -> bool:
    return bool(int(getattr(event, "state", 0)) & _CONTROL_MASK)


def _has_shift(event: Any) -> bool:
    return bool(int(getattr(event, "state", 0)) & _SHIFT_MASK)


def _matches_letter_shortcut(event: Any, letter: str) -> bool:
    keysym = str(getattr(event, "keysym", "") or "").strip().lower()
    char = str(getattr(event, "char", "") or "").strip().lower()
    keycode = getattr(event, "keycode", None)
    aliases = _LATIN_CYRILLIC_ALIASES.get(letter, (letter,))

    if keysym in aliases or char in aliases:
        return True

    expected_keycode = _LETTER_KEYCODES.get(letter)
    if expected_keycode is not None and keycode == expected_keycode:
        return True
    return False


def _show_hotkey_help(app: Any) -> None:
    """Show the modal hotkey help dialog."""
    existing = getattr(app, "_hotkey_help_dialog", None)
    if isinstance(existing, tk.Toplevel) and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return

    dialog = tk.Toplevel(app)
    app._hotkey_help_dialog = dialog
    dialog.withdraw()
    dialog.title(tr("hotkeys.help.title", "Горячие клавиши"))
    dialog.transient(app)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(0, weight=1)

    columns = ("key", "scope", "action")
    tree = ttk.Treeview(content, columns=columns, show="headings", height=17)
    tree.heading("key", text=tr("hotkeys.help.key", "Клавиша"))
    tree.heading("scope", text=tr("hotkeys.help.scope", "Область"))
    tree.heading("action", text=tr("hotkeys.help.action", "Действие"))
    tree.column("key", width=140, minwidth=140, stretch=False, anchor="w")
    tree.column("scope", width=120, minwidth=120, stretch=False, anchor="w")
    tree.column("action", width=240, minwidth=240, stretch=True, anchor="w")
    enable_treeview_column_autosize(tree, columns=("action",), max_width=420)
    tree.grid(row=0, column=0, sticky="nsew")

    scrollbar = ttk.Scrollbar(content, orient=tk.VERTICAL, command=tree.yview)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
    tree.configure(yscrollcommand=scrollbar.set)

    rows = [
        (
            "Alt+1..8",
            tr("hotkeys.scope.global", "Глобально"),
            tr("hotkeys.action.switch_tab", "Переключить вкладку"),
        ),
        (
            "F5",
            tr("hotkeys.scope.global", "Глобально"),
            tr("hotkeys.action.refresh_data", "Обновить данные"),
        ),
        (
            "F1 / ?",
            tr("hotkeys.scope.global", "Глобально"),
            tr("hotkeys.action.this_help", "Эта справка"),
        ),
        (
            "Ctrl+I",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.income", "Тип -> Доход"),
        ),
        (
            "Ctrl+E",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.expense", "Тип -> Расход"),
        ),
        (
            "Home",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.first", "Первая запись"),
        ),
        (
            "End",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.end", "Последняя запись"),
        ),
        (
            "Ctrl+E",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.expense", "Тип -> Расход"),
        ),
        (
            "Del",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.delete", "Удалить запись"),
        ),
        (
            "Ctrl+Del",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.delete_all", "Удалить все записи"),
        ),
        (
            "F2",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.edit", "Редактировать запись"),
        ),
        (
            "Enter",
            tr("tabs.operations", "Операции"),
            tr("hotkeys.action.operations.save", "Сохранить операцию"),
        ),
        (
            "Ctrl+G",
            tr("tabs.reports", "Отчеты"),
            tr("hotkeys.action.reports.generate", "Сформировать отчет"),
        ),
        (
            "Ctrl+Shift+C",
            tr("tabs.reports", "Отчеты"),
            tr("hotkeys.action.reports.csv", "Экспорт CSV"),
        ),
        (
            "Ctrl+Shift+X",
            tr("tabs.reports", "Отчеты"),
            tr("hotkeys.action.reports.xlsx", "Экспорт XLSX"),
        ),
        (
            "Ctrl+Shift+P",
            tr("tabs.reports", "Отчеты"),
            tr("hotkeys.action.reports.pdf", "Экспорт PDF"),
        ),
        (
            "Ctrl+R",
            tr("tabs.analytics", "Аналитика"),
            tr("hotkeys.action.analytics.refresh", "Обновить аналитику"),
        ),
        (
            "Ctrl+T",
            tr("tabs.analytics", "Аналитика"),
            tr("hotkeys.action.analytics.toggle_tags", "Переключить режим тегов"),
        ),
        ("Enter", tr("tabs.budget", "Бюджет"), tr("hotkeys.action.budget.add", "Добавить бюджет")),
        ("Del", tr("tabs.budget", "Бюджет"), tr("hotkeys.action.budget.delete", "Удалить бюджет")),
        (
            "F2",
            tr("tabs.budget", "Бюджет"),
            tr("hotkeys.action.budget.edit", "Редактировать бюджет"),
        ),
        ("Enter", tr("tabs.debts", "Долги"), tr("hotkeys.action.debts.add", "Добавить долг")),
        ("Ctrl+P", tr("tabs.debts", "Долги"), tr("hotkeys.action.debts.pay", "Погасить долг")),
        (
            "Ctrl+W",
            tr("tabs.debts", "Долги"),
            tr("hotkeys.action.debts.write_off", "Списать долг"),
        ),
        ("Del", tr("tabs.debts", "Долги"), tr("hotkeys.action.debts.delete", "Удалить долг")),
    ]
    for row in rows:
        tree.insert("", "end", values=row)

    buttons = ttk.Frame(content)
    buttons.grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))

    def _close() -> None:
        if getattr(app, "_hotkey_help_dialog", None) is dialog:
            app._hotkey_help_dialog = None
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        if dialog.winfo_exists():
            dialog.destroy()

    close_button = ttk.Button(buttons, text=tr("common.close", "Закрыть"), command=_close)
    close_button.grid(row=0, column=0, sticky="e")

    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.bind("<Escape>", lambda _event: _close(), add="+")
    center_dialog(dialog, app, min_width=560, min_height=360)
    dialog.deiconify()
    dialog.grab_set()
    close_button.focus_set()


def register_hotkeys(app: Any) -> None:
    """Register all application hotkeys once."""
    if getattr(app, "_hotkeys_registered", False):
        return

    def _bind(sequence: str, handler: Callable[[Any], bool]) -> None:
        def _wrapped(event=None):
            if handler(event):
                return "break"
            return None

        app.bind_all(sequence, _wrapped, add="+")

    def _switch_to(tab_key: str) -> bool:
        notebook = getattr(app, "_notebook", None)
        widgets = getattr(app, "_tab_widgets", None)
        if notebook is None or not isinstance(widgets, dict):
            return False
        target = widgets.get(tab_key)
        if target is None:
            return False
        notebook.select(target)
        return True

    def _refresh_all_views() -> bool:
        called = False
        for attr_name in ("_refresh_list", "_refresh_charts", "_refresh_budgets", "_refresh_all"):
            called = _call_action(getattr(app, attr_name, None)) or called
        return called

    def _tab_binding(attr_name: str, tab_key: str) -> Any | None:
        if _active_tab(app) != tab_key:
            return None
        return getattr(app, attr_name, None)

    def _export_report(fmt: str) -> bool:
        reports_tab = _tab_binding("_reports_tab", "reports")
        export = getattr(reports_tab, "_export", None)
        if not callable(export):
            return False
        export(fmt)
        return True

    def _guarded_tab_action(action: Callable[[], bool], *, block_on_entry: bool = False) -> bool:
        if not _focus_in_shell(app):
            return False
        if block_on_entry and _focus_is_entry(app):
            return False
        return action()

    def _allow_operations_shell_hotkeys() -> bool:
        return not (_active_tab(app) == "operations" and _operations_inline_editor_active(app))

    for index, tab_key in enumerate(getattr(app, "_tab_order", [])[:8], start=1):
        _bind(
            f"<Alt-Key-{index}>",
            lambda _event, key=tab_key: _guarded_tab_action(lambda: _switch_to(key)),
        )

    _bind("<F1>", lambda _event: _show_hotkey_help(app) or True)
    _bind("<F5>", lambda _event: _guarded_tab_action(_refresh_all_views))
    _bind(
        "<Home>",
        lambda _event: _guarded_tab_action(
            lambda: _call_action(
                getattr(_tab_binding("_operations_bindings", "operations"), "select_first", None)
            ),
            block_on_entry=True,
        ),
    )
    _bind(
        "<End>",
        lambda _event: _guarded_tab_action(
            lambda: _call_action(
                getattr(_tab_binding("_operations_bindings", "operations"), "select_last", None)
            ),
            block_on_entry=True,
        ),
    )
    _bind(
        "<Delete>",
        lambda _event: (
            False
            if not _allow_operations_shell_hotkeys()
            else _guarded_tab_action(
                lambda: (
                    _call_action(
                        getattr(
                            _tab_binding("_operations_bindings", "operations"),
                            "delete_selected",
                            None,
                        )
                    )
                    or _call_action(
                        getattr(_tab_binding("_budget_bindings", "budget"), "delete_budget", None)
                    )
                    or _call_action(
                        getattr(_tab_binding("_debt_bindings", "debts"), "delete_debt", None)
                    )
                ),
                block_on_entry=True,
            )
        ),
    )
    _bind(
        "<Control-Delete>",
        lambda _event: (
            False
            if not _allow_operations_shell_hotkeys()
            else _guarded_tab_action(
                lambda: _call_action(
                    getattr(_tab_binding("_operations_bindings", "operations"), "delete_all", None)
                ),
                block_on_entry=True,
            )
        ),
    )
    _bind(
        "<F2>",
        lambda _event: (
            False
            if not _allow_operations_shell_hotkeys()
            else _guarded_tab_action(
                lambda: (
                    _call_action(
                        getattr(
                            _tab_binding("_operations_bindings", "operations"),
                            "edit_selected",
                            None,
                        )
                    )
                    or _call_action(
                        getattr(_tab_binding("_budget_bindings", "budget"), "edit_budget", None)
                    )
                ),
                block_on_entry=True,
            )
        ),
    )
    _bind(
        "<Return>",
        lambda _event: (
            False
            if _focus_is_combo_or_text(app) or not _allow_operations_shell_hotkeys()
            else _guarded_tab_action(
                lambda: (
                    _call_action(
                        getattr(
                            _tab_binding("_operations_bindings", "operations"), "save_record", None
                        )
                    )
                    or _call_action(
                        getattr(_tab_binding("_budget_bindings", "budget"), "add_budget", None)
                    )
                    or _call_action(
                        getattr(_tab_binding("_debt_bindings", "debts"), "add_debt", None)
                    )
                )
            )
        ),
    )

    def _on_control_keypress(event: Any) -> bool:
        if not _has_control(event) or _has_shift(event):
            return False
        if _matches_letter_shortcut(event, "i"):
            if not _allow_operations_shell_hotkeys():
                return False
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(
                        _tab_binding("_operations_bindings", "operations"), "set_type_income", None
                    )
                )
            )
        if _matches_letter_shortcut(event, "e"):
            if not _allow_operations_shell_hotkeys():
                return False
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(
                        _tab_binding("_operations_bindings", "operations"), "set_type_expense", None
                    )
                )
            )
        if _matches_letter_shortcut(event, "g"):
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(_tab_binding("_reports_tab", "reports"), "_on_generate", None)
                )
            )
        if _matches_letter_shortcut(event, "r"):
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(_tab_binding("_analytics_bindings", "analytics"), "refresh", None)
                )
            )
        if _matches_letter_shortcut(event, "t"):
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(
                        _tab_binding("_analytics_bindings", "analytics"), "toggle_tag_mode", None
                    )
                ),
            )
        if _matches_letter_shortcut(event, "p"):
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(_tab_binding("_debt_bindings", "debts"), "pay_debt", None)
                ),
                block_on_entry=True,
            )
        if _matches_letter_shortcut(event, "w"):
            return _guarded_tab_action(
                lambda: _call_action(
                    getattr(_tab_binding("_debt_bindings", "debts"), "write_off_debt", None)
                ),
                block_on_entry=True,
            )
        return False

    def _on_control_shift_keypress(event: Any) -> bool:
        if not _has_control(event) or not _has_shift(event):
            return False
        if _matches_letter_shortcut(event, "c"):
            return _guarded_tab_action(lambda: _export_report("csv"))
        if _matches_letter_shortcut(event, "x"):
            return _guarded_tab_action(lambda: _export_report("xlsx"))
        if _matches_letter_shortcut(event, "p"):
            return _guarded_tab_action(lambda: _export_report("pdf"))
        return False

    _bind("<Control-KeyPress>", _on_control_keypress)
    _bind("<Control-Shift-KeyPress>", _on_control_shift_keypress)

    app._hotkeys_registered = True
