import os
import tempfile
from datetime import date
from unittest.mock import Mock, patch

import pytest

from app.use_cases import (
    CloseDebt,
    CreateDebt,
    CreateExpense,
    CreateIncome,
    CreateLoan,
    DeleteAllRecords,
    DeleteDebt,
    DeleteDebtPayment,
    DeleteRecord,
    GenerateReport,
    GetClosedDebts,
    GetDebtHistory,
    GetDebts,
    GetOpenDebts,
    ImportFromCSV,
    RecalculateDebt,
    RegisterDebtPayment,
    RegisterDebtWriteOff,
)
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, Record
from domain.wallets import Wallet
from infrastructure.repositories import JsonFileRecordRepository, RecordRepository


class TestCreateIncome:
    def test_execute_creates_income_record_and_saves_to_repository(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_currency.convert.return_value = 47000.0  # 100 * 470
        mock_repo.load_wallets.return_value = [
            Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
        ]

        use_case = CreateIncome(repository=mock_repo, currency=mock_currency)

        # Act
        use_case.execute(
            date="2025-01-01",
            wallet_id=1,
            amount=100.0,
            currency="USD",
            category="Salary",
        )

        # Assert
        mock_currency.convert.assert_called_once_with(100.0, "USD")
        expected_record = IncomeRecord(
            date="2025-01-01",
            wallet_id=1,
            amount_original=100.0,
            currency="USD",
            rate_at_operation=470.0,
            amount_kzt=47000.0,
            category="Salary",
        )
        mock_repo.save.assert_called_once_with(expected_record)

    def test_execute_with_default_category(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_currency.convert.return_value = 47000.0
        mock_repo.load_wallets.return_value = [
            Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
        ]

        use_case = CreateIncome(repository=mock_repo, currency=mock_currency)

        # Act
        use_case.execute(date="2025-01-01", wallet_id=1, amount=100.0, currency="USD")

        # Assert
        expected_record = IncomeRecord(
            date="2025-01-01",
            wallet_id=1,
            amount_original=100.0,
            currency="USD",
            rate_at_operation=470.0,
            amount_kzt=47000.0,
            category="General",
        )
        mock_repo.save.assert_called_once_with(expected_record)

    def test_execute_rejects_numeric_only_tags(self):
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_repo.load_wallets.return_value = [
            Wallet(id=1, name="Main", currency="KZT", initial_balance=0.0, system=True)
        ]

        use_case = CreateIncome(repository=mock_repo, currency=mock_currency)

        with pytest.raises(ValueError, match="numbers only"):
            use_case.execute(
                date="2025-01-01",
                wallet_id=1,
                amount=100.0,
                currency="USD",
                category="Salary",
                tags=("2026",),
            )

        mock_repo.save.assert_not_called()


class TestCreateExpense:
    def test_execute_creates_expense_record_and_saves_to_repository(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_currency.convert.return_value = 23500.0  # 50 * 470
        mock_repo.load_wallets.return_value = [
            Wallet(
                id=1,
                name="Main",
                currency="KZT",
                initial_balance=50000.0,
                system=True,
            )
        ]
        mock_repo.load_all.return_value = []

        use_case = CreateExpense(repository=mock_repo, currency=mock_currency)

        # Act
        use_case.execute(
            date="2025-01-02",
            wallet_id=1,
            amount=50.0,
            currency="USD",
            category="Food",
        )

        # Assert
        assert mock_currency.convert.call_args_list[0].args == (50.0, "USD")
        expected_record = ExpenseRecord(
            date="2025-01-02",
            wallet_id=1,
            amount_original=50.0,
            currency="USD",
            rate_at_operation=470.0,
            amount_kzt=23500.0,
            category="Food",
        )
        mock_repo.save.assert_called_once_with(expected_record)

    def test_execute_with_default_category(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_currency.convert.return_value = 23500.0
        mock_repo.load_wallets.return_value = [
            Wallet(
                id=1,
                name="Main",
                currency="KZT",
                initial_balance=50000.0,
                system=True,
            )
        ]
        mock_repo.load_all.return_value = []

        use_case = CreateExpense(repository=mock_repo, currency=mock_currency)

        # Act
        use_case.execute(date="2025-01-02", wallet_id=1, amount=50.0, currency="USD")

        # Assert
        expected_record = ExpenseRecord(
            date="2025-01-02",
            wallet_id=1,
            amount_original=50.0,
            currency="USD",
            rate_at_operation=470.0,
            amount_kzt=23500.0,
            category="General",
        )
        mock_repo.save.assert_called_once_with(expected_record)

    def test_execute_rejects_numeric_only_tags(self):
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_currency.convert.return_value = 23500.0
        mock_repo.load_wallets.return_value = [
            Wallet(
                id=1,
                name="Main",
                currency="KZT",
                initial_balance=50000.0,
                system=True,
            )
        ]
        mock_repo.load_all.return_value = []

        use_case = CreateExpense(repository=mock_repo, currency=mock_currency)

        with pytest.raises(ValueError, match="numbers only"):
            use_case.execute(
                date="2025-01-02",
                wallet_id=1,
                amount=50.0,
                currency="USD",
                category="Food",
                tags=("2026",),
            )

        mock_repo.save.assert_not_called()


class TestGenerateReport:
    def test_execute_returns_report_with_all_records(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", _amount_init=50.0, category="Food"),
        ]
        mock_repo.load_all.return_value = records

        use_case = GenerateReport(repository=mock_repo)

        # Act
        report = use_case.execute()

        # Assert
        mock_repo.load_all.assert_called_once()
        assert report.records() == records

    def test_execute_converts_multi_currency_initial_balances_to_kzt(self):
        mock_repo = Mock(spec=RecordRepository)
        mock_currency = Mock()
        mock_repo.load_all.return_value = []
        mock_repo.load_wallets.return_value = [
            Wallet(id=1, name="Cash", currency="KZT", initial_balance=1000.0, system=True),
            Wallet(id=2, name="USD", currency="USD", initial_balance=10.0, system=False),
        ]
        mock_currency.convert.side_effect = lambda amount, code: amount if code == "KZT" else 5000.0

        report = GenerateReport(repository=mock_repo, currency=mock_currency).execute()

        assert report.initial_balance == 6000.0
        mock_currency.convert.assert_any_call(10.0, "USD")

    def test_delete_record_success(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_repo.delete_by_index.return_value = True

        use_case = DeleteRecord(repository=mock_repo)

        # Act
        result = use_case.execute(index=1)

        # Assert
        mock_repo.delete_by_index.assert_called_once_with(1)
        assert result is True

    def test_delete_record_failure(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_repo.delete_by_index.return_value = False

        use_case = DeleteRecord(repository=mock_repo)

        # Act
        result = use_case.execute(index=99)

        # Assert
        mock_repo.delete_by_index.assert_called_once_with(99)
        assert result is False


class TestDeleteAllRecords:
    def test_execute_calls_delete_all_on_repository(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)

        use_case = DeleteAllRecords(repository=mock_repo)

        # Act
        use_case.execute()

        # Assert
        mock_repo.delete_all.assert_called_once()


class TestImportFromCSV:
    def test_execute_imports_records_from_csv_and_saves_to_repository(self):
        # Arrange
        mock_repo = Mock(spec=RecordRepository)
        mock_repo.load_initial_balance.return_value = 0.0

        with patch("utils.csv_utils.import_records_from_csv") as mock_import:
            test_records = [Mock(spec=Record), Mock(spec=Record), Mock(spec=Record)]
            mock_import.return_value = (test_records, 0.0, (3, 0, []))

            use_case = ImportFromCSV(repository=mock_repo)

            # Act
            result = use_case.execute("test.csv")

            # Assert
            mock_import.assert_called_once_with(
                "test.csv",
                policy=ImportPolicy.FULL_BACKUP,
                existing_initial_balance=0.0,
            )
            mock_repo.replace_records_and_transfers.assert_called_once_with(test_records, [])
            assert result == 3


class TestDebtUseCases:
    def test_create_debt_delegates_to_service(self):
        service = Mock()
        expected = Mock()
        service.create_debt.return_value = expected

        result = CreateDebt(service).execute(
            contact_name="Alice",
            wallet_id=2,
            amount_kzt=500.0,
            created_at="2026-03-01",
        )

        service.create_debt.assert_called_once_with(
            contact_name="Alice",
            wallet_id=2,
            amount_kzt=500.0,
            created_at="2026-03-01",
            currency="KZT",
            interest_rate=0.0,
            description="",
        )
        assert result is expected

    def test_register_payment_delegates_to_service(self):
        service = Mock()
        expected = Mock()
        service.register_payment.return_value = expected

        result = RegisterDebtPayment(service).execute(
            debt_id=1,
            wallet_id=2,
            amount_kzt=100.0,
            payment_date="2026-03-05",
            description="Partially paid",
        )

        service.register_payment.assert_called_once_with(
            debt_id=1,
            wallet_id=2,
            amount_kzt=100.0,
            payment_date="2026-03-05",
            description="Partially paid",
        )
        assert result is expected

    def test_query_and_delete_use_cases_delegate_to_service(self):
        service = Mock()

        GetDebts(service).execute()
        GetOpenDebts(service).execute()
        GetClosedDebts(service).execute()
        GetDebtHistory(service).execute(3)
        DeleteDebt(service).execute(4)
        DeleteDebtPayment(service).execute(5, delete_linked_record=True)
        RecalculateDebt(service).execute(6)
        CloseDebt(service).execute(
            debt_id=7,
            payment_date="2026-03-10",
            wallet_id=2,
            write_off=False,
            description="Close",
        )
        CreateLoan(service).execute(
            contact_name="Bob",
            wallet_id=2,
            amount_kzt=250.0,
            created_at="2026-03-01",
        )
        RegisterDebtWriteOff(service).execute(
            debt_id=8,
            amount_kzt=50.0,
            payment_date="2026-03-11",
        )

        service.get_all_debts.assert_called_once()
        service.get_open_debts.assert_called_once()
        service.get_closed_debts.assert_called_once()
        service.get_debt_history.assert_called_once_with(3)
        service.delete_debt.assert_called_once_with(4)
        service.delete_payment.assert_called_once_with(5, delete_linked_record=True)
        service.recalculate_debt.assert_called_once_with(6)
        service.close_debt.assert_called_once_with(
            debt_id=7,
            payment_date="2026-03-10",
            wallet_id=2,
            write_off=False,
            description="Close",
        )
        service.create_loan.assert_called_once_with(
            contact_name="Bob",
            wallet_id=2,
            amount_kzt=250.0,
            created_at="2026-03-01",
            currency="KZT",
            interest_rate=0.0,
            description="",
        )
        service.register_write_off.assert_called_once_with(
            debt_id=8,
            amount_kzt=50.0,
            payment_date="2026-03-11",
        )

    def test_execute_saves_initial_balance(self):
        mock_repo = Mock(spec=RecordRepository)
        mock_repo.load_initial_balance.return_value = 0.0
        with patch("utils.csv_utils.import_records_from_csv") as mock_import:
            mock_import.return_value = ([], 123.45, (0, 0, []))

            use_case = ImportFromCSV(repository=mock_repo)
            use_case.execute("test.csv")

            mock_repo.replace_records_and_transfers.assert_called_once_with([], [])
            mock_repo.save_initial_balance.assert_called_once_with(123.45)

    def test_execute_does_not_modify_repository_on_import_error(self):
        mock_repo = Mock(spec=RecordRepository)
        with patch("utils.csv_utils.import_records_from_csv") as mock_import:
            mock_import.side_effect = ValueError("invalid csv")
            use_case = ImportFromCSV(repository=mock_repo)

            with patch.object(mock_repo, "replace_records_and_transfers") as replace_records:
                with patch.object(mock_repo, "delete_all") as delete_all:
                    with patch.object(mock_repo, "save") as save_record:
                        with patch.object(mock_repo, "save_initial_balance") as save_balance:
                            with pytest.raises(ValueError):
                                use_case.execute("broken.csv")

                        replace_records.assert_not_called()
                        delete_all.assert_not_called()
                        save_record.assert_not_called()
                        save_balance.assert_not_called()

    def test_execute_keeps_existing_data_when_csv_invalid(self):
        repo_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json")
        repo_file.close()
        csv_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv")
        csv_file.write("date,type,category,amount_original,currency,rate_at_operation,amount_kzt\n")
        csv_file.write("bad-date,income,Salary,10,USD,500,5000\n")
        csv_file.close()
        try:
            os.unlink(repo_file.name)
            repository = JsonFileRecordRepository(repo_file.name)
            repository.save_initial_balance(77.0)
            repository.save(IncomeRecord(date="2025-01-01", _amount_init=10.0, category="Salary"))

            use_case = ImportFromCSV(repository=repository)
            with pytest.raises(ValueError):
                use_case.execute(csv_file.name)

            assert repository.load_initial_balance() == 77.0
            records = repository.load_all()
            assert len(records) == 1
            assert records[0].date == date(2025, 1, 1)
        finally:
            os.unlink(repo_file.name)
            os.unlink(csv_file.name)
