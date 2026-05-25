from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import CurrencyService
from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.analytics.balance import BalanceService, WalletBalance


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def build_test_db(
    path: Path,
    *,
    wallets: list[dict],
    records: list[dict],
    transfers: list[dict],
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(Path(_schema_path()).read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA ignore_check_constraints = ON")

        for wallet in wallets:
            conn.execute(
                """
                INSERT INTO wallets (
                    id, name, currency, initial_balance, system, allow_negative, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wallet["id"],
                    wallet["name"],
                    wallet["currency"],
                    wallet.get("initial_balance", 0.0),
                    wallet.get("system", 0),
                    wallet.get("allow_negative", 0),
                    wallet.get("is_active", 1),
                ),
            )

        for transfer in transfers:
            conn.execute(
                """
                INSERT INTO transfers (
                    id, from_wallet_id, to_wallet_id, date, amount_original, currency,
                    rate_at_operation, amount_base, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transfer["id"],
                    transfer["from_wallet_id"],
                    transfer["to_wallet_id"],
                    transfer["date"],
                    transfer["amount_original"],
                    transfer["currency"],
                    transfer["rate_at_operation"],
                    transfer["amount_base"],
                    transfer.get("description", ""),
                ),
            )

        for record in records:
            conn.execute(
                """
                INSERT INTO records (
                    id, type, date, wallet_id, transfer_id, amount_original, currency,
                    rate_at_operation, amount_base, category, description, period
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["type"],
                    record["date"],
                    record["wallet_id"],
                    record.get("transfer_id"),
                    record["amount_original"],
                    record["currency"],
                    record["rate_at_operation"],
                    record["amount_base"],
                    record.get("category", "General"),
                    record.get("description", ""),
                    record.get("period"),
                ),
            )

        conn.commit()
    finally:
        conn.close()


def _wallet(
    wallet_id: int,
    *,
    name: str = "Wallet",
    currency: str = "KZT",
    initial_balance: float = 0.0,
    is_active: int = 1,
) -> dict:
    return {
        "id": wallet_id,
        "name": name,
        "currency": currency,
        "initial_balance": initial_balance,
        "system": 1 if wallet_id == 1 else 0,
        "allow_negative": 0,
        "is_active": is_active,
    }


def _record(
    record_id: int,
    *,
    record_type: str,
    date: str,
    wallet_id: int,
    amount_base: float,
    category: str = "General",
    transfer_id: int | None = None,
) -> dict:
    return {
        "id": record_id,
        "type": record_type,
        "date": date,
        "wallet_id": wallet_id,
        "transfer_id": transfer_id,
        "amount_original": amount_base,
        "currency": "KZT",
        "rate_at_operation": 1.0,
        "amount_base": amount_base,
        "category": category,
        "description": "",
        "period": "monthly" if record_type == "mandatory_expense" else None,
    }


def _transfer(
    transfer_id: int,
    *,
    from_wallet_id: int,
    to_wallet_id: int,
    date: str,
    amount_base: float,
) -> dict:
    return {
        "id": transfer_id,
        "from_wallet_id": from_wallet_id,
        "to_wallet_id": to_wallet_id,
        "date": date,
        "amount_original": amount_base,
        "currency": "KZT",
        "rate_at_operation": 1.0,
        "amount_base": amount_base,
        "description": "Transfer",
    }


def _make_repo(tmp_path: Path, *, name: str = "balance.db") -> SQLiteRecordRepository:
    return SQLiteRecordRepository(str(tmp_path / name), schema_path=_schema_path())


def _build_repo(
    tmp_path: Path,
    *,
    wallets: list[dict] | None = None,
    records: list[dict] | None = None,
    transfers: list[dict] | None = None,
    name: str = "balance.db",
) -> SQLiteRecordRepository:
    build_test_db(
        tmp_path / name,
        wallets=wallets or [],
        records=records or [],
        transfers=transfers or [],
    )
    return _make_repo(tmp_path, name=name)


def _count_rows(repo: SQLiteRecordRepository, table: str) -> int:
    row = repo.query_one(f"SELECT COUNT(*) FROM {table}")
    assert row is not None
    return int(row[0])


def test_get_wallet_balance_returns_initial_balance_when_no_records(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path, wallets=[_wallet(1, initial_balance=1000.0)])
    try:
        svc = BalanceService(repo)
        assert svc.get_wallet_balance(1) == 1000.0
    finally:
        repo.close()


def test_get_wallet_balance_converts_multi_currency_initial_balance_to_kzt(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, currency="USD", initial_balance=10.0)],
        name="balance_fx.db",
    )
    try:
        svc = BalanceService(repo, CurrencyService())
        assert svc.get_wallet_balance(1) == 5000.0
    finally:
        repo.close()


def test_get_wallet_balance_adds_income_records(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=1000.0)],
        records=[
            _record(1, record_type="income", date="2026-01-01", wallet_id=1, amount_base=200.0),
            _record(2, record_type="income", date="2026-01-02", wallet_id=1, amount_base=50.0),
        ],
    )
    try:
        svc = BalanceService(repo)
        assert svc.get_wallet_balance(1) == 1250.0
    finally:
        repo.close()


def test_get_wallet_balance_subtracts_expense_records(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=1000.0)],
        records=[
            _record(1, record_type="expense", date="2026-01-01", wallet_id=1, amount_base=120.0),
            _record(
                2,
                record_type="mandatory_expense",
                date="2026-01-02",
                wallet_id=1,
                amount_base=30.0,
                category="Mandatory",
            ),
        ],
    )
    try:
        svc = BalanceService(repo)
        assert svc.get_wallet_balance(1) == 850.0
    finally:
        repo.close()


def test_get_wallet_balance_respects_inclusive_date_filter(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=1000.0)],
        records=[
            _record(1, record_type="income", date="2026-01-01", wallet_id=1, amount_base=200.0),
            _record(2, record_type="expense", date="2026-01-10", wallet_id=1, amount_base=50.0),
            _record(3, record_type="income", date="2026-01-20", wallet_id=1, amount_base=500.0),
        ],
    )
    try:
        svc = BalanceService(repo)
        assert svc.get_wallet_balance(1, date="2026-01-10") == 1150.0
    finally:
        repo.close()


def test_get_total_balance_is_unchanged_by_transfer_between_wallets(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[
            _wallet(1, name="Cash", initial_balance=1000.0),
            _wallet(2, name="Card", initial_balance=500.0),
        ],
        transfers=[
            _transfer(1, from_wallet_id=1, to_wallet_id=2, date="2026-01-05", amount_base=300.0)
        ],
        records=[
            _record(
                1,
                record_type="expense",
                date="2026-01-05",
                wallet_id=1,
                amount_base=300.0,
                category="Transfer",
                transfer_id=1,
            ),
            _record(
                2,
                record_type="income",
                date="2026-01-05",
                wallet_id=2,
                amount_base=300.0,
                category="Transfer",
                transfer_id=1,
            ),
        ],
    )
    try:
        svc = BalanceService(repo)
        assert svc.get_total_balance(date="2026-01-04") == 1500.0
        assert svc.get_total_balance(date="2026-01-05") == 1500.0
    finally:
        repo.close()


def test_get_wallet_balances_excludes_inactive_wallets(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[
            _wallet(1, name="Active", initial_balance=100.0, is_active=1),
            _wallet(2, name="Inactive", initial_balance=999.0, is_active=0),
        ],
    )
    try:
        svc = BalanceService(repo)
        balances = svc.get_wallet_balances()
        assert balances == [
            WalletBalance(wallet_id=1, name="Active", currency="KZT", balance=100.0)
        ]
    finally:
        repo.close()


def test_total_balance_matches_sum_of_individual_wallet_balances(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[
            _wallet(1, name="Cash", initial_balance=100.0),
            _wallet(2, name="Card", initial_balance=200.0),
        ],
        records=[
            _record(1, record_type="income", date="2026-02-01", wallet_id=1, amount_base=50.0),
            _record(2, record_type="expense", date="2026-02-01", wallet_id=2, amount_base=30.0),
        ],
    )
    try:
        svc = BalanceService(repo)
        expected = svc.get_wallet_balance(1) + svc.get_wallet_balance(2)
        assert svc.get_total_balance() == expected
    finally:
        repo.close()


def test_get_cashflow_returns_income_expenses_and_net(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=0.0)],
        records=[
            _record(1, record_type="income", date="2026-03-01", wallet_id=1, amount_base=400.0),
            _record(2, record_type="expense", date="2026-03-02", wallet_id=1, amount_base=150.0),
            _record(
                3,
                record_type="mandatory_expense",
                date="2026-03-03",
                wallet_id=1,
                amount_base=50.0,
                category="Mandatory",
            ),
        ],
    )
    try:
        svc = BalanceService(repo)
        result = svc.get_cashflow("2026-03-01", "2026-03-31")
        assert result.income == 400.0
        assert result.expenses == 200.0
        assert result.cashflow == 200.0
    finally:
        repo.close()


def test_get_cashflow_excludes_transfer_category_records(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=0.0), _wallet(2, initial_balance=0.0)],
        transfers=[
            _transfer(1, from_wallet_id=1, to_wallet_id=2, date="2026-03-10", amount_base=500.0)
        ],
        records=[
            _record(1, record_type="income", date="2026-03-01", wallet_id=1, amount_base=1000.0),
            _record(
                2,
                record_type="expense",
                date="2026-03-10",
                wallet_id=1,
                amount_base=500.0,
                category="Transfer",
                transfer_id=1,
            ),
            _record(
                3,
                record_type="income",
                date="2026-03-10",
                wallet_id=2,
                amount_base=500.0,
                category="Transfer",
                transfer_id=1,
            ),
            _record(4, record_type="expense", date="2026-03-15", wallet_id=1, amount_base=100.0),
        ],
    )
    try:
        svc = BalanceService(repo)
        result = svc.get_cashflow("2026-03-01", "2026-03-31")
        assert result.income == 1000.0
        assert result.expenses == 100.0
        assert result.cashflow == 900.0
    finally:
        repo.close()


def test_get_cashflow_keeps_regular_category_named_transfer(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=0.0)],
        records=[
            _record(1, record_type="income", date="2026-03-01", wallet_id=1, amount_base=1000.0),
            _record(
                2,
                record_type="expense",
                date="2026-03-12",
                wallet_id=1,
                amount_base=250.0,
                category="Transfer",
            ),
        ],
        name="balance_transfer_category.db",
    )
    try:
        svc = BalanceService(repo)
        result = svc.get_cashflow("2026-03-01", "2026-03-31")
        assert result.income == 1000.0
        assert result.expenses == 250.0
        assert result.cashflow == 750.0
    finally:
        repo.close()


def test_get_income_filters_by_date_range(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=0.0)],
        records=[
            _record(1, record_type="income", date="2026-01-01", wallet_id=1, amount_base=10.0),
            _record(2, record_type="income", date="2026-02-10", wallet_id=1, amount_base=20.0),
            _record(3, record_type="income", date="2026-03-01", wallet_id=1, amount_base=30.0),
        ],
    )
    try:
        svc = BalanceService(repo)
        assert svc.get_income("2026-02-01", "2026-02-28") == 20.0
    finally:
        repo.close()


def test_get_expenses_includes_mandatory_expense_type(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[_wallet(1, initial_balance=0.0)],
        records=[
            _record(1, record_type="expense", date="2026-04-01", wallet_id=1, amount_base=70.0),
            _record(
                2,
                record_type="mandatory_expense",
                date="2026-04-02",
                wallet_id=1,
                amount_base=30.0,
                category="Mandatory",
            ),
        ],
    )
    try:
        svc = BalanceService(repo)
        assert svc.get_expenses("2026-04-01", "2026-04-30") == 100.0
    finally:
        repo.close()


def test_balance_service_handles_empty_database(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, name="empty.db")
    try:
        svc = BalanceService(repo)
        assert svc.get_wallet_balance(1) == 0.0
        assert svc.get_wallet_balances() == []
        assert svc.get_total_balance() == 0.0
        cashflow = svc.get_cashflow("2026-01-01", "2026-12-31")
        assert cashflow.income == 0.0
        assert cashflow.expenses == 0.0
        assert cashflow.cashflow == 0.0
        assert svc.get_income("2026-01-01", "2026-12-31") == 0.0
        assert svc.get_expenses("2026-01-01", "2026-12-31") == 0.0
    finally:
        repo.close()


def test_balance_service_does_not_write_to_db(tmp_path: Path) -> None:
    repo = _build_repo(
        tmp_path,
        wallets=[
            _wallet(1, name="Cash", initial_balance=100.0),
            _wallet(2, name="Card", initial_balance=200.0),
        ],
        transfers=[
            _transfer(1, from_wallet_id=1, to_wallet_id=2, date="2026-05-03", amount_base=25.0)
        ],
        records=[
            _record(1, record_type="income", date="2026-05-01", wallet_id=1, amount_base=50.0),
            _record(2, record_type="expense", date="2026-05-02", wallet_id=1, amount_base=10.0),
            _record(
                3,
                record_type="expense",
                date="2026-05-03",
                wallet_id=1,
                amount_base=25.0,
                category="Transfer",
                transfer_id=1,
            ),
            _record(
                4,
                record_type="income",
                date="2026-05-03",
                wallet_id=2,
                amount_base=25.0,
                category="Transfer",
                transfer_id=1,
            ),
            _record(
                5,
                record_type="mandatory_expense",
                date="2026-05-04",
                wallet_id=2,
                amount_base=5.0,
                category="Mandatory",
            ),
        ],
    )
    try:
        tables = ("wallets", "records", "transfers")
        before = {table: _count_rows(repo, table) for table in tables}
        svc = BalanceService(repo)
        svc.get_wallet_balance(1)
        svc.get_wallet_balances()
        svc.get_total_balance()
        svc.get_cashflow("2026-01-01", "2026-12-31")
        svc.get_income("2026-01-01", "2026-12-31")
        svc.get_expenses("2026-01-01", "2026-12-31")
        after = {table: _count_rows(repo, table) for table in tables}
        assert before == after
    finally:
        repo.close()
