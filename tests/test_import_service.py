import logging
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.finance_service import ImportCapabilities
from app.services import CurrencyService
from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord
from domain.transfers import Transfer
from domain.wallets import Wallet
from gui.controller_import_support import normalize_operation_ids_for_import, run_import_transaction
from gui.controller_support import build_list_items
from gui.controllers import FinancialController
from infrastructure.repositories import JsonFileRecordRepository
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.import_parser import ParsedImportData
from services.import_service import ImportService
from tests.type_helpers import typed_repo


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _make_sqlite_controller(
    tmp_path: Path, name: str
) -> tuple[SQLiteRecordRepository, FinancialController]:
    db_path = tmp_path / name
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    return repo, FinancialController(repo, CurrencyService(use_online=False))


def _finance_mock() -> Mock:
    service = Mock()
    service.supports_bulk_import_replace = False
    service.supports_load_debts = False
    service.run_import_transaction.side_effect = lambda operation: operation()
    service.get_system_initial_balance.return_value = 0.0
    service.get_currency_rate.return_value = 1.0
    service.get_import_capabilities.side_effect = lambda: ImportCapabilities(
        supports_bulk_replace=bool(getattr(service, "supports_bulk_import_replace", False)),
        supports_distribution_snapshots_replace=True,
        supports_assets_replace=True,
        supports_goals_replace=True,
        supports_budgets_replace=True,
        supports_distribution_structure_replace=True,
        supports_load_debts=bool(getattr(service, "supports_load_debts", False)),
    )
    service.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True),
        Wallet(id=2, name="Cash", currency="KZT", initial_balance=0.0),
    ]
    service.load_debts.return_value = []
    return service


def test_import_service_groups_two_transfer_records_into_single_transfer() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            },
            {
                "date": "2026-01-02",
                "type": "expense",
                "wallet_id": "1",
                "transfer_id": "55",
                "category": "Transfer",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
            },
            {
                "date": "2026-01-02",
                "type": "income",
                "wallet_id": "2",
                "transfer_id": "55",
                "category": "Transfer",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=3, skipped=0, errors=tuple())
    finance_service.reset_operations_for_import.assert_called_once_with(initial_balance=0.0)
    finance_service.create_income.assert_called_once()
    finance_service.create_transfer.assert_called_once()
    finance_service.create_expense.assert_not_called()


def test_import_service_csv_never_uses_bulk_replace_even_if_supported() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.replace_all_for_import.assert_not_called()
    finance_service.reset_operations_for_import.assert_called_once_with(initial_balance=0.0)
    finance_service.create_income.assert_called_once()


def test_import_service_csv_preserves_related_debt_id_in_created_records() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "id": "10",
                "date": "2026-01-01",
                "type": "expense",
                "wallet_id": "1",
                "related_debt_id": "1",
                "category": "Debt payment",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.create_expense.call_args.kwargs
    assert kwargs["related_debt_id"] == 1


def test_import_service_csv_preserves_tags_in_created_records() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
                "tags": "#work, #bonus",
            },
            {
                "date": "2026-01-02",
                "type": "expense",
                "wallet_id": "1",
                "category": "Food",
                "amount_original": "25",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "25",
                "tags": "#food",
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=2, skipped=0, errors=tuple())
    assert finance_service.create_income.call_args.kwargs["tags"] == ("work", "bonus")
    assert finance_service.create_expense.call_args.kwargs["tags"] == ("food",)


def test_import_service_json_without_sections_preserves_debts_and_assets() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    payload = ParsedImportData(
        path="data.json",
        file_type="json",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            }
        ],
        json_sections_present=frozenset({"records"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert kwargs["debts"] is None
    assert kwargs["debt_payments"] is None
    assert kwargs["assets"] is None
    assert kwargs["asset_snapshots"] is None
    assert kwargs["goals"] is None
    finance_service.replace_assets.assert_not_called()
    finance_service.replace_goals.assert_not_called()
    finance_service.replace_budgets.assert_not_called()
    finance_service.replace_distribution_structure.assert_not_called()
    finance_service.replace_distribution_snapshots.assert_not_called()


def test_import_service_records_only_json_preserves_related_debt_links() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.get_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-01-01",
        )
    ]
    payload = ParsedImportData(
        path="data.json",
        file_type="json",
        rows=[
            {
                "id": "10",
                "date": "2026-01-01",
                "type": "expense",
                "wallet_id": "1",
                "related_debt_id": "1",
                "category": "Debt payment",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            }
        ],
        json_sections_present=frozenset({"records"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert kwargs["records"][0].related_debt_id == 1
    assert kwargs["debts"] is None
    assert kwargs["debt_payments"] is None


def test_import_service_json_without_section_metadata_uses_payload_fallback(caplog) -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    caplog.set_level("WARNING")
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        assets=[
            {
                "id": 1,
                "name": "Deposit",
                "category": "bank",
                "currency": "KZT",
                "is_active": True,
                "created_at": "2026-04-05",
            }
        ],
        asset_snapshots=[
            {
                "id": 1,
                "asset_id": 1,
                "snapshot_date": "2026-04-05",
                "value_minor": 500000,
                "currency": "KZT",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert len(kwargs["assets"]) == 1
    assert len(kwargs["asset_snapshots"]) == 1
    assert "fallback detection from payload" in caplog.text


def test_import_service_preserves_original_row_order_without_type_sorting() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[
            {
                "date": "2026-01-03",
                "type": "expense",
                "wallet_id": "1",
                "category": "Food",
                "amount_original": "15",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "15",
            },
            {
                "date": "2026-01-03",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            },
            {
                "date": "2026-01-03",
                "type": "expense",
                "wallet_id": "1",
                "transfer_id": "55",
                "category": "Transfer",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
            },
            {
                "date": "2026-01-03",
                "type": "income",
                "wallet_id": "2",
                "transfer_id": "55",
                "category": "Transfer",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
            },
            {
                "date": "2026-01-03",
                "type": "mandatory_expense",
                "wallet_id": "1",
                "category": "Rent",
                "amount_original": "50",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "50",
                "description": "Monthly",
                "period": "monthly",
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=5, skipped=0, errors=tuple())
    method_order = [call[0] for call in finance_service.method_calls]
    assert method_order.index("create_expense") < method_order.index("create_income")
    assert method_order.index("create_income") < method_order.index("create_transfer")
    assert method_order.index("create_transfer") < method_order.index(
        "create_mandatory_expense_record"
    )


def test_import_service_bulk_replace_preserves_original_row_order() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[
            {
                "date": "2026-01-03",
                "type": "expense",
                "wallet_id": "1",
                "category": "Food",
                "amount_original": "15",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "15",
            },
            {
                "date": "2026-01-03",
                "type": "expense",
                "wallet_id": "1",
                "transfer_id": "55",
                "category": "Transfer",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
            },
            {
                "date": "2026-01-03",
                "type": "income",
                "wallet_id": "2",
                "transfer_id": "55",
                "category": "Transfer",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
            },
            {
                "date": "2026-01-03",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=4, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    records = kwargs["records"]
    assert [record.category for record in records] == ["Food", "Transfer", "Transfer", "Salary"]
    assert [record.transfer_id for record in records] == [None, 1, 1, None]


def test_import_service_preserves_csv_transfer_row_position() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-03",
                "type": "expense",
                "wallet_id": "1",
                "category": "Food",
                "amount_original": "15",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "15",
            },
            {
                "date": "2026-01-03",
                "type": "transfer",
                "from_wallet_id": "1",
                "to_wallet_id": "2",
                "amount_original": "10",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "10",
                "description": "Move",
            },
            {
                "date": "2026-01-03",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=3, skipped=0, errors=tuple())
    method_order = [call[0] for call in finance_service.method_calls]
    assert method_order.index("create_expense") < method_order.index("create_transfer")
    assert method_order.index("create_transfer") < method_order.index("create_income")


def test_import_service_skips_missing_wallet_and_does_not_apply_changes() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "999",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(
        imported=0,
        skipped=1,
        errors=("row 2: wallet not found (999)",),
    )
    finance_service.reset_operations_for_import.assert_not_called()
    finance_service.create_income.assert_not_called()
    finance_service.create_expense.assert_not_called()
    finance_service.create_transfer.assert_not_called()


def test_import_service_mandatory_import_uses_finance_service_only() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="mandatory.csv",
        file_type="csv",
        rows=[
            {
                "type": "mandatory_expense",
                "date": "2026-03-18",
                "category": "Rent",
                "amount_original": "50",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "50",
                "description": "Monthly",
                "period": "monthly",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service).import_mandatory_file("mandatory.csv")

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.reset_mandatory_for_import.assert_called_once_with()
    finance_service.create_mandatory_expense.assert_called_once_with(
        amount=50.0,
        currency="KZT",
        wallet_id=1,
        category="Rent",
        description="Monthly",
        period="monthly",
        date="2026-03-18",
        amount_kzt=50.0,
        rate_at_operation=1.0,
    )


def test_import_service_fills_empty_mandatory_description() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "mandatory_expense",
                "wallet_id": "1",
                "category": "Rent",
                "amount_original": "50",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "50",
                "description": "",
                "period": "monthly",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.create_mandatory_expense_record.assert_called_once_with(
        date="2026-01-01",
        wallet_id=1,
        amount=50.0,
        currency="KZT",
        category="Rent",
        description="Imported Rent",
        period="monthly",
        amount_kzt=50.0,
        rate_at_operation=1.0,
    )


def test_import_service_json_backup_imports_mandatory_templates() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        mandatory_rows=[
            {
                "date": "2026-03-19",
                "category": "Subscriptions",
                "amount_original": "12",
                "currency": "USD",
                "rate_at_operation": "500",
                "amount_kzt": "6000",
                "description": "Music",
                "period": "monthly",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.reset_all_for_import.assert_called_once()
    finance_service.create_mandatory_expense.assert_called_once_with(
        amount=12.0,
        currency="USD",
        wallet_id=1,
        category="Subscriptions",
        description="Music",
        period="monthly",
        date="2026-03-19",
        amount_kzt=6000.0,
        rate_at_operation=500.0,
    )


def test_import_service_bulk_replace_preserves_mandatory_date() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        mandatory_rows=[
            {
                "date": "2026-03-20",
                "category": "Internet",
                "amount_original": "15",
                "currency": "USD",
                "rate_at_operation": "500",
                "amount_kzt": "7500",
                "description": "ISP",
                "period": "monthly",
                "type": "mandatory_expense",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    mandatory_templates = kwargs["mandatory_templates"]
    assert len(mandatory_templates) == 1
    assert str(mandatory_templates[0].date) == "2026-03-20"
    assert mandatory_templates[0].auto_pay is True


def test_import_service_json_backup_restores_distribution_structure() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        distribution_items=[
            {
                "id": 1,
                "name": "Investments",
                "group_name": "Goals",
                "sort_order": 0,
                "pct": 100.0,
                "pct_minor": 10000,
                "is_active": True,
            }
        ],
        distribution_subitems=[
            {
                "id": 10,
                "item_id": 1,
                "name": "BTC",
                "sort_order": 0,
                "pct": 100.0,
                "pct_minor": 10000,
                "is_active": True,
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    finance_service.replace_distribution_structure.assert_called_once()
    items_arg, subitems_arg = finance_service.replace_distribution_structure.call_args.args
    assert len(items_arg) == 1
    assert items_arg[0].name == "Investments"
    assert len(subitems_arg[1]) == 1
    assert subitems_arg[1][0].name == "BTC"


def test_import_service_json_backup_restores_budgets() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        budgets=[
            {
                "id": 1,
                "category": "Food",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "limit_kzt": 1500.0,
                "limit_kzt_minor": 150000,
                "include_mandatory": True,
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    finance_service.replace_budgets.assert_called_once()
    budgets_arg = finance_service.replace_budgets.call_args.args[0]
    assert len(budgets_arg) == 1
    assert budgets_arg[0].category == "Food"
    assert budgets_arg[0].include_mandatory is True


def test_import_service_json_backup_restores_assets_and_goals() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        assets=[
            {
                "id": 1,
                "name": "Deposit",
                "category": "bank",
                "currency": "KZT",
                "is_active": True,
                "created_at": "2026-04-05",
                "description": "Reserve",
            }
        ],
        asset_snapshots=[
            {
                "id": 1,
                "asset_id": 1,
                "snapshot_date": "2026-04-05",
                "value_minor": 500000,
                "currency": "KZT",
                "note": "Initial",
            }
        ],
        goals=[
            {
                "id": 1,
                "title": "Emergency Fund",
                "target_amount_minor": 1000000,
                "currency": "KZT",
                "created_at": "2026-04-05",
                "target_date": "2026-12-31",
                "is_completed": False,
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    finance_service.replace_assets.assert_called_once()
    finance_service.replace_goals.assert_called_once()
    assets_arg, snapshots_arg = finance_service.replace_assets.call_args.args
    assert len(assets_arg) == 1
    assert assets_arg[0].category is AssetCategory.BANK
    assert len(snapshots_arg) == 1
    assert snapshots_arg[0].value_minor == 500000
    goals_arg = finance_service.replace_goals.call_args.args[0]
    assert len(goals_arg) == 1
    assert goals_arg[0].title == "Emergency Fund"


def test_import_service_bulk_replace_does_not_apply_assets_and_goals_twice() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.replace_all_for_import = Mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        assets=[
            {
                "id": 1,
                "name": "Deposit",
                "category": "bank",
                "currency": "KZT",
                "is_active": True,
                "created_at": "2026-04-05",
            }
        ],
        asset_snapshots=[
            {
                "id": 1,
                "asset_id": 1,
                "snapshot_date": "2026-04-05",
                "value_minor": 500000,
                "currency": "KZT",
            }
        ],
        goals=[
            {
                "id": 1,
                "title": "Emergency Fund",
                "target_amount_minor": 1000000,
                "currency": "KZT",
                "created_at": "2026-04-05",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    finance_service.replace_all_for_import.assert_called_once()
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert len(kwargs["assets"]) == 1
    assert len(kwargs["asset_snapshots"]) == 1
    assert len(kwargs["goals"]) == 1
    finance_service.replace_assets.assert_not_called()
    finance_service.replace_goals.assert_not_called()


def test_import_service_current_rate_json_skips_orphan_asset_snapshots() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.replace_all_for_import = Mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        assets=[
            {
                "id": 1,
                "name": "Broken asset",
                "category": "invalid",
                "currency": "KZT",
                "is_active": True,
                "created_at": "2026-04-05",
            }
        ],
        asset_snapshots=[
            {
                "id": 1,
                "asset_id": 1,
                "snapshot_date": "2026-04-05",
                "value_minor": 500000,
                "currency": "KZT",
                "note": "Initial",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 10.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=10.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.CURRENT_RATE).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    finance_service.replace_all_for_import.assert_called_once()
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assets_arg = kwargs["assets"]
    snapshots_arg = kwargs["asset_snapshots"]
    assert assets_arg == []
    assert snapshots_arg == []


def test_import_service_current_rate_json_skips_orphan_debt_payments() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.replace_all_for_import = Mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[
            {
                "id": "10",
                "date": "2026-03-02",
                "type": "expense",
                "wallet_id": "1",
                "category": "Food",
                "amount_original": "25",
                "currency": "USD",
                "description": "Expense",
            }
        ],
        debt_payments=[
            {
                "id": 5,
                "debt_id": 99,
                "record_id": 10,
                "operation_type": "debt_repay",
                "principal_paid_minor": 2500,
                "is_write_off": False,
                "payment_date": "2026-03-02",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        json_sections_present=frozenset({"records", "debts", "debt_payments", "wallets"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.CURRENT_RATE).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert kwargs["debts"] == []
    assert kwargs["debt_payments"] == []


def test_import_service_current_rate_json_clears_orphan_record_debt_link() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.replace_all_for_import = Mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[
            {
                "id": "10",
                "date": "2026-03-02",
                "type": "expense",
                "wallet_id": "1",
                "related_debt_id": "99",
                "category": "Debt payment",
                "amount_original": "25",
                "currency": "USD",
                "description": "Debt payment",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        json_sections_present=frozenset({"records", "debts", "debt_payments", "wallets"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.CURRENT_RATE).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert kwargs["records"][0].related_debt_id is None


def test_import_service_current_rate_json_skips_invalid_distribution_snapshots() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.replace_all_for_import = Mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        distribution_snapshots=[
            {
                "month": "2026-13",
                "column_order": ["month", "fixed"],
                "headings_by_column": {"month": "Month"},
                "values_by_column": {"month": "2026-13"},
            },
            {
                "month": "2026-03",
                "column_order": ["month", "fixed"],
                "headings_by_column": {"month": "Month"},
                "values_by_column": {"month": "2026-03"},
            },
            {
                "month": "2026-03",
                "column_order": ["month", "fixed"],
                "headings_by_column": {"month": "Month"},
                "values_by_column": {"month": "2026-03 duplicate"},
            },
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        json_sections_present=frozenset({"records", "debts", "debt_payments", "wallets"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.CURRENT_RATE).import_file(
            "data_backup.json"
        )

    assert summary == ImportResult(imported=0, skipped=0, errors=tuple())
    finance_service.replace_distribution_snapshots.assert_called_once()
    rows_arg = finance_service.replace_distribution_snapshots.call_args.args[0]
    assert [row.month for row in rows_arg] == ["2026-03"]


def test_import_service_full_backup_rejects_duplicate_distribution_snapshot_month() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        distribution_snapshots=[
            {
                "month": "2026-03",
                "column_order": ["month"],
                "headings_by_column": {"month": "Month"},
                "values_by_column": {"month": "2026-03"},
            },
            {
                "month": "2026-03",
                "column_order": ["month"],
                "headings_by_column": {"month": "Month"},
                "values_by_column": {"month": "2026-03 duplicate"},
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        with pytest.raises(ValueError, match="Duplicate distribution snapshot month: 2026-03"):
            ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
                "data_backup.json"
            )


def test_import_service_rejects_duplicate_wallet_ids_in_payload() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            },
            {
                "id": 1,
                "name": "Duplicate",
                "currency": "USD",
                "initial_balance": 5.0,
                "system": False,
                "allow_negative": False,
                "is_active": True,
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        with pytest.raises(ValueError, match="Duplicate wallet id in import payload: 1"):
            ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
                "data_backup.json"
            )


def test_import_service_rejects_multiple_system_wallets_in_payload() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            },
            {
                "id": 2,
                "name": "Secondary system",
                "currency": "USD",
                "initial_balance": 5.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            },
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        with pytest.raises(ValueError, match="Multiple system wallets in import payload: 1, 2"):
            ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
                "data_backup.json"
            )


def test_import_service_full_backup_rejects_invalid_distribution_structure() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data_backup.json",
        file_type="json",
        rows=[],
        distribution_items=[
            {
                "id": 1,
                "name": "Investments",
                "group_name": "Goals",
                "sort_order": 0,
                "pct": 100.0,
                "pct_minor": 10000,
                "is_active": True,
            }
        ],
        distribution_subitems=[
            {
                "id": 10,
                "item_id": 999,
                "name": "BTC",
                "sort_order": 0,
                "pct": 100.0,
                "pct_minor": 10000,
                "is_active": True,
            }
        ],
        json_sections_present=frozenset({"records", "debts", "debt_payments", "wallets"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        with pytest.raises(ValueError, match="references missing item_id=999"):
            ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
                "data_backup.json"
            )


def test_import_service_full_backup_passes_fixed_rate_values() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "USD",
                "rate_at_operation": "530",
                "amount_kzt": "53000",
                "description": "Payroll",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.create_income.assert_called_once_with(
        date="2026-01-01",
        wallet_id=1,
        amount=100.0,
        currency="USD",
        category="Salary",
        description="Payroll",
        amount_kzt=53000.0,
        rate_at_operation=530.0,
    )


def test_import_service_current_rate_does_not_pass_fixed_values() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "USD",
                "description": "Payroll",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.CURRENT_RATE).import_file(
            "data.csv"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.create_income.assert_called_once()
    kwargs = finance_service.create_income.call_args.kwargs
    assert kwargs["amount_kzt"] is None
    assert kwargs["rate_at_operation"] is None


def test_import_service_reports_duplicate_initial_balance_rows() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {"type": "initial_balance", "amount_original": "100"},
            {"type": "initial_balance", "amount_original": "200"},
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv"
        )

    assert summary == ImportResult(
        imported=0,
        skipped=1,
        errors=("row 3: duplicate initial_balance row",),
    )
    finance_service.reset_operations_for_import.assert_not_called()


def test_import_service_bulk_replace_normalizes_mandatory_ids_from_one() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    finance_service.replace_all_for_import = Mock()
    payload = ParsedImportData(
        path="data.json",
        file_type="json",
        rows=[],
        mandatory_rows=[
            {
                "type": "mandatory_expense",
                "id": "50",
                "category": "Rent",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
                "description": "Monthly",
                "period": "monthly",
            },
            {
                "type": "mandatory_expense",
                "id": "77",
                "category": "Internet",
                "amount_original": "25",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "25",
                "description": "ISP",
                "period": "monthly",
            },
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        initial_balance=0.0,
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.json"
        )

    assert summary == ImportResult(imported=2, skipped=0, errors=tuple())
    finance_service.replace_all_for_import.assert_called_once()
    mandatory_templates = finance_service.replace_all_for_import.call_args.kwargs[
        "mandatory_templates"
    ]
    assert [template.id for template in mandatory_templates] == [1, 2]


def test_import_service_bulk_replace_passes_debts_and_debt_payments() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    payload = ParsedImportData(
        path="data.json",
        file_type="json",
        rows=[
            {
                "id": "10",
                "date": "2026-03-02",
                "type": "expense",
                "wallet_id": "1",
                "related_debt_id": "1",
                "category": "Debt payment",
                "amount_original": "25",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "25",
            }
        ],
        debts=[
            {
                "id": 1,
                "contact_name": "Alex",
                "kind": "debt",
                "total_amount_minor": 10000,
                "remaining_amount_minor": 7500,
                "currency": "KZT",
                "interest_rate": 0.0,
                "status": "open",
                "created_at": "2026-03-01",
                "closed_at": None,
            }
        ],
        debt_payments=[
            {
                "id": 5,
                "debt_id": 1,
                "record_id": 10,
                "operation_type": "debt_repay",
                "principal_paid_minor": 2500,
                "is_write_off": False,
                "payment_date": "2026-03-02",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        json_sections_present=frozenset({"records", "debts", "debt_payments", "wallets"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert len(kwargs["debts"]) == 1
    assert kwargs["debts"][0].kind is DebtKind.DEBT
    assert kwargs["debts"][0].status is DebtStatus.OPEN
    assert len(kwargs["debt_payments"]) == 1
    assert kwargs["debt_payments"][0].operation_type is DebtOperationType.DEBT_REPAY
    assert kwargs["records"][0].related_debt_id == 1


def test_import_service_current_rate_json_still_bulk_replaces_debts() -> None:
    finance_service = _finance_mock()
    finance_service.supports_bulk_import_replace = True
    payload = ParsedImportData(
        path="data.json",
        file_type="json",
        rows=[
            {
                "id": "10",
                "date": "2026-03-02",
                "type": "expense",
                "wallet_id": "1",
                "related_debt_id": "1",
                "category": "Debt payment",
                "amount_original": "25",
                "currency": "USD",
                "description": "Debt payment",
            }
        ],
        debts=[
            {
                "id": 1,
                "contact_name": "Alex",
                "kind": "debt",
                "total_amount_minor": 10000,
                "remaining_amount_minor": 7500,
                "currency": "KZT",
                "interest_rate": 0.0,
                "status": "open",
                "created_at": "2026-03-01",
                "closed_at": None,
            }
        ],
        debt_payments=[
            {
                "id": 5,
                "debt_id": 1,
                "record_id": 10,
                "operation_type": "debt_repay",
                "principal_paid_minor": 2500,
                "is_write_off": False,
                "payment_date": "2026-03-02",
            }
        ],
        wallets=[
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        json_sections_present=frozenset({"records", "debts", "debt_payments", "wallets"}),
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.CURRENT_RATE).import_file(
            "data.json"
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple())
    finance_service.replace_all_for_import.assert_called_once()
    kwargs = finance_service.replace_all_for_import.call_args.kwargs
    assert len(kwargs["debts"]) == 1
    assert len(kwargs["debt_payments"]) == 1
    assert kwargs["records"][0].related_debt_id == 1
    finance_service.create_income.assert_not_called()
    finance_service.create_expense.assert_not_called()


def test_import_service_passes_force_flag_to_parser() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(path="data.json", file_type="json", rows=[])

    with patch("services.import_service.parse_import_file", return_value=payload) as parse_mock:
        ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.json",
            force=True,
        )

    parse_mock.assert_called_once_with("data.json", force=True)


def test_import_service_dry_run_returns_preview_without_writing() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.csv",
        file_type="csv",
        rows=[
            {
                "date": "2026-01-01",
                "type": "income",
                "wallet_id": "1",
                "category": "Salary",
                "amount_original": "100",
                "currency": "KZT",
                "rate_at_operation": "1",
                "amount_kzt": "100",
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        summary = ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file(
            "data.csv",
            dry_run=True,
        )

    assert summary == ImportResult(imported=1, skipped=0, errors=tuple(), dry_run=True)
    finance_service.run_import_transaction.assert_not_called()
    finance_service.reset_operations_for_import.assert_not_called()
    finance_service.create_income.assert_not_called()


def test_import_service_rejects_fractional_wallet_id_in_wallet_payload() -> None:
    finance_service = _finance_mock()
    payload = ParsedImportData(
        path="data.json",
        file_type="json",
        rows=[],
        wallets=[
            {
                "id": "1.5",
                "name": "Broken",
                "currency": "KZT",
                "initial_balance": 0.0,
            }
        ],
    )

    with patch("services.import_service.parse_import_file", return_value=payload):
        with pytest.raises(ValueError, match="Invalid wallet id in import payload"):
            ImportService(finance_service, policy=ImportPolicy.FULL_BACKUP).import_file("data.json")


def test_build_list_items_uses_invariant_ids_where_transfer_counts_once() -> None:
    items = build_list_items(
        [
            ExpenseRecord(
                id=1,
                date="2026-03-05",
                wallet_id=1,
                amount_original=50.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_kzt=50.0,
                category="Food",
            ),
            ExpenseRecord(
                id=2,
                date="2026-03-01",
                wallet_id=1,
                transfer_id=7,
                amount_original=25.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_kzt=25.0,
                category="Transfer",
                description="Move",
            ),
            IncomeRecord(
                id=3,
                date="2026-03-01",
                wallet_id=2,
                transfer_id=7,
                amount_original=25.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_kzt=25.0,
                category="Transfer",
                description="Move",
            ),
            IncomeRecord(
                id=4,
                date="2026-03-10",
                wallet_id=2,
                amount_original=100.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_kzt=100.0,
                category="Salary",
            ),
        ]
    )

    assert [item.type_label for item in items] == ["Expense", "Transfer", "Income"]
    assert [item.invariant_id for item in items] == [1, 2, 3]
    assert [item.repository_index for item in items] == [0, 1, 3]


def test_normalize_operation_ids_for_import_is_deterministic_by_date_then_id() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=7,
            date="2026-03-03",
            wallet_id=1,
            transfer_id=20,
            amount_original=10.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=10.0,
            category="Transfer",
        ),
        IncomeRecord(
            id=8,
            date="2026-03-03",
            wallet_id=2,
            transfer_id=20,
            amount_original=10.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=10.0,
            category="Transfer",
        ),
        ExpenseRecord(
            id=3,
            date="2026-03-01",
            wallet_id=1,
            transfer_id=None,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Food",
        ),
    ]
    repository.load_transfers.return_value = [
        Transfer(
            id=20,
            from_wallet_id=1,
            to_wallet_id=2,
            date="2026-03-03",
            amount_original=10.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=10.0,
            description="Later",
        ),
        Transfer(
            id=10,
            from_wallet_id=1,
            to_wallet_id=3,
            date="2026-03-02",
            amount_original=7.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=7.0,
            description="Earlier",
        ),
    ]

    normalize_operation_ids_for_import(repository)

    normalized_records, normalized_transfers = (
        repository.replace_records_and_transfers.call_args.args
    )
    assert [transfer.id for transfer in normalized_transfers] == [1, 2]
    assert [transfer.description for transfer in normalized_transfers] == ["Earlier", "Later"]
    assert [record.id for record in normalized_records] == [1, 2, 3]
    assert [record.transfer_id for record in normalized_records] == [2, 2, None]


def test_normalize_operation_ids_for_import_remaps_debt_payment_record_ids() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-01",
            wallet_id=1,
            related_debt_id=1,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Debt payment",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=10,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-02",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert [record.id for record in kwargs["records"]] == [1]
    assert kwargs["debt_payments"][0].record_id == 1


def test_normalize_operation_ids_for_import_syncs_record_related_debt_id_from_payment() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-02",
            wallet_id=1,
            related_debt_id=None,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Debt payment",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=3,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=3,
            record_id=10,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-02",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert kwargs["debt_payments"][0].record_id == 1
    assert kwargs["records"][0].related_debt_id == 3


def test_normalize_operation_ids_for_import_conflicting_record_link_is_cleared(caplog) -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-02",
            wallet_id=1,
            related_debt_id=2,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Debt payment",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=2,
            contact_name="Debt-2",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        ),
        Debt(
            id=3,
            contact_name="Debt-3",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        ),
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=3,
            record_id=10,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-02",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert kwargs["debt_payments"][0].record_id is None
    assert kwargs["records"][0].related_debt_id == 2
    assert "conflicting record" in caplog.text


def test_normalize_operation_ids_for_import_restores_cleared_debt_payment_record_ids() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-01",
            wallet_id=1,
            related_debt_id=1,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Debt payment",
            description="Alex",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=None,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-01",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert [record.id for record in kwargs["records"]] == [1]
    assert kwargs["debt_payments"][0].record_id == 1


def test_normalize_operation_ids_for_import_restores_record_id_with_nonstandard_category() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-01",
            wallet_id=1,
            related_debt_id=1,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Погашение долга",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=None,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-01",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert [record.id for record in kwargs["records"]] == [1]
    assert kwargs["debt_payments"][0].record_id == 1


def test_normalize_operation_ids_for_import_restores_record_id_without_related_debt_link() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-01",
            wallet_id=1,
            related_debt_id=None,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Debt payment",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=None,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-01",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert [record.id for record in kwargs["records"]] == [1]
    assert kwargs["debt_payments"][0].record_id == 1


def test_normalize_operation_ids_for_import_restores_record_id_without_link_and_category() -> None:
    repository = Mock()
    repository.load_all.return_value = [
        ExpenseRecord(
            id=10,
            date="2026-03-01",
            wallet_id=1,
            related_debt_id=None,
            amount_original=5.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_kzt=5.0,
            category="Погашение долга",
        )
    ]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = []
    repository.load_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.DEBT,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=None,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-01",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert [record.id for record in kwargs["records"]] == [1]
    assert kwargs["debt_payments"][0].record_id == 1


def test_normalize_operation_ids_for_import_excludes_mandatory_records_from_loan_relinking() -> (
    None
):
    repository = Mock()
    mandatory_record = MandatoryExpenseRecord(
        id=10,
        wallet_id=1,
        date="2026-03-01",
        amount_original=5.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_kzt=5.0,
        category="Loan payment",
        description="Monthly charge",
        period="monthly",
        auto_pay=True,
    )
    repository.load_all.return_value = [mandatory_record]
    repository.load_transfers.return_value = []
    repository.load_wallets.return_value = [
        Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
    ]
    repository.load_mandatory_expenses.return_value = [mandatory_record]
    repository.load_debts.return_value = [
        Debt(
            id=1,
            contact_name="Alex",
            kind=DebtKind.LOAN,
            total_amount_minor=1000,
            remaining_amount_minor=500,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2026-03-01",
        )
    ]
    repository.load_debt_payments.return_value = [
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=None,
            operation_type=DebtOperationType.LOAN_COLLECT,
            principal_paid_minor=500,
            is_write_off=False,
            payment_date="2026-03-01",
        )
    ]

    normalize_operation_ids_for_import(repository)

    kwargs = repository.replace_all_data.call_args.kwargs
    assert kwargs["debt_payments"][0].record_id is None
    assert kwargs["records"][0].related_debt_id is None


def test_run_import_transaction_restores_assets_on_failure(tmp_path: Path) -> None:
    repo, controller = _make_sqlite_controller(tmp_path, "import_rollback_assets.db")
    try:
        repo.replace_all_data(
            wallets=[
                Wallet(
                    id=1,
                    name="Main",
                    currency="KZT",
                    initial_balance=0.0,
                    system=True,
                    allow_negative=False,
                    is_active=True,
                )
            ],
            records=[],
            mandatory_expenses=[],
            transfers=[],
        )
        controller.replace_assets(
            [
                Asset(
                    id=1,
                    name="Old",
                    category=AssetCategory.BANK,
                    currency="KZT",
                    is_active=True,
                    created_at="2026-04-01",
                )
            ],
            [
                AssetSnapshot(
                    id=1,
                    asset_id=1,
                    snapshot_date="2026-04-02",
                    value_minor=100,
                    currency="KZT",
                    note="",
                )
            ],
        )

        with pytest.raises(RuntimeError, match="boom"):
            controller.run_import_transaction(
                lambda: (
                    controller.replace_assets(
                        [
                            Asset(
                                id=2,
                                name="New",
                                category=AssetCategory.BANK,
                                currency="KZT",
                                is_active=True,
                                created_at="2026-04-03",
                            )
                        ],
                        [
                            AssetSnapshot(
                                id=2,
                                asset_id=2,
                                snapshot_date="2026-04-04",
                                value_minor=200,
                                currency="KZT",
                                note="",
                            )
                        ],
                    ),
                    (_ for _ in ()).throw(RuntimeError("boom")),
                )
            )

        assets = repo.load_assets()
        snapshots = repo.load_asset_snapshots()
        assert [(asset.id, asset.name) for asset in assets] == [(1, "Old")]
        assert [
            (snapshot.id, snapshot.asset_id, snapshot.value_minor) for snapshot in snapshots
        ] == [(1, 1, 100)]
    finally:
        repo.close()


def test_run_import_transaction_restores_debts_for_json_repository(tmp_path: Path) -> None:
    repo = JsonFileRecordRepository(str(tmp_path / "import_rollback.json"))
    repo.replace_all_data(
        wallets=[
            Wallet(
                id=1,
                name="Main",
                currency="KZT",
                initial_balance=0.0,
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ],
        records=[],
        mandatory_expenses=[],
        transfers=[],
        debts=[
            Debt(
                id=1,
                contact_name="Alex",
                kind=DebtKind.DEBT,
                total_amount_minor=1000,
                remaining_amount_minor=700,
                currency="KZT",
                interest_rate=0.0,
                status=DebtStatus.OPEN,
                created_at="2026-04-01",
            )
        ],
        debt_payments=[
            DebtPayment(
                id=1,
                debt_id=1,
                record_id=None,
                operation_type=DebtOperationType.DEBT_REPAY,
                principal_paid_minor=300,
                is_write_off=False,
                payment_date="2026-04-02",
            )
        ],
    )

    with pytest.raises(RuntimeError, match="boom"):
        run_import_transaction(
            typed_repo(repo),
            lambda: (
                repo.replace_all_data(
                    wallets=repo.load_wallets(),
                    records=[],
                    mandatory_expenses=[],
                    transfers=[],
                    debts=[
                        Debt(
                            id=2,
                            contact_name="New",
                            kind=DebtKind.LOAN,
                            total_amount_minor=500,
                            remaining_amount_minor=500,
                            currency="USD",
                            interest_rate=0.0,
                            status=DebtStatus.OPEN,
                            created_at="2026-04-03",
                        )
                    ],
                    debt_payments=[],
                ),
                (_ for _ in ()).throw(RuntimeError("boom")),
            ),
            logging.getLogger(__name__),
        )

    debts = repo.load_debts()
    debt_payments = repo.load_debt_payments()
    assert [(debt.id, debt.contact_name, debt.remaining_amount_minor) for debt in debts] == [
        (1, "Alex", 700)
    ]
    assert [
        (payment.id, payment.debt_id, payment.principal_paid_minor) for payment in debt_payments
    ] == [(1, 1, 300)]


def test_run_import_transaction_rolls_back_on_key_error_for_json_repository(tmp_path: Path) -> None:
    repo = JsonFileRecordRepository(str(tmp_path / "import_rollback_keyerror.json"))
    repo.replace_all_data(
        wallets=[
            Wallet(
                id=1,
                name="Main",
                currency="KZT",
                initial_balance=0.0,
                system=True,
                allow_negative=False,
                is_active=True,
            )
        ],
        records=[],
        mandatory_expenses=[],
        transfers=[],
        debts=[
            Debt(
                id=1,
                contact_name="Alex",
                kind=DebtKind.DEBT,
                total_amount_minor=1000,
                remaining_amount_minor=700,
                currency="KZT",
                interest_rate=0.0,
                status=DebtStatus.OPEN,
                created_at="2026-04-01",
            )
        ],
        debt_payments=[],
    )

    with pytest.raises(KeyError, match="boom"):
        run_import_transaction(
            typed_repo(repo),
            lambda: (
                repo.replace_all_data(
                    wallets=[
                        Wallet(
                            id=2,
                            name="Changed",
                            currency="KZT",
                            initial_balance=0.0,
                            system=True,
                            allow_negative=False,
                            is_active=True,
                        )
                    ],
                    records=[],
                    mandatory_expenses=[],
                    transfers=[],
                    debts=[],
                    debt_payments=[],
                ),
                (_ for _ in ()).throw(KeyError("boom")),
            ),
            logging.getLogger(__name__),
        )

    debts = repo.load_debts()
    wallets = repo.load_wallets()
    assert [(wallet.id, wallet.name) for wallet in wallets] == [(1, "Main")]
    assert [(debt.id, debt.contact_name) for debt in debts] == [(1, "Alex")]


def test_run_import_transaction_raises_when_json_rollback_fails() -> None:
    class BrokenRollbackRepo:
        def load_wallets(self):
            return []

        def load_all(self):
            return []

        def load_mandatory_expenses(self):
            return []

        def load_transfers(self):
            return []

        def load_debts(self):
            return []

        def load_debt_payments(self):
            return []

        def replace_all_data(self, **kwargs):  # noqa: ARG002
            raise RuntimeError("rollback failure")

    repo = BrokenRollbackRepo()

    with pytest.raises(RuntimeError, match="repository rollback also failed"):
        run_import_transaction(
            typed_repo(repo),
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            logging.getLogger(__name__),
        )
