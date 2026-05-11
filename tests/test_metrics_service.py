from __future__ import annotations

import sqlite3
from pathlib import Path

from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.metrics_service import CategorySpend, MetricsService, MonthlySummary, TagSpend


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


def _insert_tag(conn: sqlite3.Connection, tag_id: int, *, name: str, color: str = "") -> None:
    conn.execute(
        "INSERT INTO tags (id, name, color, usage_count, last_used_at) VALUES (?, ?, ?, 0, '')",
        (int(tag_id), str(name), str(color)),
    )
    conn.commit()


def _insert_record_tag(conn: sqlite3.Connection, *, record_id: int, tag_id: int) -> None:
    conn.execute(
        "INSERT INTO record_tags (record_id, tag_id) VALUES (?, ?)",
        (int(record_id), int(tag_id)),
    )
    conn.commit()


def _count_rows(repo: SQLiteRecordRepository, table: str) -> int:
    row = repo.query_one(f"SELECT COUNT(*) FROM {table}")
    return int(row[0]) if row else 0


def test_get_savings_rate_empty_db_returns_zero(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "metrics.db"), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_savings_rate("2026-01-01", "2026-01-31") == 0.0
    finally:
        repo.close()


def test_get_savings_rate_income_and_expense(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=100000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=60000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_savings_rate("2026-01-01", "2026-01-31") == 40.0
    finally:
        repo.close()


def test_get_savings_rate_income_zero_returns_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=1000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_savings_rate("2026-01-01", "2026-01-31") == 0.0
    finally:
        repo.close()


def test_get_savings_rate_excludes_transfers(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_wallet(conn, 2)
        _insert_record(
            conn, record_type="income", date="2026-01-01", wallet_id=1, amount_base=1000.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-01-02", wallet_id=1, amount_base=200.0
        )

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
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_savings_rate("2026-01-01", "2026-01-31") == 80.0
    finally:
        repo.close()


def test_get_burn_rate_empty_db_returns_zero(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "metrics.db"), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_burn_rate("2026-01-01", "2026-01-31") == 0.0
    finally:
        repo.close()


def test_get_burn_rate_total_expense_over_days(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="expense", date="2026-01-15", wallet_id=1, amount_base=30000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_burn_rate("2026-01-01", "2026-01-30") == 1000.0
    finally:
        repo.close()


def test_get_spending_by_category_is_sorted_desc(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-01",
            wallet_id=1,
            amount_base=2000.0,
            category="Food",
        )
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-02",
            wallet_id=1,
            amount_base=5000.0,
            category="Rent",
        )
        _insert_record(
            conn,
            record_type="mandatory_expense",
            date="2026-01-03",
            wallet_id=1,
            amount_base=3000.0,
            category="Fun",
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_spending_by_category("2026-01-01", "2026-01-31") == [
            CategorySpend(category="Rent", total_base=5000.0, record_count=1),
            CategorySpend(category="Fun", total_base=3000.0, record_count=1),
            CategorySpend(category="Food", total_base=2000.0, record_count=1),
        ]
    finally:
        repo.close()


def test_get_spending_by_category_limit_truncates(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        for index, (category, amount) in enumerate(
            [("A", 500.0), ("B", 400.0), ("C", 300.0), ("D", 200.0), ("E", 100.0)],
            start=1,
        ):
            _insert_record(
                conn,
                record_type="expense",
                date=f"2026-01-{index:02d}",
                wallet_id=1,
                amount_base=amount,
                category=category,
            )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        result = svc.get_spending_by_category("2026-01-01", "2026-01-31", limit=2)
        assert len(result) == 2
        assert result[0].category == "A"
        assert result[1].category == "B"
    finally:
        repo.close()


def test_get_income_by_category_sums_and_sorts(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-01",
            wallet_id=1,
            amount_base=6000.0,
            category="Salary",
        )
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-02",
            wallet_id=1,
            amount_base=4000.0,
            category="Salary",
        )
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-03",
            wallet_id=1,
            amount_base=5000.0,
            category="Gift",
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_income_by_category("2026-01-01", "2026-01-31") == [
            CategorySpend(category="Salary", total_base=10000.0, record_count=2),
            CategorySpend(category="Gift", total_base=5000.0, record_count=1),
        ]
    finally:
        repo.close()


def test_get_top_expense_categories_is_wrapper(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        for index, (category, amount) in enumerate(
            [("A", 500.0), ("B", 400.0), ("C", 300.0), ("D", 200.0)],
            start=1,
        ):
            _insert_record(
                conn,
                record_type="expense",
                date=f"2026-01-{index:02d}",
                wallet_id=1,
                amount_base=amount,
                category=category,
            )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_top_expense_categories(
            "2026-01-01", "2026-01-31", top_n=3
        ) == svc.get_spending_by_category(
            "2026-01-01",
            "2026-01-31",
            limit=3,
        )
    finally:
        repo.close()


def test_get_spending_by_tag_counts_full_amount_for_each_tag(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-01",
            wallet_id=1,
            amount_base=900.0,
            category="Food",
        )
        first_record_id = int(conn.execute("SELECT MAX(id) FROM records").fetchone()[0])
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-02",
            wallet_id=1,
            amount_base=600.0,
            category="Leisure",
        )
        second_record_id = int(conn.execute("SELECT MAX(id) FROM records").fetchone()[0])
        _insert_tag(conn, 1, name="food", color="#F2994A")
        _insert_tag(conn, 2, name="fun", color="#5B8DEF")
        _insert_record_tag(conn, record_id=first_record_id, tag_id=1)
        _insert_record_tag(conn, record_id=first_record_id, tag_id=2)
        _insert_record_tag(conn, record_id=second_record_id, tag_id=2)
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_spending_by_tag("2026-01-01", "2026-01-31") == [
            TagSpend(tag="fun", total_base=1500.0, record_count=2, color="#5B8DEF"),
            TagSpend(tag="food", total_base=900.0, record_count=1, color="#F2994A"),
        ]
    finally:
        repo.close()


def test_get_monthly_summary_empty_db_returns_empty_list(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "metrics.db"), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_monthly_summary() == []
    finally:
        repo.close()


def test_get_monthly_summary_two_months(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
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
        _insert_record(
            conn, record_type="income", date="2026-02-01", wallet_id=1, amount_base=500.0
        )
        _insert_record(
            conn, record_type="expense", date="2026-02-02", wallet_id=1, amount_base=700.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_monthly_summary() == [
            MonthlySummary(
                month="2026-01", income=1000.0, expenses=200.0, cashflow=800.0, savings_rate=80.0
            ),
            MonthlySummary(
                month="2026-02", income=500.0, expenses=700.0, cashflow=-200.0, savings_rate=-40.0
            ),
        ]
    finally:
        repo.close()


def test_get_monthly_summary_savings_rate_is_zero_when_income_is_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_record(
            conn, record_type="expense", date="2026-03-05", wallet_id=1, amount_base=1000.0
        )
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        assert svc.get_monthly_summary() == [
            MonthlySummary(
                month="2026-03", income=0.0, expenses=1000.0, cashflow=-1000.0, savings_rate=0.0
            )
        ]
    finally:
        repo.close()


def test_metrics_service_is_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1)
        _insert_wallet(conn, 2)
        _insert_record(
            conn,
            record_type="income",
            date="2026-01-01",
            wallet_id=1,
            amount_base=1000.0,
            category="Salary",
        )
        _insert_record(
            conn,
            record_type="expense",
            date="2026-01-02",
            wallet_id=1,
            amount_base=200.0,
            category="Food",
        )

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
    finally:
        conn.close()

    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    try:
        svc = MetricsService(repo)
        before = {
            "wallets": _count_rows(repo, "wallets"),
            "transfers": _count_rows(repo, "transfers"),
            "records": _count_rows(repo, "records"),
        }

        svc.get_savings_rate("2026-01-01", "2026-01-31")
        svc.get_burn_rate("2026-01-01", "2026-01-31")
        svc.get_spending_by_category("2026-01-01", "2026-01-31")
        svc.get_income_by_category("2026-01-01", "2026-01-31")
        svc.get_top_expense_categories("2026-01-01", "2026-01-31", top_n=2)
        svc.get_monthly_summary(start_date="2026-01-01", end_date="2026-01-31")

        after = {
            "wallets": _count_rows(repo, "wallets"),
            "transfers": _count_rows(repo, "transfers"),
            "records": _count_rows(repo, "records"),
        }
        assert after == before
    finally:
        repo.close()
