import json
import os
import tempfile
import threading
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import infrastructure.repositories as repositories_module
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord
from infrastructure.repositories import (
    JsonFileRecordRepository,
    RecordRepository,
    RepositoryDataCorruptionError,
    RepositorySaveError,
)


class TestRecordRepository:
    def test_repository_is_abstract(self):
        # RecordRepository is abstract and cannot be instantiated directly
        with pytest.raises(TypeError):
            RecordRepository()  # type: ignore


class TestJsonFileRecordRepository:
    def setup_method(self):
        # Create a temporary file for each test
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json")
        self.temp_file.close()
        os.unlink(self.temp_file.name)
        self.repo = JsonFileRecordRepository(self.temp_file.name)

    def teardown_method(self):
        # Clean up the temporary file
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
        parent = os.path.dirname(self.temp_file.name) or "."
        basename = os.path.basename(self.temp_file.name)
        for entry in os.listdir(parent):
            if entry.startswith(basename + ".corrupt_"):
                try:
                    os.unlink(os.path.join(parent, entry))
                except FileNotFoundError:
                    pass

    def test_save_and_load_single_income(self):
        record = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        self.repo.save(record)
        records = self.repo.load_all()
        assert len(records) == 1
        assert records[0].date == date(2025, 1, 1)
        assert records[0].amount == 100.0
        assert records[0].category == "Salary"
        assert isinstance(records[0], IncomeRecord)

    def test_save_and_load_single_expense(self):
        record = ExpenseRecord(date="2025-01-02", _amount_init=50.0, category="Food")
        self.repo.save(record)
        records = self.repo.load_all()
        assert len(records) == 1
        assert records[0].date == date(2025, 1, 2)
        assert records[0].amount == 50.0
        assert records[0].category == "Food"
        assert isinstance(records[0], ExpenseRecord)

    def test_save_multiple_records(self):
        income1 = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        expense1 = ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food")
        income2 = IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Bonus")

        self.repo.save(income1)
        self.repo.save(expense1)
        self.repo.save(income2)

        records = self.repo.load_all()
        assert len(records) == 3

    def test_load_all_empty_file(self):
        with open(self.temp_file.name, "w", encoding="utf-8"):
            pass

        with pytest.raises(RepositoryDataCorruptionError, match="Repository JSON is corrupted"):
            self.repo.load_all()

        quarantine_candidates = [
            path
            for path in os.listdir(os.path.dirname(self.temp_file.name) or ".")
            if path.startswith(os.path.basename(self.temp_file.name) + ".corrupt_")
        ]
        assert quarantine_candidates

    def test_load_all_nonexistent_file(self):
        # Create repo with non-existent file
        nonexistent_repo = JsonFileRecordRepository("nonexistent.json")
        records = nonexistent_repo.load_all()
        assert records == []

    def test_load_all_corrupted_json_raises_data_corruption_error(self):
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            f.write('{"records": [}')

        with pytest.raises(RepositoryDataCorruptionError, match="Repository JSON is corrupted"):
            self.repo.load_all()

        quarantine_candidates = [
            path
            for path in os.listdir(os.path.dirname(self.temp_file.name) or ".")
            if path.startswith(os.path.basename(self.temp_file.name) + ".corrupt_")
        ]
        assert quarantine_candidates

    def test_json_file_format(self):
        # Test that the JSON file has the correct format
        record = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        self.repo.save(record)

        # Read the raw JSON to verify format
        with open(self.temp_file.name, encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert "wallets" in data
        assert "records" in data
        assert data["wallets"][0]["initial_balance"] == 0.0
        assert len(data["records"]) == 1
        assert data["records"][0]["type"] == "income"
        assert data["records"][0]["date"] == "2025-01-01"
        assert data["records"][0]["amount_original"] == 100.0
        assert data["records"][0]["amount_base"] == 100.0
        assert data["records"][0]["currency"] == "KZT"
        assert data["records"][0]["rate_at_operation"] == 1.0
        assert data["records"][0]["category"] == "Salary"

    def test_save_data_fsyncs_temp_file_before_replace(self):
        with patch.object(repositories_module.os, "fsync") as fsync_mock:
            self.repo.save(IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"))

        fsync_mock.assert_called_once()

    def test_save_surfaces_onedrive_like_lock_without_overwriting_existing_data(self):
        self.repo.save(IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"))
        original_payload = json.loads(Path(self.temp_file.name).read_text(encoding="utf-8"))

        def _locked_replace(_src, _dst):
            error = PermissionError("file is locked")
            error.winerror = 32
            raise error

        with (
            patch.object(repositories_module.os, "replace", side_effect=_locked_replace),
            patch.object(repositories_module.time, "sleep"),
        ):
            with pytest.raises(RepositorySaveError, match="Temporary file saved to"):
                self.repo.save(IncomeRecord(date="2025-01-02", _amount_init=50.0, category="Bonus"))

        current_payload = json.loads(Path(self.temp_file.name).read_text(encoding="utf-8"))
        assert current_payload == original_payload

        error_copy = Path(self.temp_file.name + ".error")
        assert error_copy.exists()
        error_payload = json.loads(error_copy.read_text(encoding="utf-8"))
        assert len(error_payload["records"]) == 2
        error_copy.unlink()

    def test_load_records_with_backward_compatibility(self):
        # Test loading records without category (backward compatibility)
        json_data = [
            {"type": "income", "date": "2025-01-01", "amount": 100.0},
            {"type": "expense", "date": "2025-01-02", "amount": 50.0},
        ]
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        records = self.repo.load_all()
        assert len(records) == 2
        assert records[0].category == "General"  # Default category
        assert records[1].category == "General"  # Default category

    def test_load_records_preserves_legacy_amount_kzt_values(self):
        json_data = {
            "wallets": [
                {
                    "id": 1,
                    "name": "Main wallet",
                    "currency": "KZT",
                    "initial_balance": 0.0,
                    "system": True,
                    "allow_negative": False,
                    "is_active": True,
                }
            ],
            "records": [
                {
                    "id": 1,
                    "type": "income",
                    "date": "2025-01-01",
                    "wallet_id": 1,
                    "amount_original": 10.0,
                    "currency": "USD",
                    "rate_at_operation": 500.0,
                    "amount_kzt": 5000.0,
                    "category": "Salary",
                }
            ],
            "mandatory_expenses": [],
            "transfers": [],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        records = self.repo.load_all()
        assert len(records) == 1
        assert records[0].amount_original == pytest.approx(10.0)
        assert records[0].amount_base == pytest.approx(5000.0)

    def test_load_transfers_preserves_legacy_amount_kzt_values(self):
        json_data = {
            "wallets": [
                {
                    "id": 1,
                    "name": "Main wallet",
                    "currency": "KZT",
                    "initial_balance": 0.0,
                    "system": True,
                    "allow_negative": False,
                    "is_active": True,
                },
                {
                    "id": 2,
                    "name": "Savings",
                    "currency": "USD",
                    "initial_balance": 0.0,
                    "system": False,
                    "allow_negative": False,
                    "is_active": True,
                },
            ],
            "records": [
                {
                    "id": 1,
                    "type": "expense",
                    "date": "2025-01-01",
                    "wallet_id": 1,
                    "transfer_id": 7,
                    "amount_original": 100.0,
                    "currency": "USD",
                    "rate_at_operation": 500.0,
                    "amount_kzt": 50000.0,
                    "category": "Transfers",
                    "description": "To savings",
                },
                {
                    "id": 2,
                    "type": "income",
                    "date": "2025-01-01",
                    "wallet_id": 2,
                    "transfer_id": 7,
                    "amount_original": 100.0,
                    "currency": "USD",
                    "rate_at_operation": 500.0,
                    "amount_kzt": 50000.0,
                    "category": "Transfers",
                    "description": "To savings",
                },
            ],
            "mandatory_expenses": [],
            "transfers": [
                {
                    "id": 7,
                    "from_wallet_id": 1,
                    "to_wallet_id": 2,
                    "date": "2025-01-01",
                    "amount_original": 100.0,
                    "currency": "USD",
                    "rate_at_operation": 500.0,
                    "amount_kzt": 50000.0,
                    "description": "To savings",
                }
            ],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        transfers = self.repo.load_transfers()
        assert len(transfers) == 1
        assert transfers[0].amount_original == pytest.approx(100.0)
        assert transfers[0].amount_base == pytest.approx(50000.0)

    def test_invalid_record_type_ignored(self):
        # Test that invalid record types are ignored
        json_data = [
            {
                "type": "income",
                "date": "2025-01-01",
                "amount": 100.0,
                "category": "Salary",
            },
            {
                "type": "invalid",
                "date": "2025-01-02",
                "amount": 50.0,
                "category": "Test",
            },
        ]
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        records = self.repo.load_all()
        assert len(records) == 1  # Only the valid income record
        assert isinstance(records[0], IncomeRecord)

    def test_load_data_missing_mandatory_expenses_key(self):
        # Ensure missing mandatory_expenses is normalized
        json_data = {"initial_balance": 10.0, "records": []}
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        records = self.repo.load_all()
        assert records == []
        expenses = self.repo.load_mandatory_expenses()
        assert expenses == []

    def test_load_mandatory_expenses_skips_invalid_row(self):
        json_data = {
            "wallets": [
                {
                    "id": 1,
                    "name": "Main wallet",
                    "currency": "KZT",
                    "initial_balance": 0.0,
                    "system": True,
                    "allow_negative": False,
                    "is_active": True,
                }
            ],
            "records": [],
            "mandatory_expenses": [
                {
                    "date": "",
                    "wallet_id": 1,
                    "amount_original": 10.0,
                    "currency": "KZT",
                    "rate_at_operation": 1.0,
                    "amount_base": 10.0,
                    "category": "Mandatory",
                    "period": "monthly",
                },
                {"date": "", "wallet_id": "bad", "amount_original": "bad"},
            ],
            "transfers": [],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        expenses = self.repo.load_mandatory_expenses()
        assert len(expenses) == 1

    def test_load_wallets_uses_system_wallet_currency_as_fallback(self):
        json_data = {
            "wallets": [
                {
                    "id": 1,
                    "name": "Main wallet",
                    "currency": "USD",
                    "initial_balance": 0.0,
                    "system": True,
                    "allow_negative": False,
                    "is_active": True,
                },
                {
                    "id": 2,
                    "name": "Cash",
                    "initial_balance": 0.0,
                    "system": False,
                    "allow_negative": False,
                    "is_active": True,
                },
            ],
            "records": [],
            "mandatory_expenses": [],
            "transfers": [],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        wallets = self.repo.load_wallets()

        assert [wallet.currency for wallet in wallets] == ["USD", "USD"]

    def test_save_mandatory_expenses_ids_start_from_one(self):
        self.repo.save(IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"))
        self.repo.save_mandatory_expense(
            MandatoryExpenseRecord(
                date="",
                _amount_init=10.0,
                category="Mandatory",
                description="A",
                period="monthly",
            )
        )
        self.repo.save_mandatory_expense(
            MandatoryExpenseRecord(
                date="",
                _amount_init=20.0,
                category="Mandatory",
                description="B",
                period="monthly",
            )
        )
        expenses = self.repo.load_mandatory_expenses()
        assert [expense.id for expense in expenses] == [1, 2]

    def test_load_data_normalizes_mandatory_ids_from_one(self):
        json_data = {
            "wallets": [
                {
                    "id": 1,
                    "name": "Main wallet",
                    "currency": "KZT",
                    "initial_balance": 0.0,
                    "system": True,
                    "allow_negative": False,
                    "is_active": True,
                }
            ],
            "records": [],
            "mandatory_expenses": [
                {
                    "id": 11,
                    "date": "",
                    "wallet_id": 1,
                    "amount_original": 10.0,
                    "currency": "KZT",
                    "rate_at_operation": 1.0,
                    "amount_base": 10.0,
                    "category": "Mandatory",
                    "description": "A",
                    "period": "monthly",
                },
                {
                    "id": 77,
                    "date": "",
                    "wallet_id": 1,
                    "amount_original": 20.0,
                    "currency": "KZT",
                    "rate_at_operation": 1.0,
                    "amount_base": 20.0,
                    "category": "Mandatory",
                    "description": "B",
                    "period": "monthly",
                },
            ],
            "transfers": [],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        expenses = self.repo.load_mandatory_expenses()
        assert [expense.id for expense in expenses] == [1, 2]

    def test_save_and_load_mandatory_expense_preserves_date(self):
        self.repo.save_mandatory_expense(
            MandatoryExpenseRecord(
                date="2026-03-10",
                wallet_id=1,
                amount_original=10.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=10.0,
                category="Mandatory",
                description="A",
                period="monthly",
                auto_pay=True,
            )
        )

        expenses = self.repo.load_mandatory_expenses()
        assert len(expenses) == 1
        assert str(expenses[0].date) == "2026-03-10"
        assert expenses[0].auto_pay is True

    def test_delete_by_index_success(self):
        # Setup: add some records
        income1 = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        expense1 = ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food")
        income2 = IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Bonus")

        self.repo.save(income1)
        self.repo.save(expense1)
        self.repo.save(income2)

        # Verify we have 3 records
        records = self.repo.load_all()
        assert len(records) == 3

        # Delete the middle record (index 1)
        result = self.repo.delete_by_index(1)
        assert result is True

        # Verify we now have 2 records and the correct one was deleted
        records = self.repo.load_all()
        assert len(records) == 2
        assert records[0].category == "Salary"  # First record still there
        assert records[1].category == "Bonus"  # Third record still there

    def test_delete_by_index_out_of_range(self):
        income1 = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        self.repo.save(income1)

        # Try to delete non-existent index
        result = self.repo.delete_by_index(5)
        assert result is False

        # Verify record still exists
        records = self.repo.load_all()
        assert len(records) == 1

    def test_delete_by_index_negative(self):
        income1 = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        self.repo.save(income1)

        # Try to delete with negative index
        result = self.repo.delete_by_index(-1)
        assert result is False

        # Verify record still exists
        records = self.repo.load_all()
        assert len(records) == 1

    def test_delete_by_index_empty_repository(self):
        # Try to delete from empty repository
        result = self.repo.delete_by_index(0)
        assert result is False

    def test_delete_all(self):
        # Setup: add some records
        income1 = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        expense1 = ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food")
        income2 = IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Bonus")

        self.repo.save(income1)
        self.repo.save(expense1)
        self.repo.save(income2)

        # Verify we have 3 records
        records = self.repo.load_all()
        assert len(records) == 3

        # Delete all records
        self.repo.delete_all()

        # Verify repository is empty
        records = self.repo.load_all()
        assert len(records) == 0

        # Verify JSON file contains empty records but initial_balance
        with open(self.temp_file.name, encoding="utf-8") as f:
            data = json.load(f)
        assert data["records"] == []
        assert "initial_balance" not in data

    def test_save_and_load_initial_balance(self):
        # Test saving and loading initial balance
        self.repo.save_initial_balance(100.0)
        balance = self.repo.load_initial_balance()
        assert balance == 100.0

        # Verify JSON file
        with open(self.temp_file.name, encoding="utf-8") as f:
            data = json.load(f)
        assert "initial_balance" not in data
        assert "wallets" in data
        assert data["wallets"][0]["id"] == 1
        assert data["wallets"][0]["initial_balance"] == 100.0
        assert data["records"] == []

    def test_load_initial_balance_default(self):
        # Test loading initial balance when not set (should be 0.0)
        balance = self.repo.load_initial_balance()
        assert balance == 0.0

    def test_save_initial_balance_overwrite(self):
        # Test overwriting initial balance
        self.repo.save_initial_balance(50.0)
        self.repo.save_initial_balance(75.0)
        balance = self.repo.load_initial_balance()
        assert balance == 75.0

    def test_initial_balance_with_records(self):
        # Test initial balance persists with records
        self.repo.save_initial_balance(200.0)
        record = IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")
        self.repo.save(record)

        balance = self.repo.load_initial_balance()
        assert balance == 200.0

        records = self.repo.load_all()
        assert len(records) == 1

        # Verify JSON file
        with open(self.temp_file.name, encoding="utf-8") as f:
            data = json.load(f)
        assert "initial_balance" not in data
        assert data["wallets"][0]["initial_balance"] == 200.0
        assert len(data["records"]) == 1

    def test_concurrent_access_save_and_load(self):
        def writer(start: int) -> None:
            for index in range(start, start + 20):
                self.repo.save(
                    IncomeRecord(
                        date="2025-01-01",
                        _amount_init=float(index),
                        category=f"C{index}",
                    )
                )

        threads = [threading.Thread(target=writer, args=(i * 20,)) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        records = self.repo.load_all()
        assert len(records) == 60

    def test_load_all_skips_record_with_fractional_wallet_id_in_json(self):
        json_data = {
            "wallets": [
                {
                    "id": 1,
                    "name": "Main wallet",
                    "currency": "KZT",
                    "initial_balance": 0.0,
                    "system": True,
                    "allow_negative": False,
                    "is_active": True,
                }
            ],
            "records": [
                {
                    "id": 1,
                    "type": "income",
                    "date": "2025-01-01",
                    "wallet_id": 1,
                    "amount_original": 10.0,
                    "currency": "KZT",
                    "rate_at_operation": 1.0,
                    "amount_base": 10.0,
                    "category": "Salary",
                },
                {
                    "id": 2,
                    "type": "income",
                    "date": "2025-01-02",
                    "wallet_id": "1.5",
                    "amount_original": 20.0,
                    "currency": "KZT",
                    "rate_at_operation": 1.0,
                    "amount_base": 20.0,
                    "category": "Bonus",
                },
            ],
            "mandatory_expenses": [],
            "transfers": [],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        records = self.repo.load_all()

        assert len(records) == 1
        assert records[0].category == "Salary"

    def test_load_all_raises_when_repository_migration_cannot_be_persisted(self):
        json_data = {
            "initial_balance": 0.0,
            "records": [
                {
                    "type": "income",
                    "date": "2025-01-01",
                    "amount": 10.0,
                    "category": "Salary",
                }
            ],
            "mandatory_expenses": [],
        }
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(json_data, f)

        with patch.object(self.repo, "_save_data", side_effect=RepositorySaveError("boom")):
            with pytest.raises(RepositorySaveError, match="boom"):
                self.repo.load_all()
