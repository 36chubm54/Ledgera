from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import CurrencyService
from gui.controllers import FinancialController
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "dashboard.db") -> SQLiteRecordRepository:
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
            VALUES
                (1, 'Main', 'KZT', 0, 0, 1, 0, 1),
                (2, 'Cash', 'KZT', 1000, 100000, 0, 0, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO records (
                id, type, date, wallet_id, amount_original, amount_original_minor,
                currency, rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
            )
            VALUES
                (1, 'income', '2026-04-01', 2, 500, 50000, 'KZT', 1, '1.000000', 500, 50000, 'Salary', ''),
                (2, 'expense', '2026-04-15', 2, 100, 10000, 'KZT', 1, '1.000000', 100, 10000, 'Food', '')
            """  # noqa: E501
        )
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_controller_builds_dashboard_payload(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    controller = FinancialController(repo, CurrencyService(rates={"USD": 500.0}, use_online=False))
    try:
        asset = controller.create_asset(
            name="Brokerage",
            category="bank",
            currency="USD",
            created_at="2026-04-01",
        )
        controller.add_asset_snapshot(
            asset_id=asset.id,
            snapshot_date="2026-04-05",
            value=10.0,
        )
        goal = controller.create_goal(
            title="Reserve",
            target_amount=10000.0,
            currency="KZT",
            created_at="2026-04-05",
        )

        payload = controller.get_dashboard_payload()

        assert payload.summary.net_worth_base == 6400.0
        assert payload.summary.assets_total_base == 5000.0
        assert payload.summary.goals_total == 1
        assert payload.summary.goals_completed == 0
        assert payload.trend[-1].month == "2026-04"
        assert payload.trend[-1].balance == 1400.0
        assert len(payload.allocation) == 1
        assert payload.allocation[0].category == "bank"
        assert payload.allocation[0].amount_base == 5000.0
        assert payload.allocation[0].share_pct == 100.0
        assert len(payload.goals) == 1
        assert payload.goals[0].goal.id == goal.id
        assert payload.goals[0].progress_pct == 50.0
    finally:
        repo.close()
