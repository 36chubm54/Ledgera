import json
import tempfile
from datetime import date

from app.services import CurrencyService
from app.use_cases_pkg.operations import CreateIncome
from app.use_cases_pkg.reporting import GenerateReport
from domain.records import ExpenseRecord, IncomeRecord
from domain.reports import Report
from infrastructure.repositories import JsonFileRecordRepository
from tests.type_helpers import typed_repo


def test_wallet_migration_preserves_balance():
    legacy_payload = {
        "initial_balance": 120.0,
        "records": [
            {"type": "income", "date": "2025-01-01", "amount": 80.0, "category": "Salary"},
            {"type": "expense", "date": "2025-01-02", "amount": 30.0, "category": "Food"},
        ],
        "mandatory_expenses": [],
    }
    expected_balance = 120.0 + 80.0 - 30.0

    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json", encoding="utf-8"
    ) as fp:
        json.dump(legacy_payload, fp)
        path = fp.name

    repo = JsonFileRecordRepository(path)
    migrated_report = GenerateReport(typed_repo(repo)).execute()
    assert migrated_report.total_fixed() == expected_balance

    with open(path, encoding="utf-8") as fp:
        migrated = json.load(fp)
    assert "initial_balance" not in migrated
    assert migrated["wallets"][0]["id"] == 1
    assert migrated["wallets"][0]["initial_balance"] == 120.0
    assert all(item.get("wallet_id") == 1 for item in migrated["records"])


def test_create_record_assigns_system_wallet_id():
    class DummyCurrency:
        def convert(self, amount: float, _currency: str) -> float:
            return amount

        def get_rate(self, currency: str) -> float:
            return 1.0

    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json", encoding="utf-8"
    ) as fp:
        fp.write("{}")
        path = fp.name

    repo = JsonFileRecordRepository(path)
    CreateIncome(typed_repo(repo), CurrencyService()).execute(
        date="2025-01-01",
        wallet_id=1,
        amount=10.0,
        currency="KZT",
        category="Test",
    )
    records = repo.load_all()
    assert len(records) == 1
    assert records[0].wallet_id == 1


def test_report_total_unchanged_with_wallet_filter_defaults():
    records = [
        IncomeRecord(date="2025-01-01", amount_original=100.0, category="Salary"),
        ExpenseRecord(date="2025-01-03", amount_original=40.0, category="Food"),
    ]
    before = Report(records, initial_balance=50.0, wallet_id=None).total_fixed()
    after = Report(records, initial_balance=50.0).total_fixed()
    assert before == after


def test_opening_balance_uses_wallet_initial_balance():
    records = [
        IncomeRecord(date="2025-01-05", wallet_id=1, amount_original=20.0, category="Salary"),
        ExpenseRecord(date="2025-01-10", wallet_id=1, amount_original=5.0, category="Food"),
        IncomeRecord(date="2025-01-08", wallet_id=2, amount_original=999.0, category="Other"),
    ]
    report = Report(records, initial_balance=100.0, wallet_id=1)
    assert report.opening_balance("2025-01-09") == 120.0


def test_record_date_is_datetime_date_and_opening_balance_accepts_date_object():
    record = IncomeRecord(date="2025-01-01", _amount_init=10.0, category="Salary")
    assert isinstance(record.date, date)

    report = Report([record], initial_balance=5.0)
    assert report.opening_balance(date(2025, 1, 2)) == 15.0
