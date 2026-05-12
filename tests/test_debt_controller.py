from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import CurrencyService
from gui.controllers import FinancialController
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _build_repo(tmp_path: Path, name: str = "debt_controller.db") -> SQLiteRecordRepository:
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
        conn.commit()
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_controller_exposes_debt_flow_end_to_end(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    controller = FinancialController(repo, CurrencyService())
    try:
        debt = controller.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=300.0,
            created_at="2026-03-01",
        )
        payment = controller.register_debt_payment(
            debt_id=debt.id,
            wallet_id=2,
            amount_base=100.0,
            payment_date="2026-03-02",
        )

        open_debts = controller.get_open_debts()
        history = controller.get_debt_history(debt.id)
        recalculated = controller.recalculate_debt(debt.id)

        assert len(controller.get_debts()) == 1
        assert len(open_debts) == 1
        assert open_debts[0].id == debt.id
        assert len(history) == 1
        assert history[0].id == payment.id
        assert recalculated.remaining_amount_minor == 20000

        controller.close_debt(
            debt_id=debt.id,
            payment_date="2026-03-03",
            wallet_id=2,
        )
        assert controller.get_closed_debts()[0].id == debt.id
    finally:
        repo.close()


def test_controller_net_worth_includes_open_debt_liability(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "debt_net_worth.db")
    controller = FinancialController(repo, CurrencyService())
    try:
        baseline = controller.net_worth_fixed()
        controller.create_debt(
            contact_name="Alice",
            wallet_id=2,
            amount_base=300.0,
            created_at="2026-03-01",
        )
        assert controller.net_worth_fixed() == baseline
    finally:
        repo.close()


def test_controller_can_filter_debts_by_wallet_via_linked_records(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, "debt_wallet_filter.db")
    controller = FinancialController(repo, CurrencyService())
    try:
        cash_debt = controller.create_debt(
            contact_name="Cash debt",
            wallet_id=2,
            amount_base=300.0,
            created_at="2026-03-01",
        )
        main_debt = controller.create_debt(
            contact_name="Main debt",
            wallet_id=1,
            amount_base=150.0,
            created_at="2026-03-02",
        )

        assert {debt.id for debt in controller.get_debts()} == {cash_debt.id, main_debt.id}
        assert [debt.id for debt in controller.get_debts(2)] == [cash_debt.id]
        assert [debt.id for debt in controller.get_debts(1)] == [main_debt.id]
    finally:
        repo.close()
