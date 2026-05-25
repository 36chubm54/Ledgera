from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from gui.tabs.operations import OperationsTabContext, build_operations_tab
from gui.tabs.operations.core.contracts import OperationsRepository


def _find_button(parent: tk.Misc, text: str) -> tk.Button | ttk.Button | None:
    for child in parent.winfo_children():
        if isinstance(child, (tk.Button, ttk.Button)):
            try:
                if child.cget("text") == text:
                    return child
            except Exception:
                pass
        nested = _find_button(child, text)
        if nested is not None:
            return nested
    return None


def _collect_combos(parent: tk.Misc) -> list[ttk.Combobox]:
    combos: list[ttk.Combobox] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, ttk.Combobox):
                combos.append(child)
            _walk(child)

    _walk(parent)
    return combos


def _find_combo_by_values(parent: tk.Misc, expected_values: tuple[str, ...]) -> ttk.Combobox | None:
    for combo in _collect_combos(parent):
        if tuple(combo.cget("values")) == expected_values:
            return combo
    return None


def _collect_entries(parent: tk.Misc) -> list[tk.Entry | ttk.Entry]:
    entries: list[tk.Entry | ttk.Entry] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, (tk.Entry, ttk.Entry)) and not isinstance(child, ttk.Combobox):
                entries.append(child)
            _walk(child)

    _walk(parent)
    return entries


def _make_context() -> OperationsTabContext:
    wallets = [
        SimpleNamespace(id=1, name="Main", currency="KZT"),
        SimpleNamespace(id=2, name="Cash", currency="USD"),
    ]
    controller = SimpleNamespace(
        load_active_wallets=MagicMock(return_value=wallets),
        get_income_categories=MagicMock(return_value=["Salary"]),
        get_expense_categories=MagicMock(return_value=["Food"]),
        create_income=MagicMock(),
        create_expense=MagicMock(),
        create_transfer=MagicMock(return_value=123),
    )
    context = MagicMock(spec=OperationsTabContext)
    context.controller = controller
    context.repository = SimpleNamespace(
        load_all=MagicMock(return_value=[]), load_transfers=MagicMock(return_value=[])
    )
    context._record_id_to_repo_index = {}
    context._record_id_to_domain_id = {}
    context._refresh_list = MagicMock()
    context._refresh_charts = MagicMock()
    context._refresh_wallets = MagicMock()
    context._refresh_budgets = MagicMock()
    context._refresh_all = MagicMock()
    context._run_background = MagicMock()
    context._import_policy_from_ui = MagicMock(return_value=None)
    return context


def test_operations_creator_frames_have_keyboard_navigation() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = tk.Frame(root)
        parent.pack()
        context = _make_context()
        build_operations_tab(
            parent, context, import_formats={"CSV": {"ext": ".csv", "desc": "CSV"}}
        )
        root.update_idletasks()

        combos = _collect_combos(parent)
        entries = _collect_entries(parent)
        save_button = _find_button(parent, "Сохранить")
        transfer_button = _find_button(parent, "Создать перевод")

        assert len(combos) >= 5
        assert len(entries) >= 8
        assert save_button is not None
        assert transfer_button is not None

        date_entry = entries[0]
        description_entry = entries[3]
        transfer_date_entry = entries[4]
        transfer_description_entry = entries[9]

        assert date_entry.bind("<Up>")
        assert description_entry.bind("<Down>")
        assert save_button.bind("<Return>")
        assert save_button.bind("<Left>")
        assert save_button.bind("<Right>")

        assert transfer_date_entry.bind("<Down>")
        assert transfer_date_entry.bind("<Up>")
        assert transfer_description_entry.bind("<Down>")
        assert transfer_button.bind("<Return>")
        assert transfer_button.bind("<Left>")
        assert transfer_button.bind("<Right>")
    finally:
        root.destroy()


def test_operations_format_selector_excludes_unsupported_export_formats() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = tk.Frame(root)
        parent.pack()
        context = _make_context()
        build_operations_tab(
            parent,
            context,
            import_formats={
                "CSV": {"ext": ".csv", "desc": "CSV"},
                "XLSX": {"ext": ".xlsx", "desc": "Excel"},
                "JSON": {"ext": ".json", "desc": "JSON"},
            },
        )
        root.update_idletasks()

        format_combo = _find_combo_by_values(parent, ("CSV", "XLSX"))

        assert format_combo is not None
        assert tuple(format_combo.cget("values")) == ("CSV", "XLSX")
    finally:
        root.destroy()


def test_operations_export_defers_repository_loads_to_background_task() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = tk.Frame(root)
        parent.pack()
        context = _make_context()
        run_background_mock = MagicMock()
        load_all_mock = MagicMock(return_value=[])
        load_transfers_mock = MagicMock(return_value=[])
        context._run_background = run_background_mock
        context.repository = cast(
            OperationsRepository,
            SimpleNamespace(
                load_all=load_all_mock,
                load_transfers=load_transfers_mock,
            ),
        )
        build_operations_tab(
            parent,
            context,
            import_formats={
                "CSV": {"ext": ".csv", "desc": "CSV"},
                "XLSX": {"ext": ".xlsx", "desc": "Excel"},
            },
        )
        root.update_idletasks()

        export_button = _find_button(parent, "Экспорт")
        assert export_button is not None

        with patch(
            "gui.tabs.operations.core.builder.filedialog.asksaveasfilename",
            return_value="C:\\temp\\records.csv",
        ):
            export_button.invoke()

        load_all_mock.assert_not_called()
        load_transfers_mock.assert_not_called()
        run_background_mock.assert_called_once()

        task = run_background_mock.call_args.args[0]
        assert callable(task)
    finally:
        root.destroy()
