from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import ttk
from typing import Any, cast
from unittest.mock import patch

import pytest

from app.data.records import RecordService
from app.services import CurrencyService
from app.use_cases_pkg.mandatory import ApplyMandatoryAutoPayments, CreateMandatoryExpense
from domain.records import MandatoryExpenseRecord
from gui.controllers import FinancialController
from gui.tabs.mandatory import MandatoryTabContext, build_mandatory_tab
from gui.tabs.settings import SettingsTabContext, build_settings_tab
from gui.tabs.wallet_manager import create_wallet_manager_dialog
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _find_treeview(parent: tk.Misc, *, column: str) -> ttk.Treeview:
    found: ttk.Treeview | None = None

    def _walk(node: tk.Misc) -> None:
        nonlocal found
        for child in node.winfo_children():
            if isinstance(child, ttk.Treeview) and column in child.cget("columns"):
                found = child
                return
            _walk(child)
            if found is not None:
                return

    _walk(parent)
    if found is None:
        raise AssertionError(f"Treeview with column {column!r} not found")
    return found


def _find_buttons(parent: tk.Misc, text: str) -> list[tk.Button | ttk.Button]:
    found: list[tk.Button | ttk.Button] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, (tk.Button, ttk.Button)):
                try:
                    if child.cget("text") == text:
                        found.append(child)
                except Exception:
                    pass
            _walk(child)

    _walk(parent)
    return found


def _find_labels(parent: tk.Misc, text: str) -> list[tk.Label | ttk.Label]:
    found: list[tk.Label | ttk.Label] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, (tk.Label, ttk.Label)):
                try:
                    if child.cget("text") == text:
                        found.append(child)
                except Exception:
                    pass
            _walk(child)

    _walk(parent)
    return found


def _find_entry_by_value(parent: tk.Misc, value: str) -> tk.Entry | ttk.Entry:
    found: tk.Entry | ttk.Entry | None = None

    def _walk(node: tk.Misc) -> None:
        nonlocal found
        for child in node.winfo_children():
            if isinstance(child, (tk.Entry, ttk.Entry)):
                try:
                    if child.get() == value:
                        found = child
                        return
                except Exception:
                    pass
            _walk(child)
            if found is not None:
                return

    _walk(parent)
    if found is None:
        raise AssertionError(f"Entry with value {value!r} not found")
    return found


def _find_entries(parent: tk.Misc) -> list[tk.Entry | ttk.Entry]:
    found: list[tk.Entry | ttk.Entry] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, (tk.Entry, ttk.Entry)):
                found.append(child)
            _walk(child)

    _walk(parent)
    return found


def _find_entry_after_label(parent: tk.Misc, label_text: str) -> tk.Entry | ttk.Entry:
    found: tk.Entry | ttk.Entry | None = None

    def _walk(node: tk.Misc) -> None:
        nonlocal found
        for child in node.winfo_children():
            if isinstance(child, (tk.Label, ttk.Label)):
                try:
                    if child.cget("text") == label_text:
                        info = child.grid_info()
                        row = int(info["row"])
                        column = int(info["column"]) + 1
                        for sibling in child.master.winfo_children():
                            grid_info = getattr(sibling, "grid_info", None)
                            if not callable(grid_info):
                                continue
                            sibling_info = cast(dict[str, Any], grid_info())
                            sibling_row = sibling_info.get("row", -1)
                            sibling_column = sibling_info.get("column", -1)
                            if isinstance(sibling, (tk.Entry, ttk.Entry)) and (
                                (
                                    int(str(sibling_row)) == row
                                    and int(str(sibling_column)) == column
                                )
                                or (
                                    int(str(sibling_row)) == row + 1
                                    and int(str(sibling_column)) == int(info["column"])
                                )
                            ):
                                found = sibling
                                return
                except Exception:
                    pass
            _walk(child)
            if found is not None:
                return

    _walk(parent)
    if found is None:
        raise AssertionError(f"Entry after label {label_text!r} not found")
    return found


def _find_combobox_by_values(
    parent: tk.Misc,
    *,
    expected_values: tuple[str, ...],
) -> ttk.Combobox:
    found: ttk.Combobox | None = None

    def _walk(node: tk.Misc) -> None:
        nonlocal found
        for child in node.winfo_children():
            if isinstance(child, ttk.Combobox):
                values = tuple(str(item) for item in child.cget("values"))
                if values == expected_values:
                    found = child
                    return
            _walk(child)
            if found is not None:
                return

    _walk(parent)
    if found is None:
        raise AssertionError(f"Combobox with values {expected_values!r} not found")
    return found


def _find_combobox_by_text(parent: tk.Misc, value: str) -> ttk.Combobox:
    found: ttk.Combobox | None = None

    def _walk(node: tk.Misc) -> None:
        nonlocal found
        for child in node.winfo_children():
            if isinstance(child, ttk.Combobox):
                try:
                    if child.get() == value:
                        found = child
                        return
                except Exception:
                    pass
            _walk(child)
            if found is not None:
                return

    _walk(parent)
    if found is None:
        raise AssertionError(f"Combobox with text {value!r} not found")
    return found


def test_create_mandatory_without_date(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_no_date.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
        )
        expense = repo.load_mandatory_expenses()[0]
        assert expense.date == ""
        assert expense.auto_pay is False
    finally:
        repo.close()


def test_create_mandatory_with_date(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_with_date.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-03-09",
        )
        expense = repo.load_mandatory_expenses()[0]
        assert str(expense.date) == "2026-03-09"
        assert expense.auto_pay is True
    finally:
        repo.close()


def test_with_updated_amount_base_recalculates_rate() -> None:
    expense = MandatoryExpenseRecord(
        amount_original=10.0,
        currency="USD",
        rate_at_operation=500.0,
        amount_base=5000.0,
        category="Mandatory",
        description="Rent",
        period="monthly",
    )

    updated = expense.with_updated_amount_base(6000.0)

    assert updated is not expense
    assert updated.amount_base == 6000.0
    assert updated.rate_at_operation == 600.0
    assert expense.amount_base == 5000.0


def test_with_updated_date_empty_disables_auto_pay() -> None:
    expense = MandatoryExpenseRecord(
        date="2026-03-09",
        amount_original=10.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=10.0,
        category="Mandatory",
        description="Rent",
        period="monthly",
        auto_pay=True,
    )

    updated = expense.with_updated_date("")

    assert updated.date == ""
    assert updated.auto_pay is False


def test_with_updated_date_value_enables_auto_pay() -> None:
    expense = MandatoryExpenseRecord(
        amount_original=10.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=10.0,
        category="Mandatory",
        description="Rent",
        period="monthly",
    )

    updated = expense.with_updated_date("2026-03-09")

    assert str(updated.date) == "2026-03-09"
    assert updated.auto_pay is True


def test_update_mandatory_amount_base_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_amount_update.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=10.0,
            currency="USD",
            category="Mandatory",
            description="Rent",
            period="monthly",
            amount_base=5000.0,
            rate_at_operation=500.0,
        )
        expense = repo.load_mandatory_expenses()[0]
        RecordService(repo).update_mandatory_amount_base(expense.id, 6000.0)

        stored = repo.get_mandatory_expense_by_id(expense.id)
        assert stored.amount_base == 6000.0
        assert stored.rate_at_operation == 600.0
    finally:
        repo.close()


def test_update_mandatory_date_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_date_update.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
        )
        expense = repo.load_mandatory_expenses()[0]
        RecordService(repo).update_mandatory_date(expense.id, "2026-03-09")

        stored = repo.get_mandatory_expense_by_id(expense.id)
        assert str(stored.date) == "2026-03-09"
        assert stored.auto_pay is True
    finally:
        repo.close()


def test_update_mandatory_amount_base_negative_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_amount_invalid.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
        )
        expense = repo.load_mandatory_expenses()[0]
        with pytest.raises(ValueError):
            RecordService(repo).update_mandatory_amount_base(expense.id, -1.0)
    finally:
        repo.close()


def test_update_mandatory_date_invalid_format_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_date_invalid.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
        )
        expense = repo.load_mandatory_expenses()[0]
        with pytest.raises(ValueError):
            RecordService(repo).update_mandatory_date(expense.id, "09-03-2026")
    finally:
        repo.close()


def test_update_mandatory_wallet_and_period_persist(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_wallet_period_update.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        repo.save_initial_balance(0.0)
        repo.create_wallet(name="Cash", currency="KZT", initial_balance=0.0)
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            wallet_id=1,
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-03-09",
        )
        expense = repo.load_mandatory_expenses()[0]

        RecordService(repo).update_mandatory_wallet_id(expense.id, 2)
        RecordService(repo).update_mandatory_period(expense.id, "weekly")

        stored = repo.get_mandatory_expense_by_id(expense.id)
        assert int(stored.wallet_id) == 2
        assert str(stored.period) == "weekly"
        assert stored.auto_pay is True
    finally:
        repo.close()


def test_audit_reports_14_checks_on_clean_db(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_audit.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        controller = FinancialController(repo, CurrencyService(use_online=False))
        report = controller.run_audit()
        assert len(report.findings) == 15
        assert len(report.passed) == 14
    finally:
        repo.close()


def test_settings_tab_builds_with_current_treeview_anchors(tmp_path: Path) -> None:
    db_path = tmp_path / "settings_build.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        controller = FinancialController(repo, CurrencyService(use_online=False))
        controller.create_wallet(
            name="Cash",
            currency="KZT",
            initial_balance=0.0,
            allow_negative=False,
        )
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            SettingsTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )

        build_settings_tab(parent, context)
        root.update_idletasks()
        manage_buttons = _find_buttons(parent, "Управление кошельками...")
        assert manage_buttons
    finally:
        root.destroy()
        repo.close()


def test_settings_tab_currency_section_saves_runtime_config(tmp_path: Path) -> None:
    db_path = tmp_path / "settings_currency.db"
    config_path = tmp_path / "currency_config.json"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        with patch.object(CurrencyService, "CONFIG_FILE", config_path):
            controller = FinancialController(repo, CurrencyService(use_online=False))
            calls: list[dict[str, object]] = []
            original_update = controller.update_runtime_currency_config

            def _capture_update(**kwargs: object) -> None:
                calls.append(dict(kwargs))
                original_update(
                    display_currency=str(kwargs["display_currency"]),
                    provider_mode=str(kwargs["provider_mode"]),
                    primary_provider=str(kwargs["primary_provider"]),
                    fallback_provider=str(kwargs["fallback_provider"]),
                    exchange_rate_api_key=str(kwargs["exchange_rate_api_key"]),
                    auto_update=bool(kwargs["auto_update"]),
                    update_interval_minutes=str(kwargs["update_interval_minutes"]),
                )

            controller.update_runtime_currency_config = _capture_update  # type: ignore[method-assign]
            parent = tk.Frame(root)
            parent.pack()
            context = cast(
                SettingsTabContext,
                type(
                    "Ctx",
                    (),
                    {
                        "controller": controller,
                        "repository": repo,
                        "refresh_operation_wallet_menu": None,
                        "refresh_transfer_wallet_menus": None,
                        "refresh_wallets": None,
                        "_refresh_list": lambda self: None,
                        "_refresh_charts": lambda self: None,
                        "_refresh_budgets": lambda self: None,
                        "_refresh_all": lambda self: None,
                        "_run_background": lambda self, task, **kwargs: kwargs.get(
                            "on_success", lambda *_: None
                        )(task()),
                    },
                )(),
            )

            build_settings_tab(parent, context)
            root.update()

            base_currency_labels = _find_labels(parent, "KZT")
            assert base_currency_labels
            assert _find_labels(parent, "ⓘ")
            assert not _find_labels(
                parent,
                "Базовая валюта доступна только при первом запуске приложения.",
            )

            display_combo = _find_combobox_by_values(
                parent,
                expected_values=("EUR", "KZT", "RUB", "USD"),
            )
            provider_mode_combo = _find_combobox_by_values(
                parent,
                expected_values=("personal", "commercial"),
            )

            display_combo.set("USD")
            provider_mode_combo.set("commercial")
            root.update()

            with (
                patch("gui.tabs.settings.messagebox.showerror"),
                patch("gui.tabs.settings.messagebox.showinfo"),
            ):
                save_buttons = _find_buttons(parent, "Сохранить")
                assert save_buttons
                save_buttons[0].invoke()
                root.update()

            assert calls
            assert calls[-1]["display_currency"] == "USD"
            assert calls[-1]["provider_mode"] == "commercial"
            assert calls[-1]["update_interval_minutes"] == "60"
            saved = CurrencyService.load_config_payload(
                config_file=config_path,
                use_env_override=False,
            )
            assert saved["display_currency"] == "USD"
            assert saved["provider_mode"] == "commercial"
            assert saved["update_interval_minutes"] == 60
    finally:
        root.destroy()
        repo.close()


def test_settings_tab_attaches_linux_popup_support_to_currency_combos(tmp_path: Path) -> None:
    db_path = tmp_path / "settings_currency_wayland.db"
    config_path = tmp_path / "currency_config.json"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        with patch.object(CurrencyService, "CONFIG_FILE", config_path):
            controller = FinancialController(repo, CurrencyService(use_online=False))
            parent = tk.Frame(root)
            parent.pack()
            context = cast(
                SettingsTabContext,
                type(
                    "Ctx",
                    (),
                    {
                        "controller": controller,
                        "repository": repo,
                        "refresh_operation_wallet_menu": None,
                        "refresh_transfer_wallet_menus": None,
                        "refresh_wallets": None,
                        "_refresh_list": lambda self: None,
                        "_refresh_charts": lambda self: None,
                        "_refresh_budgets": lambda self: None,
                        "_refresh_all": lambda self: None,
                        "_run_background": lambda self, task, **kwargs: kwargs.get(
                            "on_success", lambda *_: None
                        )(task()),
                    },
                )(),
            )

            with patch(
                "gui.tabs.settings.currency_section.enable_wayland_combobox_support",
                wraps=lambda widget: setattr(widget, "_compat_attached", True),
            ) as wrapped:
                build_settings_tab(parent, context)

            assert wrapped.call_count >= 4

            attached_combos: list[ttk.Combobox] = []

            def _walk(node: tk.Misc) -> None:
                for child in node.winfo_children():
                    if isinstance(child, ttk.Combobox) and getattr(
                        child, "_compat_attached", False
                    ):
                        attached_combos.append(child)
                    _walk(child)

            _walk(parent)
            assert attached_combos
    finally:
        root.destroy()
        repo.close()


def test_settings_tab_wallet_opener_invokes_wallet_manager(tmp_path: Path) -> None:
    db_path = tmp_path / "settings_wallet_opener.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        controller = FinancialController(repo, CurrencyService(use_online=False))
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            SettingsTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )
        build_settings_tab(parent, context)
        root.update()

        with patch("gui.tabs.settings.show_wallet_manager_dialog") as open_dialog:
            manage_buttons = _find_buttons(parent, "Управление кошельками...")
            assert manage_buttons
            manage_buttons[0].invoke()
            root.update()

        open_dialog.assert_called_once()
    finally:
        root.destroy()
        repo.close()


def test_wallet_manager_dialog_builds_and_handles_wallet_crud(tmp_path: Path) -> None:
    db_path = tmp_path / "wallet_manager_dialog.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        controller = FinancialController(repo, CurrencyService(use_online=False))
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            SettingsTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )

        build_settings_tab(parent, context)
        root.update()

        dialog = create_wallet_manager_dialog(parent, context=context, base_currency_code="KZT")
        root.update()

        assert isinstance(dialog, tk.Toplevel)
        assert bool(dialog.winfo_exists())
        wallet_tree = _find_treeview(dialog, column="allow_negative")

        name_entry = _find_entry_by_value(dialog, "")
        currency_entry = _find_entry_by_value(dialog, "KZT")
        initial_entry = _find_entry_by_value(dialog, "0")

        name_entry.insert(0, "Reserve")
        currency_entry.delete(0, tk.END)
        currency_entry.insert(0, "USD")
        initial_entry.delete(0, tk.END)
        initial_entry.insert(0, "0")

        with (
            patch("gui.tabs.wallet_manager.messagebox.showerror"),
            patch("gui.tabs.wallet_manager.messagebox.showinfo"),
        ):
            create_buttons = _find_buttons(dialog, "Создать кошелек")
            assert create_buttons
            create_buttons[0].invoke()
            root.update()

        values_after_create = [
            tuple(wallet_tree.item(iid, "values")) for iid in wallet_tree.get_children()
        ]
        assert any(row[1] == "Reserve" and row[2] == "USD" for row in values_after_create)

        controller.create_wallet(
            name="Spare",
            currency="EUR",
            initial_balance=10.0,
            allow_negative=False,
        )
        refresh_buttons = _find_buttons(dialog, "Обновить")
        assert refresh_buttons
        refresh_buttons[0].invoke()
        root.update()
        values_after_refresh = [
            tuple(wallet_tree.item(iid, "values")) for iid in wallet_tree.get_children()
        ]
        assert any(row[1] == "Spare" and row[2] == "EUR" for row in values_after_refresh)

        reserve_iid = next(
            iid
            for iid in wallet_tree.get_children()
            if wallet_tree.item(iid, "values")[1] == "Reserve"
        )
        wallet_tree.selection_set(reserve_iid)

        with (
            patch("gui.tabs.wallet_manager.messagebox.showerror"),
            patch("gui.tabs.wallet_manager.messagebox.showinfo"),
        ):
            delete_buttons = _find_buttons(dialog, "Удалить кошелек")
            assert delete_buttons
            delete_buttons[0].invoke()
            root.update()

        assert not any(
            wallet.name == "Reserve" and wallet.is_active for wallet in controller.load_wallets()
        )

        dialog.destroy()
        root.update()
    finally:
        root.destroy()
        repo.close()


def test_mandatory_tab_edit_accepts_grouped_amount_input(tmp_path: Path) -> None:
    db_path = tmp_path / "settings_mandatory_edit.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        repo.save_initial_balance(0.0)
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            wallet_id=1,
            category="Mandatory",
            description="Rent",
            period="monthly",
            amount_base=5000.0,
            rate_at_operation=50.0,
        )
        controller = FinancialController(repo, CurrencyService(use_online=False))
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            MandatoryTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "refresh_mandatory": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )

        build_mandatory_tab(parent, context, {"CSV": {"ext": ".csv", "desc": "CSV"}})
        root.update()

        mand_tree = _find_treeview(parent, column="autopay")
        mand_tree.selection_set("0")

        with (
            patch("gui.tabs.mandatory.messagebox.showerror"),
            patch("gui.tabs.mandatory.messagebox.showinfo"),
        ):
            edit_buttons = _find_buttons(parent, "Редактировать")
            assert edit_buttons
            edit_buttons[-1].invoke()
            root.update()

            amount_entry = _find_entry_by_value(parent, "5000.0")
            amount_entry.delete(0, tk.END)
            amount_entry.insert(0, "15,000")

            save_buttons = _find_buttons(parent, "Сохранить")
            assert save_buttons
            save_buttons[-1].invoke()
            root.update()

        stored = repo.load_mandatory_expenses()[0]
        assert stored.amount_base == 15000.0
    finally:
        root.destroy()
        repo.close()


def test_mandatory_tab_create_form_adds_expense(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_create_form.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        repo.save_initial_balance(0.0)
        controller = FinancialController(repo, CurrencyService(use_online=False))
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            MandatoryTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "refresh_mandatory": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )

        build_mandatory_tab(parent, context, {"CSV": {"ext": ".csv", "desc": "CSV"}})
        root.update()

        amount_entry = _find_entry_after_label(parent, "Сумма:")
        description_entry = _find_entry_after_label(parent, "Описание:")
        amount_entry.insert(0, "12,500")
        description_entry.insert(0, "Internet")

        with (
            patch("gui.tabs.mandatory.messagebox.showerror"),
            patch("gui.tabs.mandatory.messagebox.showinfo"),
        ):
            create_buttons = _find_buttons(parent, "Создать обязательный расход")
            assert create_buttons
            create_buttons[0].invoke()
            root.update()

        stored = repo.load_mandatory_expenses()
        assert len(stored) == 1
        assert stored[0].amount_original == 12500.0
        assert stored[0].description == "Internet"
    finally:
        root.destroy()
        repo.close()


def test_mandatory_tab_forms_have_keyboard_navigation(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_keyboard_nav.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        repo.save_initial_balance(0.0)
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            wallet_id=1,
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-03-09",
        )
        controller = FinancialController(repo, CurrencyService(use_online=False))
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            MandatoryTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "refresh_mandatory": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )

        build_mandatory_tab(parent, context, {"CSV": {"ext": ".csv", "desc": "CSV"}})
        root.update()

        amount_entry = _find_entry_after_label(parent, "Сумма:")
        period_combo = _find_combobox_by_values(
            parent,
            expected_values=("daily", "weekly", "monthly", "yearly"),
        )
        date_entry = _find_entry_after_label(parent, "Дата (необязательно):")
        create_button = _find_buttons(parent, "Создать обязательный расход")[0]

        assert amount_entry.bind("<Up>")
        assert period_combo.bind("<Return>")
        assert date_entry.bind("<Down>")
        assert create_button.bind("<Return>")

        mand_tree = _find_treeview(parent, column="autopay")
        mand_tree.selection_set("0")
        _find_buttons(parent, "Редактировать")[-1].invoke()
        root.update()

        edit_amount_entry = _find_entry_by_value(parent, "100.0")
        save_button = _find_buttons(parent, "Сохранить")[-1]
        cancel_button = _find_buttons(parent, "Отмена")[-1]

        assert edit_amount_entry.bind("<Escape>")
        assert edit_amount_entry.bind("<Return>")
        assert save_button.bind("<Left>")
        assert save_button.bind("<Right>")
        assert cancel_button.bind("<Escape>")

        cancel_button.invoke()
        root.update()

        _find_buttons(parent, "Добавить в записи")[-1].invoke()
        root.update()

        report_date_entry = _find_entry_after_label(parent, "Дата (YYYY-MM-DD):")
        report_wallet_combo = _find_combobox_by_text(parent, "[1] Main wallet (KZT)")
        save_button = _find_buttons(parent, "Сохранить")[-1]
        cancel_button = _find_buttons(parent, "Отмена")[-1]

        assert report_date_entry.bind("<Escape>")
        assert report_wallet_combo.bind("<Return>")
        assert save_button.bind("<Left>")
        assert cancel_button.bind("<Right>")
    finally:
        root.destroy()
        repo.close()


def test_mandatory_tab_active_fields_bind_enter_and_escape(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_keyboard_bindings.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    root = tk.Tk()
    root.withdraw()
    try:
        repo.save_initial_balance(0.0)
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            wallet_id=1,
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-03-09",
        )
        controller = FinancialController(repo, CurrencyService(use_online=False))
        parent = tk.Frame(root)
        parent.pack()
        context = cast(
            MandatoryTabContext,
            type(
                "Ctx",
                (),
                {
                    "controller": controller,
                    "repository": repo,
                    "refresh_operation_wallet_menu": None,
                    "refresh_transfer_wallet_menus": None,
                    "refresh_wallets": None,
                    "refresh_mandatory": None,
                    "_refresh_list": lambda self: None,
                    "_refresh_charts": lambda self: None,
                    "_refresh_budgets": lambda self: None,
                    "_refresh_all": lambda self: None,
                    "_run_background": lambda self, task, **kwargs: kwargs.get(
                        "on_success", lambda *_: None
                    )(task()),
                },
            )(),
        )

        build_mandatory_tab(parent, context, {"CSV": {"ext": ".csv", "desc": "CSV"}})
        root.update()

        amount_entry = _find_entry_after_label(parent, "Сумма:")
        description_entry = _find_entry_after_label(parent, "Описание:")
        assert amount_entry.bind("<Return>")
        assert amount_entry.bind("<KP_Enter>")
        assert description_entry.bind("<Return>")
        assert description_entry.bind("<KP_Enter>")

        mand_tree = _find_treeview(parent, column="autopay")
        mand_tree.selection_set("0")
        _find_buttons(parent, "Редактировать")[-1].invoke()
        root.update()

        edit_amount_entry = _find_entry_by_value(parent, "100.0")
        assert edit_amount_entry.bind("<Return>")
        assert edit_amount_entry.bind("<KP_Enter>")
        assert edit_amount_entry.bind("<Escape>")
    finally:
        root.destroy()
        repo.close()


def test_auto_pay_creates_monthly_record_once(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_autopay_once.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-01-15",
        )

        created_records = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 20))
        created_again = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 20))

        records = repo.load_all()
        mandatory_records = [
            record for record in records if isinstance(record, MandatoryExpenseRecord)
        ]
        assert len(created_records) == 1
        assert len(created_again) == 0
        assert len(mandatory_records) == 1
        assert str(mandatory_records[0].date) == "2026-03-15"
    finally:
        repo.close()


def test_auto_pay_skips_before_due_day(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_autopay_skip.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-01-25",
        )

        created_records = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 20))

        assert len(created_records) == 0
        assert repo.load_all() == []
    finally:
        repo.close()


def test_auto_pay_clamps_to_last_day_of_month(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_autopay_clamp.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=100.0,
            currency="KZT",
            category="Mandatory",
            description="Rent",
            period="monthly",
            date="2026-01-31",
        )

        created_records = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 2, 28))

        mandatory_records = [
            record for record in repo.load_all() if isinstance(record, MandatoryExpenseRecord)
        ]
        assert len(created_records) == 1
        assert str(mandatory_records[0].date) == "2026-02-28"
    finally:
        repo.close()


def test_auto_pay_creates_daily_record_once(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_autopay_daily.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=10.0,
            currency="KZT",
            category="Mandatory",
            description="Daily",
            period="daily",
            date="2026-03-01",
        )

        created_records = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 20))
        created_again = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 20))

        mandatory_records = [
            record for record in repo.load_all() if isinstance(record, MandatoryExpenseRecord)
        ]
        assert len(created_records) == 1
        assert len(created_again) == 0
        assert len(mandatory_records) == 1
        assert str(mandatory_records[0].date) == "2026-03-20"
    finally:
        repo.close()


def test_auto_pay_creates_weekly_record_on_anchor_weekday(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_autopay_weekly.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        # Anchor date is Monday (2026-03-02). For 2026-03-14 (Saturday),
        # the due date for that week is 2026-03-09 (Monday).
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=10.0,
            currency="KZT",
            category="Mandatory",
            description="Weekly",
            period="weekly",
            date="2026-03-02",
        )

        created_records = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 14))

        mandatory_records = [
            record for record in repo.load_all() if isinstance(record, MandatoryExpenseRecord)
        ]
        assert len(created_records) == 1
        assert len(mandatory_records) == 1
        assert str(mandatory_records[0].date) == "2026-03-09"
    finally:
        repo.close()


def test_auto_pay_creates_yearly_record_once(tmp_path: Path) -> None:
    db_path = tmp_path / "mandatory_autopay_yearly.db"
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        CreateMandatoryExpense(repo, CurrencyService(use_online=False)).execute(
            amount=10.0,
            currency="KZT",
            category="Mandatory",
            description="Yearly",
            period="yearly",
            date="2024-06-15",
        )

        created_early = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 3, 20))
        created_records = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 6, 20))
        created_again = ApplyMandatoryAutoPayments(repo).execute(today=date(2026, 6, 20))

        mandatory_records = [
            record for record in repo.load_all() if isinstance(record, MandatoryExpenseRecord)
        ]
        assert len(created_early) == 0
        assert len(created_records) == 1
        assert len(created_again) == 0
        assert len(mandatory_records) == 1
        assert str(mandatory_records[0].date) == "2026-06-15"
    finally:
        repo.close()
