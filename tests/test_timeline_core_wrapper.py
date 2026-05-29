from __future__ import annotations

import os
import sqlite3
from pathlib import Path

os.environ.setdefault("LEDGERA_ENABLE_RUST_CORE", "1")

from infrastructure.sqlite_repository import SQLiteRecordRepository
from services.analytics import timeline as timeline_module
from services.analytics.timeline import TimelineService
from tests.test_timeline_service import (
    _init_db,
    _insert_record,
    _insert_transfer,
    _insert_wallet,
    _insert_wallet_with_currency,
    _schema_path,
)


def _build_timeline_repo(tmp_path: Path) -> SQLiteRecordRepository:
    db_path = tmp_path / "timeline_core.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_wallet(conn, 1, initial_balance=100.0)
        _insert_wallet(conn, 2, initial_balance=50.0)
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
            date="2026-02-10",
            amount_base=300.0,
        )
        _insert_record(
            conn,
            record_type="expense",
            date="2026-02-10",
            wallet_id=1,
            amount_base=300.0,
            transfer_id=1,
            category="Transfer",
        )
        _insert_record(
            conn,
            record_type="income",
            date="2026-02-10",
            wallet_id=2,
            amount_base=300.0,
            transfer_id=1,
            category="Transfer",
        )
        _insert_record(
            conn,
            record_type="mandatory_expense",
            date="2026-02-15",
            wallet_id=1,
            amount_base=50.0,
            category="Mandatory",
        )
    finally:
        conn.close()
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_timeline_service_rust_path_matches_python_fallback(tmp_path: Path) -> None:
    repo = _build_timeline_repo(tmp_path)
    try:
        rust_service = TimelineService(repo)
        rust_values = (
            rust_service.get_net_worth_timeline(),
            rust_service.get_monthly_cashflow("2026-01-01", "2026-02-28"),
            rust_service.get_cumulative_income_expense(),
        )

        rust_core = timeline_module._RUST_TIMELINE_CORE
        timeline_module._RUST_TIMELINE_CORE = None
        try:
            fallback_service = TimelineService(repo)
            fallback_values = (
                fallback_service.get_net_worth_timeline(),
                fallback_service.get_monthly_cashflow("2026-01-01", "2026-02-28"),
                fallback_service.get_cumulative_income_expense(),
            )
        finally:
            timeline_module._RUST_TIMELINE_CORE = rust_core

        assert rust_values == fallback_values
    finally:
        repo.close()


def test_timeline_service_rust_path_matches_fallback_for_multi_currency_initial_balance(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "timeline_edges.db"
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
        rust_service = TimelineService(repo)
        rust_values = rust_service.get_net_worth_timeline()

        rust_core = timeline_module._RUST_TIMELINE_CORE
        timeline_module._RUST_TIMELINE_CORE = None
        try:
            fallback_values = TimelineService(repo).get_net_worth_timeline()
        finally:
            timeline_module._RUST_TIMELINE_CORE = rust_core

        assert rust_values == fallback_values
    finally:
        repo.close()


def test_timeline_service_rust_path_reads_live_data_after_writes(tmp_path: Path) -> None:
    repo = _build_timeline_repo(tmp_path)
    try:
        service = TimelineService(repo)
        assert service.get_monthly_cashflow("2026-01-01", "2026-02-28")[0].cashflow == 800.0

        repo.execute(
            """
            INSERT INTO records (
                type, date, wallet_id, amount_original, currency,
                rate_at_operation, amount_base, category
            ) VALUES ('expense', '2026-01-20', 1, 25.0, 'KZT', 1.0, 25.0, 'Food')
            """
        )
        repo.commit()

        assert service.get_monthly_cashflow("2026-01-01", "2026-02-28")[0].cashflow == 775.0
    finally:
        repo.close()
