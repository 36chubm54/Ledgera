from __future__ import annotations

from pathlib import Path

import pytest

import bootstrap
from infrastructure.sqlite_repository import SQLiteRecordRepository
from storage.sqlite_storage import SQLiteStorage


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _make_repo(db_path: Path) -> SQLiteRecordRepository:
    return SQLiteRecordRepository(str(db_path), schema_path=_schema_path())


def test_migration_verified_flag_roundtrip(tmp_path) -> None:
    repo = _make_repo(tmp_path / "finance.db")
    try:
        assert bootstrap._is_migration_verified(repo) is False
        bootstrap._mark_migration_verified(repo)
        assert bootstrap._is_migration_verified(repo) is True
    finally:
        repo.close()


def test_validate_sqlite_integrity_only_detects_broken_transfer(tmp_path) -> None:
    repo = _make_repo(tmp_path / "finance.db")
    try:
        repo.execute(
            """
            INSERT INTO wallets (name, currency, initial_balance, system, allow_negative, is_active)
            VALUES ('W1', 'KZT', 0, 1, 0, 1)
            """
        )
        repo.execute(
            """
            INSERT INTO wallets (name, currency, initial_balance, system, allow_negative, is_active)
            VALUES ('W2', 'KZT', 0, 0, 0, 1)
            """
        )
        repo.execute(
            """
            INSERT INTO transfers (
                from_wallet_id, to_wallet_id, date, amount_original, currency,
                rate_at_operation, amount_base, description
            )
            VALUES (1, 2, '2026-03-01', 100, 'KZT', 1, 100, '')
            """
        )
        repo.execute(
            """
            INSERT INTO records (
                type, date, wallet_id, transfer_id, amount_original, currency,
                rate_at_operation, amount_base, category, description, period
            )
            VALUES ('expense', '2026-03-01', 1, 1, 100, 'KZT', 1, 100, 'Transfer', '', NULL)
            """
        )
        repo.commit()

        with pytest.raises(RuntimeError, match="expected 2"):
            bootstrap._validate_sqlite_integrity_only(repo)
    finally:
        repo.close()


def test_bootstrap_marks_existing_sqlite_as_verified_without_json_compare(
    tmp_path, monkeypatch
) -> None:
    sqlite_path = tmp_path / "finance.db"
    storage = SQLiteStorage(str(sqlite_path))
    try:
        storage.initialize_schema(_schema_path())
        storage.execute(
            """
            INSERT INTO wallets (name, currency, initial_balance, system, allow_negative, is_active)
            VALUES ('Main wallet', 'KZT', 0, 1, 0, 1)
            """
        )
        storage.commit()
    finally:
        storage.close()

    monkeypatch.setattr(bootstrap, "SQLITE_PATH", str(sqlite_path))

    repository = bootstrap.bootstrap_repository()

    if isinstance(repository, SQLiteRecordRepository):
        try:
            row = repository.query_one(
                "SELECT value FROM schema_meta WHERE key='migration_verified'"
            )
            assert row is not None
            assert str(row[0]).lower() == "true"
        finally:
            repository.close()


def test_bootstrap_creates_sqlite_and_initializes_system_wallet(tmp_path, monkeypatch) -> None:
    sqlite_path = tmp_path / "finance.db"
    monkeypatch.setattr(bootstrap, "SQLITE_PATH", str(sqlite_path))

    repository = bootstrap.bootstrap_repository()

    if isinstance(repository, SQLiteRecordRepository):
        try:
            assert sqlite_path.exists()
            wallets = repository.load_wallets()
            assert len(wallets) == 1
            assert wallets[0].id == 1
            assert wallets[0].system is True
            assert wallets[0].name == "Main wallet"
        finally:
            repository.close()


def test_validate_sqlite_integrity_only_detects_wrong_transfer_types(tmp_path) -> None:
    repo = _make_repo(tmp_path / "finance.db")
    try:
        repo.execute(
            """
            INSERT INTO wallets (name, currency, initial_balance, system, allow_negative, is_active)
            VALUES ('W1', 'KZT', 0, 1, 0, 1)
            """
        )
        repo.execute(
            """
            INSERT INTO wallets (name, currency, initial_balance, system, allow_negative, is_active)
            VALUES ('W2', 'KZT', 0, 0, 0, 1)
            """
        )
        repo.execute(
            """
            INSERT INTO transfers (
                from_wallet_id, to_wallet_id, date, amount_original, currency,
                rate_at_operation, amount_base, description
            )
            VALUES (1, 2, '2026-03-01', 100, 'KZT', 1, 100, '')
            """
        )
        repo.execute(
            """
            INSERT INTO records (
                type, date, wallet_id, transfer_id, amount_original, currency,
                rate_at_operation, amount_base, category, description, period
            )
            VALUES ('expense', '2026-03-01', 1, 1, 100, 'KZT', 1, 100, 'Transfer', '', NULL)
            """
        )
        repo.execute(
            """
            INSERT INTO records (
                type, date, wallet_id, transfer_id, amount_original, currency,
                rate_at_operation, amount_base, category, description, period
            )
            VALUES ('expense', '2026-03-01', 2, 1, 100, 'KZT', 1, 100, 'Transfer', '', NULL)
            """
        )
        repo.commit()

        with pytest.raises(RuntimeError, match="invalid linked types"):
            bootstrap._validate_sqlite_integrity_only(repo)
    finally:
        repo.close()


def test_latest_sqlite_activity_mtime_prefers_newer_wal_file(tmp_path) -> None:
    sqlite_path = tmp_path / "finance.db"
    sqlite_path.write_text("", encoding="utf-8")
    wal_path = tmp_path / "finance.db-wal"
    wal_path.write_text("", encoding="utf-8")

    sqlite_mtime = 1_700_000_000
    wal_mtime = sqlite_mtime + 120
    sqlite_path.touch()
    wal_path.touch()
    import os

    os.utime(sqlite_path, (sqlite_mtime, sqlite_mtime))
    os.utime(wal_path, (wal_mtime, wal_mtime))

    assert bootstrap._latest_sqlite_activity_mtime(sqlite_path) == wal_mtime


def test_should_export_json_when_wal_is_newer_than_json(tmp_path, monkeypatch) -> None:
    sqlite_path = tmp_path / "finance.db"
    json_path = tmp_path / "data.json"
    wal_path = tmp_path / "finance.db-wal"

    sqlite_path.write_text("", encoding="utf-8")
    json_path.write_text("{}", encoding="utf-8")
    wal_path.write_text("", encoding="utf-8")

    db_mtime = 1_700_000_000
    json_mtime = db_mtime + 60
    wal_mtime = json_mtime + 60

    import os

    os.utime(sqlite_path, (db_mtime, db_mtime))
    os.utime(json_path, (json_mtime, json_mtime))
    os.utime(wal_path, (wal_mtime, wal_mtime))

    monkeypatch.setattr(bootstrap, "SQLITE_PATH", str(sqlite_path))
    monkeypatch.setattr(bootstrap, "JSON_PATH", str(json_path))

    assert bootstrap._should_export_json() is True


def test_initialize_schema_adds_related_debt_id_for_pre_19_records_table(tmp_path) -> None:
    sqlite_path = tmp_path / "legacy_records.db"
    storage = SQLiteStorage(str(sqlite_path))
    try:
        storage.execute(
            """
            CREATE TABLE records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                wallet_id INTEGER NOT NULL,
                transfer_id INTEGER,
                amount_original REAL NOT NULL,
                currency TEXT NOT NULL,
                rate_at_operation REAL NOT NULL,
                amount_base REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                period TEXT
            )
            """
        )
        storage.commit()
        storage.initialize_schema(_schema_path())

        columns = {str(row["name"]) for row in storage.query_all("PRAGMA table_info(records)")}
        assert "related_debt_id" in columns
    finally:
        storage.close()
