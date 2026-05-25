from __future__ import annotations

import sqlite3
from pathlib import Path

import gui.tabs.reports.core.controller as reports_controller_module
from app.services import CurrencyService
from gui.controllers import FinancialController
from gui.tabs.reports.core.controller import ReportsController
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.analytics.report import ReportFilters


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path) -> SQLiteRecordRepository:
    db_path = tmp_path / "reports_controller.db"
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
            VALUES
                (1, 'Main', 'KZT', 0, 0, 1, 0, 1),
                (2, 'Cash', 'KZT', 0, 0, 0, 0, 1)
            """
        )
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_reports_controller_monthly_summary_uses_filtered_report_period(
    monkeypatch, tmp_path: Path
):
    class FakeDate:
        @staticmethod
        def today():
            from datetime import date

            return date(2026, 4, 1)

    monkeypatch.setattr(reports_controller_module, "date", FakeDate)

    repo = _build_repo(tmp_path)
    try:
        controller = FinancialController(repo, CurrencyService(use_online=False))
        controller.create_income(
            date="2026-02-10",
            wallet_id=2,
            amount=100.0,
            currency="KZT",
            category="Salary",
        )
        controller.create_expense(
            date="2026-04-01",
            wallet_id=2,
            amount=40.0,
            currency="KZT",
            category="Food",
        )

        result = ReportsController(controller, CurrencyService(use_online=False)).generate(
            ReportFilters(
                wallet_id=None,
                period_start="2026-02",
                period_end="",
                category="",
                totals_mode="fixed",
            )
        )

        assert [row.month for row in result.monthly] == ["2026-02", "2026-03", "2026-04"]
        assert [row.date for row in result.operations] == ["2026-04-01", "2026-02-10"]
        assert result.monthly[0].income == 100.0
        assert result.monthly[1].income == 0.0
        assert result.monthly[2].expense == 40.0
    finally:
        repo.close()
