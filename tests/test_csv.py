import csv
import os
import tempfile
from datetime import date

import pytest

from domain.records import ExpenseRecord, IncomeRecord
from domain.reports import Report
from domain.transfers import Transfer
from gui.i18n import get_language, set_language
from utils.csv_utils import report_from_csv, report_to_csv


@pytest.fixture(autouse=True)
def _english_report_exports():
    previous = get_language()
    set_language("en")
    try:
        yield
    finally:
        set_language(previous)


def test_to_csv():
    records = [
        IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
        ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
    ]
    report = Report(records)
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
    try:
        report_to_csv(report, tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert rows[0] == ["Transaction statement", "", "", ""]
        assert rows[1] == ["Date", "Type", "Category", "Amount (KZT)"]
        assert rows[2] == ["", "", "", "Fixed amounts by operation-time FX rates"]
        assert rows[3] == ["2025-01-02", "Expense", "Food", "30.00"]
        assert rows[4] == ["2025-01-01", "Income", "Salary", "100.00"]
        assert rows[5] == ["SUBTOTAL", "", "", "70.00"]
    finally:
        os.unlink(tmp_path)


def test_to_csv_localizes_exported_report_and_keeps_roundtrip_in_ru():
    records = [
        IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Зарплата"),
        ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Еда"),
    ]
    report = Report(records, initial_balance=50.0)
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
    previous = get_language()
    try:
        set_language("ru")
        report_to_csv(report, tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["Отчет по операциям", "", "", ""]
        assert rows[1] == ["Дата", "Тип", "Категория", "Сумма (KZT)"]
        assert rows[3] == ["", "Начальный баланс", "", "50.00"]
        assert rows[4] == ["2025-01-02", "Расход", "Еда", "30.00"]
        assert rows[5] == ["2025-01-01", "Доход", "Зарплата", "100.00"]
        imported = report_from_csv(tmp_path)
        assert len(imported.records()) == 2
        assert abs(imported.initial_balance - 50.0) < 1e-6
        assert abs(imported.total() - report.total()) < 1e-6
    finally:
        set_language(previous)
        os.unlink(tmp_path)


def test_to_csv_localized_report_roundtrips_after_language_switch():
    records = [
        IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Зарплата"),
        ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Еда"),
    ]
    report = Report(records, initial_balance=50.0)
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
    previous = get_language()
    try:
        set_language("ru")
        report_to_csv(report, tmp_path)
        set_language("en")
        imported = report_from_csv(tmp_path)
        assert len(imported.records()) == 2
        assert abs(imported.initial_balance - 50.0) < 1e-6
        assert abs(imported.total() - report.total()) < 1e-6
    finally:
        set_language(previous)
        os.unlink(tmp_path)


def test_to_csv_with_initial_balance():
    records = [
        IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
        ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
    ]
    report = Report(records, initial_balance=50.0)
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
    try:
        report_to_csv(report, tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert rows[0] == ["Transaction statement", "", "", ""]
        assert rows[1] == ["Date", "Type", "Category", "Amount (KZT)"]
        assert rows[2] == ["", "", "", "Fixed amounts by operation-time FX rates"]
        assert rows[3] == ["", "Initial balance", "", "50.00"]
        assert rows[4] == ["2025-01-02", "Expense", "Food", "30.00"]
        assert rows[5] == ["2025-01-01", "Income", "Salary", "100.00"]
        assert rows[6] == ["SUBTOTAL", "", "", "70.00"]
        assert rows[7] == ["FINAL BALANCE", "", "", "120.00"]
    finally:
        os.unlink(tmp_path)


def test_to_csv_with_opening_balance_label_for_filtered_report():
    records = [
        IncomeRecord(date="2024-12-31", _amount_init=20.0, category="Old"),
        IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
        ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
    ]
    report = Report(records, initial_balance=50.0).filter_by_period("2025")
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
    try:
        report_to_csv(report, tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0] == [
            "Transaction statement (2025-01-01 - 2025-12-31)",
            "",
            "",
            "",
        ]
        assert rows[3] == ["", "Opening balance", "", "70.00"]
        assert rows[-1] == ["FINAL BALANCE", "", "", "140.00"]
    finally:
        os.unlink(tmp_path)


def test_from_csv():
    # Create a temporary CSV file
    csv_content = """Date,Type,Category,Amount (KZT)
2025-01-01,Income,Salary,100000.00
2025-01-02,Expense,Food,15000.00
2025-01-03,Income,Bonus,50000.00
TOTAL,,,-2000.00"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv", newline="") as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        report = report_from_csv(tmp_path)
        records = report.records()
        assert len(records) == 3

        # Check first record (Income)
        assert records[0].date == date(2025, 1, 1)
        assert isinstance(records[0], IncomeRecord)
        assert records[0].category == "Salary"
        assert records[0].amount == 100000.0

        # Check second record (Expense)
        assert records[1].date == date(2025, 1, 2)
        assert isinstance(records[1], ExpenseRecord)
        assert records[1].category == "Food"
        assert records[1].amount == 15000.0

        # Check third record (Income)
        assert records[2].date == date(2025, 1, 3)
        assert isinstance(records[2], IncomeRecord)
        assert records[2].category == "Bonus"
        assert records[2].amount == 50000.0

    finally:
        os.unlink(tmp_path)


def test_from_csv_with_negative_amounts():
    # Test CSV with negative amounts (expenses)
    csv_content = """Date,Type,Category,Amount (KZT)
2025-01-01,Income,Salary,100.00
2025-01-02,Expense,Food,(50.00)
TOTAL,,,-50.00"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv", newline="") as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        report = report_from_csv(tmp_path)
        records = report.records()
        assert len(records) == 2

        assert records[0].amount == 100.0
        assert records[1].amount == 50.0  # Should be positive for ExpenseRecord

    finally:
        os.unlink(tmp_path)


def test_from_csv_with_initial_balance():
    # Test CSV import with initial balance
    csv_content = """Date,Type,Category,Amount (KZT)
,Initial Balance,,50000.00
2025-01-01,Income,Salary,100000.00
2025-01-02,Expense,Food,15000.00
TOTAL,,,-2000.00"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv", newline="") as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        report = report_from_csv(tmp_path)
        records = report.records()
        assert len(records) == 2
        assert report._initial_balance == 50000.0
        assert report.total() == 135000.0  # 50000 + 100000 - 15000

    finally:
        os.unlink(tmp_path)


def test_from_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        report_from_csv("nonexistent_file.csv")


def test_import_records_from_csv_with_partial_errors_keeps_valid_rows():
    from domain.import_policy import ImportPolicy
    from utils.csv_utils import import_records_from_csv

    csv_content = """
date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base
2025-01-01,income,1,Salary,10,USD,500,5000
2025-13-01,expense,1,Food,2,KZT,1,2
2025-01-03,expense,1,Food,3,KZT,1,3
"""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".csv", newline="", encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        records, initial_balance, summary = import_records_from_csv(
            tmp_path, policy=ImportPolicy.FULL_BACKUP
        )
        assert initial_balance == 0.0
        assert len(records) == 2
        assert summary[0] == 2
        assert summary[1] == 1
        assert len(summary[2]) == 1
    finally:
        os.unlink(tmp_path)


def test_import_records_from_csv_rejects_fractional_transfer_wallet_ids():
    from domain.import_policy import ImportPolicy
    from utils.csv_utils import import_records_from_csv

    csv_content = """
date,type,from_wallet_id,to_wallet_id,amount_original,currency,rate_at_operation,amount_base
2025-01-01,transfer,1.5,2,10,KZT,1,10
"""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".csv", newline="", encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        records, _, summary = import_records_from_csv(tmp_path, policy=ImportPolicy.FULL_BACKUP)
        assert records == []
        assert summary[0] == 0
        assert summary[1] == 1
        assert "invalid transfer wallets" in summary[2][0]
    finally:
        os.unlink(tmp_path)


def test_csv_export_grouped_drill_down():
    """Export a report filtered by a single category (simulating grouped drill‑down)."""
    import csv
    import os
    import tempfile

    from domain.records import ExpenseRecord, IncomeRecord
    from domain.reports import Report

    records = [
        IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
        ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
        IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Salary"),
        ExpenseRecord(date="2025-01-04", _amount_init=20.0, category="Food"),
    ]
    report = Report(records, initial_balance=200.0)
    # Simulate drill‑down into "Salary" category
    filtered = report.filter_by_category("Salary")
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name
    try:
        report_to_csv(filtered, tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        # Header rows
        assert rows[0][0] == "Transaction statement"
        assert rows[1] == ["Date", "Type", "Category", "Amount (KZT)"]
        assert rows[2][3] == "Fixed amounts by operation-time FX rates"
        # No initial balance because filter_by_category resets it to zero
        # Expect two Salary records
        salary_rows = [r for r in rows if r[2] == "Salary"]
        assert len(salary_rows) == 2
        # Check amounts
        amounts = [float(r[3]) for r in rows if r[0] and r[0].startswith("2025")]
        assert amounts == [50.0, 100.0]
        # SUBTOTAL should be sum of amounts (150.0)
        subtotal_row = next(r for r in rows if r[0] == "SUBTOTAL")
        assert subtotal_row[3] == "150.00"
        # FINAL BALANCE should equal SUBTOTAL (since initial balance is zero)
        final_row = next(r for r in rows if r[0] == "FINAL BALANCE")
        assert final_row[3] == "150.00"
    finally:
        os.unlink(tmp_path)


def test_export_records_to_csv_preserves_record_positions_with_transfers() -> None:
    from utils.csv_utils import export_records_to_csv

    records = [
        ExpenseRecord(
            id=1,
            date="2026-03-05",
            wallet_id=1,
            amount_original=50.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=50.0,
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
            amount_base=25.0,
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
            amount_base=25.0,
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
            amount_base=100.0,
            category="Salary",
        ),
    ]
    transfers = [
        Transfer(
            id=7,
            from_wallet_id=1,
            to_wallet_id=2,
            date="2026-03-01",
            amount_original=25.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=25.0,
            description="Move",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv", newline="") as tmp:
        tmp_path = tmp.name
    try:
        export_records_to_csv(records, tmp_path, transfers=transfers)
        with open(tmp_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert [row["type"] for row in rows] == ["expense", "transfer", "income"]
        assert [row["category"] for row in rows] == ["Food", "Transfer", "Salary"]
        assert [row["date"] for row in rows] == ["2026-03-05", "2026-03-01", "2026-03-10"]
    finally:
        os.unlink(tmp_path)


def test_export_records_to_csv_keeps_unlinked_transfer_aggregates() -> None:
    from utils.csv_utils import export_records_to_csv

    records = [
        IncomeRecord(
            id=1,
            date="2026-03-10",
            wallet_id=2,
            amount_original=100.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=100.0,
            category="Salary",
        )
    ]
    transfers = [
        Transfer(
            id=7,
            from_wallet_id=1,
            to_wallet_id=2,
            date="2026-03-01",
            amount_original=25.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=25.0,
            description="Move",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv", newline="") as tmp:
        tmp_path = tmp.name
    try:
        export_records_to_csv(records, tmp_path, transfers=transfers)
        with open(tmp_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert [row["type"] for row in rows] == ["income", "transfer"]
        assert rows[1]["transfer_id"] == "7"
    finally:
        os.unlink(tmp_path)
