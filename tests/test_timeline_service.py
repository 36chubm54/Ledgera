from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import CurrencyService
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.analytics.timeline import (
    MonthlyCashflow,
    MonthlyCumulative,
    MonthlyNetWorth,
    TimelineService,
)


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def _insert_wallet(conn: sqlite3.Connection, wallet_id: int, initial_balance: float = 0.0) -> None:
    conn.execute(
        "INSERT INTO wallets (id, name, currency, initial_balance, is_active) "
        "VALUES (?, 'Test', 'KZT', ?, 1)",
        (int(wallet_id), float(initial_balance)),
    )
    conn.commit()


def _insert_wallet_with_currency(
    conn: sqlite3.Connection,
    wallet_id: int,
    *,
    currency: str,
    initial_balance: float = 0.0,
) -> None:
    conn.execute(
        "INSERT INTO wallets (id, name, currency, initial_balance, is_active) "
        "VALUES (?, 'Test', ?, ?, 1)",
        (int(wallet_id), str(currency), float(initial_balance)),
    )
    conn.commit()


def _insert_transfer(
    conn: sqlite3.Connection,
    *,
    transfer_id: int,
    from_wallet_id: int,
    to_wallet_id: int,
    date: str,
    amount_base: float,
) -> None:
    conn.execute(
        "INSERT INTO transfers "
        "(id, from_wallet_id, to_wallet_id, date, amount_original, currency, "
        "rate_at_operation, amount_base, description) "
        "VALUES (?, ?, ?, ?, ?, 'KZT', 1.0, ?, 'Transfer')",
        (
            int(transfer_id),
            int(from_wallet_id),
            int(to_wallet_id),
            str(date),
            float(amount_base),
            float(amount_base),
        ),
    )
    conn.commit()


def _insert_record(
    conn: sqlite3.Connection,
    *,
    record_type: str,
    date: str,
    wallet_id: int,
    amount_base: float,
    transfer_id=None,
    category: str = "General",
) -> None:
    conn.execute(
        "INSERT INTO records "
        "(type, date, wallet_id, transfer_id, amount_original, currency, "
        "rate_at_operation, amount_base, category) "
        "VALUES (?, ?, ?, ?, ?, 'KZT', 1.0, ?, ?)",
        (
            str(record_type),
            str(date),
            int(wallet_id),
            transfer_id,
            float(amount_base),
            float(amount_base),
            str(category),
        ),
    )
    conn.commit()


def _count_rows(repo: SQLiteRecordRepository, table: str) -> int:
    row = repo.query_one(f"SELECT COUNT(*) FROM {table}")
    return int(row[0]) if row else 0


def test_get_net_worth_timeline_returns_empty_list_on_empty_db(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "timeline.db"), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_net_worth_timeline() == []
    finally:
        repo.close()


def test_get_net_worth_timeline_single_income_single_month(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-10", wallet_id=1, amount_base=1000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_net_worth_timeline() == [MonthlyNetWorth(month="2026-01", balance=1000.0)]
    finally:
        repo.close()


def test_get_net_worth_timeline_is_cumulative_across_months(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-10", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-02-01", wallet_id=1, amount_base=200.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_net_worth_timeline() == [
            MonthlyNetWorth(month="2026-01", balance=1000.0),
            MonthlyNetWorth(month="2026-02", balance=800.0),
        ]
    finally:
        repo.close()


def test_get_net_worth_timeline_includes_wallet_initial_balance(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1, initial_balance=50000.0)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_net_worth_timeline() == [MonthlyNetWorth(month="2026-01", balance=51000.0)]
    finally:
        repo.close()


def test_get_net_worth_timeline_converts_multi_currency_initial_balance(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline_fx.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet_with_currency(conn, 1, currency="USD", initial_balance=10.0)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo, CurrencyService())
        assert svc.get_net_worth_timeline() == [MonthlyNetWorth(month="2026-01", balance=6000.0)]
    finally:
        repo.close()


def test_get_net_worth_timeline_transfer_pair_is_neutral(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_wallet(conn, 2)
        _insert_transfer(
            conn,
            transfer_id=1,
            from_wallet_id=1,
            to_wallet_id=2,
            date="2026-01-15",
            amount_base=500.0,
        )
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-15",
            wallet_id=1,
            amount_base=500.0,
            transfer_id=1,
            category="Transfer",
        )
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-15",
            wallet_id=2,
            amount_base=500.0,
            transfer_id=1,
            category="Transfer",
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_net_worth_timeline() == [MonthlyNetWorth(month="2026-01", balance=0.0)]
    finally:
        repo.close()


def test_get_monthly_cashflow_returns_empty_list_on_empty_db(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "timeline.db"), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_monthly_cashflow() == []
    finally:
        repo.close()


def test_get_monthly_cashflow_single_month_income_and_expense(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=400.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_monthly_cashflow() == [
            MonthlyCashflow(month="2026-01", income=1000.0, expenses=400.0, cashflow=600.0)
        ]
    finally:
        repo.close()


def test_get_monthly_cashflow_excludes_transfer_records(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_wallet(conn, 2)
        _insert_transfer(
            conn,
            transfer_id=1,
            from_wallet_id=1,
            to_wallet_id=2,
            date="2026-01-10",
            amount_base=500.0,
        )
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-10",
            wallet_id=1,
            amount_base=500.0,
            transfer_id=1,
            category="Transfer",
        )
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-10",
            wallet_id=2,
            amount_base=500.0,
            transfer_id=1,
            category="Transfer",
        )
        _insert_record(
            conn, record_type="income", date="2026-01-11", wallet_id=1, amount_base=100.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-12", wallet_id=1, amount_base=40.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_monthly_cashflow() == [
            MonthlyCashflow(month="2026-01", income=100.0, expenses=40.0, cashflow=60.0)
        ]
    finally:
        repo.close()


def test_get_monthly_cashflow_respects_start_and_end_date_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=10.0)
        _insert_record(conn, record_type="income", date="2026-02-01", wallet_id=1, amount_base=20.0)
        _insert_record(conn, record_type="income", date="2026-03-01", wallet_id=1, amount_base=30.0)
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_monthly_cashflow(start_date="2026-02-01", end_date="2026-02-28") == [
            MonthlyCashflow(month="2026-02", income=20.0, expenses=0.0, cashflow=20.0)
        ]
    finally:
        repo.close()


def test_get_cumulative_income_expense_returns_empty_list_on_empty_db(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "timeline.db"), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_cumulative_income_expense() == []
    finally:
        repo.close()


def test_get_cumulative_income_expense_accumulates_monotonically(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=200.0
        )
        _insert_record(conn, record_type="income", date="2026-02-01", wallet_id=1, amount_base=50.0)
        _insert_record(
            conn,
            record_type="mandatory_expense",
            date="2026-02-02",
            wallet_id=1,
            amount_base=10.0,
            category="Mandatory",
        )
        _insert_record(conn, record_type="expense", date="2026-03-01", wallet_id=1, amount_base=5.0)
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = TimelineService(repo)
        assert svc.get_cumulative_income_expense() == [
            MonthlyCumulative(month="2026-01", cumulative_income=1000.0, cumulative_expenses=200.0),
            MonthlyCumulative(month="2026-02", cumulative_income=1050.0, cumulative_expenses=210.0),
            MonthlyCumulative(month="2026-03", cumulative_income=1050.0, cumulative_expenses=215.0),
        ]
    finally:
        repo.close()


def test_timeline_service_is_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "timeline.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1, initial_balance=1000.0)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=100.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=50.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        before_wallets = _count_rows(repo, "wallets")
        before_records = _count_rows(repo, "records")
        before_transfers = _count_rows(repo, "transfers")
        before_mandatory = _count_rows(repo, "mandatory_expenses")

        svc = TimelineService(repo)
        _ = svc.get_net_worth_timeline()
        _ = svc.get_monthly_cashflow()
        _ = svc.get_cumulative_income_expense()

        assert _count_rows(repo, "wallets") == before_wallets
        assert _count_rows(repo, "records") == before_records
        assert _count_rows(repo, "transfers") == before_transfers
        assert _count_rows(repo, "mandatory_expenses") == before_mandatory
    finally:
        repo.close()
