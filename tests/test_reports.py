from datetime import date

import pytest

import domain.reports as reports_module
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord
from domain.reports import Report


class TestReport:
    def test_creation(self):
        records = [IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")]
        report = Report(records)
        assert report.records() == records

    def test_creation_with_initial_balance(self):
        records = [IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")]
        report = Report(records, initial_balance=50.0)
        assert report.records() == records
        assert report.total() == 150.0

    def test_total_empty(self):
        report = Report([])
        assert report.total() == 0.0

    def test_total_single_income(self):
        records = [IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")]
        report = Report(records)
        assert report.total() == 100.0

    def test_total_single_expense(self):
        records = [ExpenseRecord(date="2025-01-01", _amount_init=50.0, category="Food")]
        report = Report(records)
        assert report.total() == -50.0

    def test_total_multiple_records(self):
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
            IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Bonus"),
        ]
        report = Report(records)
        assert report.total() == 120.0  # 100 - 30 + 50

    def test_filter_by_period(self):
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-02-01", _amount_init=30.0, category="Food"),
            IncomeRecord(date="2025-01-15", _amount_init=50.0, category="Bonus"),
        ]
        report = Report(records, initial_balance=20.0)
        jan_report = report.filter_by_period("2025-01")
        assert len(jan_report.records()) == 2
        assert jan_report.total() == 170.0  # 20 + 100 + 50

    def test_filter_by_category(self):
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
            IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Salary"),
        ]
        report = Report(records)
        salary_report = report.filter_by_category("Salary")
        assert len(salary_report.records()) == 2
        assert salary_report.total() == 150.0  # 100 + 50

    def test_grouped_by_category(self):
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
            IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Salary"),
            ExpenseRecord(date="2025-01-04", _amount_init=20.0, category="Food"),
        ]
        report = Report(records)
        groups = report.grouped_by_category()
        assert "Salary" in groups
        assert "Food" in groups
        assert groups["Salary"].total() == 150.0  # 100 + 50
        assert groups["Food"].total() == -50.0  # -30 - 20

    def test_grouped_by_category_does_not_include_initial_balance(self):
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", _amount_init=30.0, category="Food"),
        ]
        report = Report(records, initial_balance=500.0)
        groups = report.grouped_by_category()
        assert groups["Salary"].total() == 100.0
        assert groups["Food"].total() == -30.0

    def test_sorted_by_date(self):
        records = [
            IncomeRecord(date="2025-01-03", _amount_init=50.0, category="Bonus"),
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            IncomeRecord(date="2025-01-02", _amount_init=25.0, category="Salary"),
        ]
        report = Report(records)
        sorted_report = report.sorted_by_date()
        sorted_dates = [r.date for r in sorted_report.records()]
        assert sorted_dates == [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]

    def test_records_returns_copy(self):
        records = [IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary")]
        report = Report(records)
        returned_records = report.records()
        returned_records.append(
            ExpenseRecord(date="2025-01-02", _amount_init=50.0, category="Food")
        )
        assert len(report.records()) == 1  # Original unchanged

    def test_monthly_income_expense_rows_defaults_to_latest_year(self):
        records = [
            IncomeRecord(date="2024-12-31", _amount_init=40.0, category="Old"),
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-02-01", _amount_init=30.0, category="Food"),
        ]
        report = Report(records)
        year, rows = report.monthly_income_expense_rows()
        assert year == 2025
        assert len(rows) == 2
        assert rows[0][0] == "2025-01"
        assert rows[0][1] == 100.0
        assert rows[0][2] == 0.0
        assert rows[1][0] == "2025-02"
        assert rows[1][1] == 0.0
        assert rows[1][2] == 30.0

    def test_monthly_income_expense_rows_with_month_limit(self):
        records = [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-02-01", _amount_init=30.0, category="Food"),
            IncomeRecord(date="2025-03-01", _amount_init=50.0, category="Bonus"),
        ]
        report = Report(records)
        year, rows = report.monthly_income_expense_rows(year=2025, up_to_month=2)
        assert year == 2025
        assert len(rows) == 2
        assert rows[0][0] == "2025-01"
        assert rows[1][0] == "2025-02"


def _build_opening_balance_test_report() -> Report:
    records = [
        IncomeRecord(date="2023-12-31", _amount_init=50.0, category="Legacy"),
        ExpenseRecord(date="2024-01-10", _amount_init=20.0, category="Rent"),
        IncomeRecord(date="2024-03-05", _amount_init=30.0, category="Salary"),
        ExpenseRecord(date="2024-03-20", _amount_init=10.0, category="Food"),
        IncomeRecord(date="2024-04-01", _amount_init=40.0, category="Bonus"),
        ExpenseRecord(date="2025-01-01", _amount_init=5.0, category="Fees"),
    ]
    return Report(records, initial_balance=100.0)


def test_unfiltered_report_uses_initial_balance():
    report = _build_opening_balance_test_report()
    records_total = sum(r.signed_amount_base() for r in report.records())
    assert report.initial_balance == 100.0
    assert report.total_fixed() == 100.0 + records_total


def test_filter_year_uses_opening_balance():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period("2024")
    assert filtered.initial_balance == 150.0  # 100 + 50 from 2023-12-31
    assert filtered.balance_label == "Opening balance"


def test_filter_month_uses_opening_balance():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period("2024-03")
    assert filtered.initial_balance == 130.0  # 100 + 50 - 20
    assert filtered.balance_label == "Opening balance"


def test_filter_day_uses_opening_balance():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period("2024-03-20")
    assert filtered.initial_balance == 160.0  # 100 + 50 - 20 + 30
    assert filtered.balance_label == "Opening balance"


def test_opening_balance_invariant_for_filtered_report():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period("2024-03")
    period_sum = sum(r.signed_amount_base() for r in filtered.records())
    assert filtered.initial_balance + period_sum == filtered.total_fixed()


def test_opening_balance_when_no_records_before_start_date():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period("2023")
    assert filtered.initial_balance == report.initial_balance


def test_opening_balance_when_filter_after_all_records():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period("2025-12")
    assert filtered.records() == []
    assert filtered.initial_balance == report.total_fixed()
    assert filtered.total_fixed() == report.total_fixed()


def test_filter_by_period_raises_for_invalid_format():
    report = _build_opening_balance_test_report()
    with pytest.raises(ValueError):
        report.filter_by_period("2025/03")


def test_filter_by_category_does_not_carry_initial_balance() -> None:
    report = Report(
        [
            IncomeRecord(date="2025-01-01", _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", _amount_init=50.0, category="Food"),
        ],
        initial_balance=1000.0,
    )
    filtered = report.filter_by_category("Salary")
    assert filtered.initial_balance == 0.0
    assert filtered.total_fixed() == 100.0


def test_grouped_by_category_preserves_report_metadata() -> None:
    report = Report(
        [
            IncomeRecord(date="2025-01-01", wallet_id=2, _amount_init=100.0, category="Salary"),
            ExpenseRecord(date="2025-01-02", wallet_id=2, _amount_init=50.0, category="Food"),
        ],
        initial_balance=25.0,
        wallet_id=2,
        balance_label="Opening balance",
        opening_start_date="2025-01-01",
        period_start_date="2025-01-01",
        period_end_date="2025-01-31",
    )
    groups = report.grouped_by_category()
    salary = groups["Salary"]
    assert salary.initial_balance == 0.0
    assert salary.balance_label == "Opening balance"
    assert salary.opening_start_date == "2025-01-01"
    assert salary.period_start_date == "2025-01-01"
    assert salary.period_end_date == "2025-01-31"
    assert salary.statement_title == "Transaction statement (2025-01-01 - 2025-01-31)"


def test_filter_by_period_raises_for_future_date():
    report = _build_opening_balance_test_report()
    with pytest.raises(ValueError):
        report.filter_by_period("2999-01")


def test_sorted_by_date_uses_record_id_as_same_day_tiebreaker() -> None:
    report = Report(
        [
            IncomeRecord(id=7, date="2025-01-03", _amount_init=70.0, category="Third"),
            IncomeRecord(id=3, date="2025-01-03", _amount_init=30.0, category="First"),
            IncomeRecord(id=5, date="2025-01-03", _amount_init=50.0, category="Second"),
        ]
    )

    assert [int(record.id) for record in report.sorted_by_date().records()] == [3, 5, 7]


def test_sorted_records_desc_uses_record_id_as_same_day_tiebreaker() -> None:
    report = Report(
        [
            IncomeRecord(id=3, date="2025-01-03", _amount_init=30.0, category="First"),
            IncomeRecord(id=7, date="2025-01-03", _amount_init=70.0, category="Third"),
            IncomeRecord(id=5, date="2025-01-03", _amount_init=50.0, category="Second"),
        ]
    )

    assert [int(record.id) for record in report.sorted_records_desc()] == [7, 5, 3]


def test_filter_by_period_range_limits_end_date():
    report = _build_opening_balance_test_report()
    filtered = report.filter_by_period_range("2024", "2024-03")
    assert [r.date for r in filtered.records()] == [
        date(2024, 1, 10),
        date(2024, 3, 5),
        date(2024, 3, 20),
    ]
    assert filtered.period_start_date == "2024-01-01"
    assert filtered.period_end_date == "2024-03-31"
    assert filtered.statement_title == "Transaction statement (2024-01-01 - 2024-03-31)"


def test_filter_by_period_range_raises_when_end_before_start():
    report = _build_opening_balance_test_report()
    with pytest.raises(ValueError):
        report.filter_by_period_range("2024-03", "2024-01")


def test_monthly_income_expense_rows_uses_current_month_when_period_end_is_implicit(
    monkeypatch,
):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 4, 15)

    monkeypatch.setattr(reports_module, "dt_date", FakeDate)

    report = Report(
        [
            IncomeRecord(date="2026-01-10", _amount_init=100.0, category="Salary"),
        ]
    ).filter_by_period_range("2026-01")

    year, rows = report.monthly_income_expense_rows()

    assert year == 2026
    assert [row[0] for row in rows] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert rows[0][1] == 100.0
    assert rows[-1][0] == "2026-04"


def test_filter_by_year_includes_boundary_dates():
    records = [
        IncomeRecord(date="2025-01-01", _amount_init=10.0, category="Salary"),
        ExpenseRecord(date="2025-12-31", _amount_init=3.0, category="Food"),
        IncomeRecord(date="2024-12-31", _amount_init=5.0, category="Old"),
    ]
    report = Report(records, initial_balance=0.0)
    filtered = report.filter_by_period("2025")
    assert [r.date for r in filtered.records()] == [date(2025, 1, 1), date(2025, 12, 31)]


def test_filter_by_year_month_includes_month_boundaries():
    records = [
        IncomeRecord(date="2025-03-01", _amount_init=10.0, category="Salary"),
        ExpenseRecord(date="2025-03-31", _amount_init=3.0, category="Food"),
        IncomeRecord(date="2025-04-01", _amount_init=5.0, category="Next"),
    ]
    report = Report(records, initial_balance=0.0)
    filtered = report.filter_by_period("2025-03")
    assert [r.date for r in filtered.records()] == [date(2025, 3, 1), date(2025, 3, 31)]


def test_filter_skips_records_without_date():
    records = [
        IncomeRecord(date="2025-03-10", _amount_init=10.0, category="Salary"),
        MandatoryExpenseRecord(
            date="",
            _amount_init=5.0,
            category="Rent",
            description="Template",
            period="monthly",
        ),
        IncomeRecord(date="2025-03-11", _amount_init=2.0, category="Bonus"),
    ]
    report = Report(records)
    filtered = report.filter_by_period("2025-03")
    assert all(record.date for record in filtered.records())
