from __future__ import annotations

import sqlite3
from datetime import date as dt_date
from pathlib import Path

import pytest

from app.use_cases import AddMandatoryExpenseToReport
from domain.budget import BudgetStatus, PaceStatus
from domain.records import MandatoryExpenseRecord
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.budget_service import BudgetService
from services.metrics_service import MetricsService
from utils.money import to_minor_units


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "budget.db") -> SQLiteRecordRepository:
    db_path = tmp_path / name
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO wallets (
                id,
                name,
                currency,
                initial_balance,
                initial_balance_minor,
                system,
                allow_negative,
                is_active
            )
            VALUES (1, 'Main', 'KZT', 0, 0, 1, 0, 1)
            """
        )
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def _insert_expense(
    conn: sqlite3.Connection,
    *,
    date: str,
    category: str,
    amount_base: float,
    record_type: str = "expense",
    wallet_id: int = 1,
    transfer_id: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO records (
            type, date, wallet_id, transfer_id, amount_original, amount_original_minor,
            currency, rate_at_operation, rate_at_operation_text,
            amount_base, amount_base_minor, category, description, period
        )
        VALUES (?, ?, ?, ?, ?, ?, 'KZT', 1.0, '1.0', ?, ?, ?, '', ?)
        """,
        (
            record_type,
            date,
            wallet_id,
            transfer_id,
            amount_base,
            to_minor_units(amount_base),
            amount_base,
            to_minor_units(amount_base),
            category,
            "monthly" if record_type == "mandatory_expense" else None,
        ),
    )
    conn.commit()


def test_create_budget_returns_budget_with_id(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        budget = BudgetService(repo).create_budget("Food", "2026-03-01", "2026-03-31", 100000.0)
        assert budget.id > 0
        assert budget.category == "Food"
    finally:
        repo.close()


def test_create_budget_rejects_empty_category(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with pytest.raises(ValueError, match="Category is required"):
            BudgetService(repo).create_budget("", "2026-03-01", "2026-03-31", 1000.0)
    finally:
        repo.close()


def test_create_budget_rejects_inverted_dates(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with pytest.raises(ValueError, match="start_date must be <="):
            BudgetService(repo).create_budget("Food", "2026-03-31", "2026-03-01", 1000.0)
    finally:
        repo.close()


def test_create_budget_rejects_non_positive_limit(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with pytest.raises(ValueError, match="positive"):
            BudgetService(repo).create_budget("Food", "2026-03-01", "2026-03-31", 0.0)
    finally:
        repo.close()


def test_create_budget_persists_minor_limit(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        budget = BudgetService(repo).create_budget("Food", "2026-03-01", "2026-03-31", 1234.56)
        assert budget.limit_base_minor == to_minor_units(1234.56)
    finally:
        repo.close()


def test_create_budget_rejects_overlap_for_same_category(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = BudgetService(repo)
        service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        with pytest.raises(ValueError, match="overlapping period"):
            service.create_budget("Food", "2026-03-15", "2026-04-15", 2000.0)
    finally:
        repo.close()


def test_create_budget_allows_adjacent_periods(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = BudgetService(repo)
        service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        service.create_budget("Food", "2026-04-01", "2026-04-30", 1000.0)
        assert len(service.get_budgets()) == 2
    finally:
        repo.close()


def test_delete_budget_removes_it_from_results(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        service.delete_budget(budget.id)
        assert service.get_budgets() == []
    finally:
        repo.close()


def test_delete_budget_rejects_missing_id(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with pytest.raises(ValueError, match="Budget not found"):
            BudgetService(repo).delete_budget(999)
    finally:
        repo.close()


def test_update_budget_limit_updates_money_and_minor_columns(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        updated = service.update_budget_limit(budget.id, 2222.25)
        assert updated.limit_base == 2222.25
        assert updated.limit_base_minor == to_minor_units(2222.25)
    finally:
        repo.close()


def test_get_budget_result_without_expenses_is_on_track(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 10))
        assert result.spent_base == 0.0
        assert result.pace_status == PaceStatus.ON_TRACK
    finally:
        repo.close()


def test_get_budget_result_counts_expenses_in_range(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Food", amount_base=1500.0)
            _insert_expense(conn, date="2026-03-10", category="Food", amount_base=500.0)
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 5000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 15))
        assert result.spent_base == 2000.0
        assert result.spent_minor == to_minor_units(2000.0)
    finally:
        repo.close()


def test_get_budget_result_ignores_expenses_outside_range(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-02-28", category="Food", amount_base=1500.0)
            _insert_expense(conn, date="2026-04-01", category="Food", amount_base=500.0)
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 5000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 15))
        assert result.spent_base == 0.0
    finally:
        repo.close()


def test_get_budget_result_excludes_mandatory_when_flag_disabled(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Food", amount_base=1000.0)
            _insert_expense(
                conn,
                date="2026-03-06",
                category="Food",
                amount_base=250.0,
                record_type="mandatory_expense",
            )
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 5000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 15))
        assert result.spent_base == 1000.0
    finally:
        repo.close()


def test_get_budget_result_includes_mandatory_when_flag_enabled(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Food", amount_base=1000.0)
            _insert_expense(
                conn,
                date="2026-03-06",
                category="Food",
                amount_base=250.0,
                record_type="mandatory_expense",
            )
        service = BudgetService(repo)
        budget = service.create_budget(
            "Food",
            "2026-03-01",
            "2026-03-31",
            5000.0,
            include_mandatory=True,
        )
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 15))
        assert result.spent_base == 1250.0
    finally:
        repo.close()


def test_get_budget_result_marks_overspent_when_limit_reached(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Food", amount_base=1000.0)
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 15))
        assert result.pace_status == PaceStatus.OVERSPENT
        assert result.remaining_base == 0.0
    finally:
        repo.close()


def test_get_budget_result_marks_overpace_when_usage_exceeds_elapsed_time_by_threshold(
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-02", category="Food", amount_base=600.0)
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 5))
        assert result.status == BudgetStatus.ACTIVE
        assert result.pace_status == PaceStatus.OVERPACE
    finally:
        repo.close()


def test_get_budget_result_stays_on_track_when_only_slightly_above_time_line(
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-05-02", category="Travel", amount_base=750.0)
        service = BudgetService(repo)
        budget = service.create_budget("Travel", "2026-05-01", "2026-05-10", 800.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 5, 9))
        assert result.time_pct == 90.0
        assert result.usage_pct == 93.8
        assert result.pace_status == PaceStatus.ON_TRACK
    finally:
        repo.close()


def test_get_budget_result_ignores_transfer_linked_records(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(
                conn,
                date="2026-03-05",
                category="Food",
                amount_base=600.0,
                transfer_id=10,
            )
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 10))
        assert result.spent_base == 0.0
    finally:
        repo.close()


def test_budget_forecast_returns_localizable_status_key_and_params(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-02", category="Food", amount_base=100.0)
            _insert_expense(conn, date="2026-03-03", category="Food", amount_base=100.0)
            _insert_expense(conn, date="2026-03-04", category="Food", amount_base=100.0)
        service = BudgetService(repo)
        budget = service.create_budget("Food", "2026-03-01", "2026-03-31", 1000.0)
        result = service.get_budget_result(budget, today=dt_date(2026, 3, 10))
        assert result.forecast_status_key == "budget.forecast.remaining"
        assert result.forecast_status_params is not None
        assert "amount_base" in result.forecast_status_params
    finally:
        repo.close()


def test_tag_budget_filters_by_tag_not_category_name(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Travel", amount_base=600.0)
            _insert_expense(conn, date="2026-03-06", category="Travel", amount_base=200.0)
        repo.replace_record_tags(1, ("travel",))

        service = BudgetService(repo)
        budget = service.create_budget(
            "Travel",
            "2026-03-01",
            "2026-03-31",
            1000.0,
            scope_type="tag",
            scope_value="#Travel",
        )

        result = service.get_budget_result(budget, today=dt_date(2026, 3, 10))
        assert budget.scope_type == "tag"
        assert budget.scope_value == "travel"
        assert result.spent_base == 600.0
    finally:
        repo.close()


def test_get_distinct_expense_categories_returns_sorted_unique_values(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Food", amount_base=100.0)
            _insert_expense(conn, date="2026-03-06", category="food", amount_base=50.0)
        categories = MetricsService(repo).get_distinct_expense_categories()
        assert categories == ["Food", "food"]
    finally:
        repo.close()


def test_get_all_results_returns_batch_results_with_correct_spend(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        with sqlite3.connect(repo.db_path) as conn:
            _insert_expense(conn, date="2026-03-05", category="Food", amount_base=100.0)
            _insert_expense(
                conn,
                date="2026-03-06",
                category="Food",
                amount_base=25.0,
                record_type="mandatory_expense",
            )
            _insert_expense(conn, date="2026-03-07", category="Travel", amount_base=300.0)

        service = BudgetService(repo)
        food = service.create_budget("Food", "2026-03-01", "2026-03-31", 500.0)
        travel = service.create_budget("Travel", "2026-03-01", "2026-03-31", 800.0)
        food_with_mandatory = service.create_budget(
            "Food",
            "2026-04-01",
            "2026-04-30",
            500.0,
            include_mandatory=True,
        )

        results = service.get_all_results(today=dt_date(2026, 3, 20))
        by_id = {result.budget.id: result for result in results}

        assert by_id[food.id].spent_base == 100.0
        assert by_id[travel.id].spent_base == 300.0
        assert by_id[food_with_mandatory.id].spent_base == 0.0
    finally:
        repo.close()


def test_budget_includes_added_mandatory_record_within_period(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    try:
        repo.save_mandatory_expense(
            MandatoryExpenseRecord(
                wallet_id=1,
                date="",
                amount_original=250.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=250.0,
                category="Food",
                description="Meal plan",
                period="monthly",
            )
        )
        service = BudgetService(repo)
        budget = service.create_budget(
            "Food",
            "2026-03-01",
            "2026-03-31",
            1000.0,
            include_mandatory=True,
        )

        assert AddMandatoryExpenseToReport(repo).execute(0, "2026-03-15", 1) is True

        result = service.get_budget_result(budget, today=dt_date(2026, 3, 20))
        assert result.spent_base == 250.0
    finally:
        repo.close()
