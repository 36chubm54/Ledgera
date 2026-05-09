from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gui.hotkeys import _active_tab, _focus_is_entry, _show_hotkey_help, register_hotkeys

if TYPE_CHECKING:
    pass


class _FakeNotebook:
    def __init__(self) -> None:
        self.selected: str | None = None

    def select(self, target=None):
        if target is None:
            return self.selected or ""
        self.selected = str(target)
        return self.selected


class _FakeApp:
    def __init__(self) -> None:
        self._notebook = _FakeNotebook()
        self._tab_order = [
            "infographics",
            "operations",
            "reports",
            "analytics",
            "dashboard",
            "budget",
            "debts",
            "distribution",
            "settings",
        ]
        self._tab_widgets = {key: object() for key in self._tab_order}
        self._tab_keys_by_widget = {str(widget): key for key, widget in self._tab_widgets.items()}
        self._notebook.select(self._tab_widgets["infographics"])
        self._bindings: dict[str, object] = {}
        self._focus_widget: object | None = None
        self._grab_widget: object | None = None
        self._operations_bindings = SimpleNamespace(
            set_type_income=MagicMock(),
            set_type_expense=MagicMock(),
            save_record=MagicMock(),
            select_first=MagicMock(),
            select_last=MagicMock(),
            delete_selected=MagicMock(),
            delete_all=MagicMock(),
            edit_selected=MagicMock(),
            inline_editor_active=MagicMock(return_value=False),
        )
        self._reports_tab = SimpleNamespace(_on_generate=MagicMock(), _export=MagicMock())
        self._analytics_bindings = SimpleNamespace(refresh=MagicMock(), toggle_tag_mode=MagicMock())
        self._budget_bindings = SimpleNamespace(add_budget=MagicMock(), delete_budget=MagicMock())
        self._debt_bindings = SimpleNamespace(
            pay_debt=MagicMock(),
            write_off_debt=MagicMock(),
            delete_debt=MagicMock(),
        )
        self._refresh_list = MagicMock()
        self._refresh_charts = MagicMock()
        self._refresh_budgets = MagicMock()
        self._refresh_all = MagicMock()
        self._shell: object = self
        self._grab_widget = None

    def bind_all(self, sequence: str, handler, add: str | None = None) -> None:
        self._bindings[sequence] = handler

    def focus_get(self) -> object | None:
        return self._focus_widget

    def winfo_toplevel(self):
        return self._shell

    def grab_current(self):
        return self._grab_widget


def _make_app() -> _FakeApp:
    return _FakeApp()


def _trigger_global_binding(app: _FakeApp, sequence: str, event: object | None = None) -> None:
    handler = app._bindings.get(sequence)
    assert callable(handler)
    handler(event)


def _key_event(
    *, keysym: str = "", char: str = "", keycode: int = 0, state: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(keysym=keysym, char=char, keycode=keycode, state=state)


def test_active_tab_returns_selected_tab_key() -> None:
    app = _make_app()
    app._notebook.select(app._tab_widgets["reports"])
    assert _active_tab(app) == "reports"


def test_focus_is_entry_recognizes_input_widgets() -> None:
    try:
        app = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk runtime unavailable for focus test: {exc}")
    app.withdraw()
    try:
        entry = ttk.Entry(app)
        combo = ttk.Combobox(app)
        button = ttk.Button(app)

        app.focus_get = lambda: entry
        assert _focus_is_entry(app) is True

        app.focus_get = lambda: combo
        assert _focus_is_entry(app) is True

        app.focus_get = lambda: button
        assert _focus_is_entry(app) is False
    finally:
        app.destroy()


def test_alt_binding_switches_tabs() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._notebook.select(app._tab_widgets["infographics"])
    _trigger_global_binding(app, "<Alt-Key-3>")
    assert _active_tab(app) == "reports"


def test_f5_calls_all_refresh_hooks() -> None:
    app = _make_app()
    register_hotkeys(app)
    _trigger_global_binding(app, "<F5>")
    app._refresh_list.assert_called_once()
    app._refresh_charts.assert_called_once()
    app._refresh_budgets.assert_called_once()
    app._refresh_all.assert_called_once()


def test_ctrl_i_runs_only_on_operations_tab_without_text_focus() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._focus_widget = object()
    app._notebook.select(app._tab_widgets["operations"])
    _trigger_global_binding(
        app, "<Control-KeyPress>", _key_event(keysym="i", char="i", keycode=73, state=0x0004)
    )
    app._operations_bindings.set_type_income.assert_called_once()


def test_ctrl_i_works_with_russian_layout_letter() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._focus_widget = object()
    app._notebook.select(app._tab_widgets["operations"])
    _trigger_global_binding(
        app,
        "<Control-KeyPress>",
        _key_event(keysym="Cyrillic_sha", char="", keycode=73, state=0x0004),
    )
    app._operations_bindings.set_type_income.assert_called_once()


def test_delete_does_not_run_when_focus_is_entry() -> None:
    root = tk.Tk()
    root.withdraw()
    app = _make_app()
    try:
        register_hotkeys(app)
        entry = ttk.Entry(root)
        app._focus_widget = entry
        app._notebook.select(app._tab_widgets["operations"])
        _trigger_global_binding(app, "<Delete>")
        app._operations_bindings.delete_selected.assert_not_called()
    finally:
        root.destroy()


def test_delete_runs_on_operations_tree_focus() -> None:
    app = _make_app()
    register_hotkeys(app)
    shell_widget = SimpleNamespace(winfo_toplevel=lambda: app)
    app._focus_widget = shell_widget
    app._notebook.select(app._tab_widgets["operations"])
    _trigger_global_binding(app, "<Delete>")
    app._operations_bindings.delete_selected.assert_called_once()


def test_home_and_end_select_first_and_last_operations_rows() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._focus_widget = SimpleNamespace(winfo_toplevel=lambda: app)
    app._notebook.select(app._tab_widgets["operations"])

    _trigger_global_binding(app, "<Home>")
    _trigger_global_binding(app, "<End>")

    app._operations_bindings.select_first.assert_called_once()
    app._operations_bindings.select_last.assert_called_once()


def test_ctrl_delete_deletes_all_operations_rows() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._focus_widget = SimpleNamespace(winfo_toplevel=lambda: app)
    app._notebook.select(app._tab_widgets["operations"])

    _trigger_global_binding(app, "<Control-Delete>")

    app._operations_bindings.delete_all.assert_called_once()


def test_register_hotkeys_is_idempotent() -> None:
    app = _make_app()
    register_hotkeys(app)
    register_hotkeys(app)
    app._focus_widget = object()
    app._notebook.select(app._tab_widgets["operations"])
    _trigger_global_binding(
        app, "<Control-KeyPress>", _key_event(keysym="i", char="i", keycode=73, state=0x0004)
    )
    app._operations_bindings.set_type_income.assert_called_once()


def test_ctrl_w_writes_off_debt_only_on_debts_tab_without_text_focus() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._focus_widget = object()
    app._notebook.select(app._tab_widgets["debts"])
    _trigger_global_binding(
        app, "<Control-KeyPress>", _key_event(keysym="w", char="w", keycode=87, state=0x0004)
    )
    app._debt_bindings.write_off_debt.assert_called_once()


def test_ctrl_r_refreshes_analytics_even_when_entry_has_focus() -> None:
    root = tk.Tk()
    root.withdraw()
    app = _make_app()
    try:
        register_hotkeys(app)
        entry = ttk.Entry(root)
        app._shell = root
        app._focus_widget = entry
        app._notebook.select(app._tab_widgets["analytics"])
        _trigger_global_binding(
            app, "<Control-KeyPress>", _key_event(keysym="r", char="r", keycode=82, state=0x0004)
        )
        app._analytics_bindings.refresh.assert_called_once()
    finally:
        root.destroy()


def test_ctrl_t_toggles_analytics_tag_mode_only_on_analytics_tab() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._focus_widget = object()

    _trigger_global_binding(
        app, "<Control-KeyPress>", _key_event(keysym="t", char="t", keycode=84, state=0x0004)
    )
    app._analytics_bindings.toggle_tag_mode.assert_not_called()

    app._notebook.select(app._tab_widgets["analytics"])
    _trigger_global_binding(
        app, "<Control-KeyPress>", _key_event(keysym="t", char="t", keycode=84, state=0x0004)
    )
    app._analytics_bindings.toggle_tag_mode.assert_called_once()


def test_ctrl_t_toggles_analytics_tag_mode_even_when_entry_has_focus() -> None:
    root = tk.Tk()
    root.withdraw()
    app = _make_app()
    try:
        register_hotkeys(app)
        entry = ttk.Entry(root)
        app._shell = root
        app._focus_widget = entry
        app._notebook.select(app._tab_widgets["analytics"])
        _trigger_global_binding(
            app, "<Control-KeyPress>", _key_event(keysym="t", char="t", keycode=84, state=0x0004)
        )
        app._analytics_bindings.toggle_tag_mode.assert_called_once()
    finally:
        root.destroy()


def test_enter_does_not_fire_when_modal_dialog_has_focus() -> None:
    root = tk.Tk()
    root.withdraw()
    app = _make_app()
    try:
        dialog = tk.Toplevel(root)
        button = ttk.Button(dialog)
        app._focus_widget = button
        app._grab_widget = dialog
        register_hotkeys(app)
        app._notebook.select(app._tab_widgets["operations"])
        _trigger_global_binding(app, "<Return>")
        app._operations_bindings.save_record.assert_not_called()
    finally:
        root.destroy()


def test_shell_operations_hotkeys_are_blocked_while_inline_editor_is_active() -> None:
    app = _make_app()
    register_hotkeys(app)
    app._operations_bindings.inline_editor_active.return_value = True
    app._focus_widget = SimpleNamespace(winfo_toplevel=lambda: app)
    app._notebook.select(app._tab_widgets["operations"])

    _trigger_global_binding(app, "<Return>")
    _trigger_global_binding(app, "<Delete>")
    _trigger_global_binding(
        app, "<Control-KeyPress>", _key_event(keysym="i", char="i", keycode=73, state=0x0004)
    )

    app._operations_bindings.save_record.assert_not_called()
    app._operations_bindings.delete_selected.assert_not_called()
    app._operations_bindings.set_type_income.assert_not_called()


def test_show_hotkey_help_populates_expected_rows() -> None:
    app = tk.Tk()
    app.withdraw()
    try:
        _show_hotkey_help(app)
        app.update()
        dialog = app._hotkey_help_dialog  # type: ignore[attr-defined]
        trees = [
            child
            for child in dialog.winfo_children()[0].winfo_children()
            if isinstance(child, ttk.Treeview)
        ]
        assert len(trees) == 1
        tree = trees[0]
        assert len(tree.get_children()) == 25
    finally:
        if getattr(app, "_hotkey_help_dialog", None) is not None:
            try:
                app._hotkey_help_dialog.destroy()  # type: ignore[attr-defined]
            except tk.TclError:
                pass
        app.destroy()
