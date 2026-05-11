from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import bootstrap
from backup import create_backup, export_to_json
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.records import IncomeRecord, MandatoryExpenseRecord
from domain.wallets import Wallet
from infrastructure.repositories import JsonFileRecordRepository
from infrastructure.sqlite_repository import SQLiteRecordRepository


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def test_create_backup_creates_timestamped_copy(tmp_path) -> None:
    src = tmp_path / "data.json"
    src.write_text('{"records": []}', encoding="utf-8")

    backup_path = create_backup(str(src))
    assert backup_path is not None
    backup = Path(backup_path)
    assert backup.exists()
    assert backup.name.startswith("data_backup_")
    assert backup.suffix == ".json"


def test_export_to_json_from_sqlite(tmp_path) -> None:
    sqlite_path = tmp_path / "finance.db"
    json_path = tmp_path / "data.json"
    schema = _schema_path()

    repo = SQLiteRecordRepository(str(sqlite_path), schema_path=schema)
    repo.save_wallet(
        Wallet(
            id=1,
            name="Main wallet",
            currency="KZT",
            initial_balance=1000.0,
            system=True,
            allow_negative=False,
            is_active=True,
        )
    )
    repo.save(
        IncomeRecord(
            id=1,
            date="2020-02-28",
            wallet_id=1,
            amount_original=100.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=100.0,
            category="Salary",
        )
    )
    repo.save_mandatory_expense(
        MandatoryExpenseRecord(
            id=1,
            wallet_id=1,
            date="2020-03-12",
            amount_original=25.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=25.0,
            category="Mandatory",
            description="Gym",
            period="monthly",
            auto_pay=True,
        )
    )
    repo.execute(
        """
        INSERT INTO distribution_items (name, group_name, sort_order, pct, pct_minor, is_active)
        VALUES ('Investments', '', 0, 100.0, 10000, 1)
        """
    )
    repo.execute(
        """
        INSERT INTO budgets (
            id, category, start_date, end_date,
            limit_base, limit_base_minor, include_mandatory
        )
        VALUES (1, 'Food', '2020-03-01', '2020-03-31', 300.0, 30000, 1)
        """
    )
    repo.save_debt(
        Debt(
            id=1,
            contact_name="Alice",
            kind=DebtKind.DEBT,
            total_amount_minor=50000,
            remaining_amount_minor=30000,
            currency="KZT",
            interest_rate=0.0,
            status=DebtStatus.OPEN,
            created_at="2020-03-01",
        )
    )
    repo.save_debt_payment(
        DebtPayment(
            id=1,
            debt_id=1,
            record_id=1,
            operation_type=DebtOperationType.DEBT_REPAY,
            principal_paid_minor=20000,
            is_write_off=False,
            payment_date="2020-03-05",
        )
    )
    repo.commit()
    repo.close()

    export_to_json(str(sqlite_path), str(json_path), schema_path=schema)

    repo = JsonFileRecordRepository(str(json_path))
    wallets = repo.load_wallets()
    records = repo.load_all()
    mandatory = repo.load_mandatory_expenses()
    assert len(wallets) == 1
    assert len(records) == 1
    assert len(mandatory) == 1
    assert wallets[0].id == 1
    assert records[0].id == 1
    assert str(mandatory[0].date) == "2020-03-12"
    assert mandatory[0].auto_pay is True
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["budgets"][0]["category"] == "Food"
    assert payload["budgets"][0]["include_mandatory"] is True
    assert payload["debts"][0]["contact_name"] == "Alice"
    assert payload["debts"][0]["remaining_amount_minor"] == 30000
    assert payload["debt_payments"][0]["operation_type"] == "debt_repay"
    assert payload["debt_payments"][0]["record_id"] == 1
    snapshot = payload["distribution_snapshots"][0]
    assert snapshot["month"] == "2020-02"
    item_keys = [key for key in snapshot["values_by_column"] if key.startswith("item_")]
    assert len(item_keys) == 1
    assert snapshot["values_by_column"][item_keys[0]] == "100"


def test_export_to_json_preserves_custom_tag_colors(tmp_path) -> None:
    sqlite_path = tmp_path / "finance.db"
    json_path = tmp_path / "data.json"
    schema = _schema_path()

    repo = SQLiteRecordRepository(str(sqlite_path), schema_path=schema)
    repo.save_wallet(
        Wallet(
            id=1,
            name="Main wallet",
            currency="KZT",
            initial_balance=0.0,
            system=True,
            allow_negative=False,
            is_active=True,
        )
    )
    repo.save(
        IncomeRecord(
            id=1,
            date="2020-02-28",
            wallet_id=1,
            amount_original=100.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=100.0,
            category="Salary",
            tags=("coursework",),
        )
    )
    repo.set_tag_color("coursework", "#9B51E0")
    repo.commit()
    repo.close()

    export_to_json(str(sqlite_path), str(json_path), schema_path=schema)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["tags"] == [
        {
            "id": 1,
            "name": "coursework",
            "color": "#9B51E0",
            "usage_count": 1,
            "last_used_at": "2020-02-28",
        }
    ]


def test_export_to_json_can_skip_autofreeze_for_background_export(tmp_path) -> None:
    sqlite_path = tmp_path / "finance.db"
    json_path = tmp_path / "data.json"
    schema = _schema_path()

    repo = SQLiteRecordRepository(str(sqlite_path), schema_path=schema)
    repo.save_wallet(
        Wallet(
            id=1,
            name="Main wallet",
            currency="KZT",
            initial_balance=0.0,
            system=True,
            allow_negative=False,
            is_active=True,
        )
    )
    repo.save(
        IncomeRecord(
            id=1,
            date="2020-02-28",
            wallet_id=1,
            amount_original=100.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=100.0,
            category="Salary",
        )
    )
    repo.execute(
        """
        INSERT INTO distribution_items (name, group_name, sort_order, pct, pct_minor, is_active)
        VALUES ('Investments', '', 0, 100.0, 10000, 1)
        """
    )
    repo.commit()
    repo.close()

    export_to_json(
        str(sqlite_path),
        str(json_path),
        schema_path=schema,
        autofreeze_closed_months=False,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["distribution_snapshots"] == []


def test_export_in_background_logs_unexpected_backup_copy_failure(monkeypatch, caplog) -> None:
    started: dict[str, Any] = {}

    class InlineThread:
        def __init__(self, target, daemon):
            started["target"] = target
            started["daemon"] = daemon

        def start(self):
            started["started"] = True
            started["target"]()

    monkeypatch.setattr(bootstrap, "export_to_json", lambda *args, **kwargs: None)

    def _raise_os_error(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(bootstrap, "create_backup", _raise_os_error)
    monkeypatch.setattr(threading, "Thread", InlineThread)

    with caplog.at_level("ERROR"):
        bootstrap._export_in_background()

    assert started["daemon"] is True
    assert started["started"] is True
    assert "Background JSON export failed" in caplog.text


def test_export_to_json_uses_consistent_sqlite_snapshot(tmp_path, monkeypatch) -> None:
    sqlite_path = tmp_path / "finance_snapshot.db"
    json_path = tmp_path / "data.json"
    schema = _schema_path()

    repo = SQLiteRecordRepository(str(sqlite_path), schema_path=schema)
    repo.save_wallet(
        Wallet(
            id=1,
            name="Main wallet",
            currency="KZT",
            initial_balance=0.0,
            system=True,
            allow_negative=False,
            is_active=True,
        )
    )
    repo.commit()
    repo.close()

    original_load_assets = SQLiteRecordRepository.load_assets
    mutated = False

    def _load_assets_and_mutate(self, *args, **kwargs):
        nonlocal mutated
        result = original_load_assets(self, *args, **kwargs)
        if not mutated:
            mutated = True
            conn = sqlite3.connect(sqlite_path)
            try:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute(
                    """
                    INSERT INTO asset_snapshots (
                        id, asset_id, snapshot_date, value_minor, currency, note
                    )
                    VALUES (1, 999, '2026-04-01', 100, 'KZT', 'late write')
                    """
                )
                conn.commit()
            finally:
                conn.close()
        return result

    monkeypatch.setattr(SQLiteRecordRepository, "load_assets", _load_assets_and_mutate)

    export_to_json(str(sqlite_path), str(json_path), schema_path=schema)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["assets"] == []
    assert payload["asset_snapshots"] == []


def test_prune_backups(tmp_path):
    """Test that _prune_backups keeps only the most recent files."""

    from backup import _prune_backups

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    source_stem = "data"
    source_suffix = ".json"

    # Create 4 backup files with timestamps (oldest to newest)
    timestamps = [
        "20250101_120000",  # oldest
        "20250102_120000",
        "20250103_120000",
        "20250104_120000",  # newest
    ]
    for ts in timestamps:
        path = backup_dir / f"{source_stem}_backup_{ts}{source_suffix}"
        path.write_text('{"test": 1}')

    # Also create a stray file that doesn't match the pattern
    stray = backup_dir / "other_backup_20250101_120000.json"
    stray.write_text("{}")

    # Keep last 2
    _prune_backups(backup_dir, source_stem=source_stem, source_suffix=source_suffix, keep_last=2)

    remaining = list(backup_dir.glob(f"{source_stem}_backup_*{source_suffix}"))
    assert len(remaining) == 2
    # Should keep the two newest timestamps
    remaining_names = [p.name for p in remaining]
    assert "data_backup_20250103_120000.json" in remaining_names
    assert "data_backup_20250104_120000.json" in remaining_names
    # Stray file should remain untouched
    assert stray.exists()


def test_prune_backups_keep_zero_removes_all_matching(tmp_path):
    from backup import _prune_backups

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for ts in ("20250101_120000", "20250102_120000"):
        (backup_dir / f"data_backup_{ts}.json").write_text("{}", encoding="utf-8")

    _prune_backups(backup_dir, source_stem="data", source_suffix=".json", keep_last=0)

    assert list(backup_dir.glob("data_backup_*.json")) == []


def test_create_backup_skips_creation_when_keep_zero(tmp_path):
    src = tmp_path / "data.json"
    src.write_text('{"records": []}', encoding="utf-8")

    backup_path = create_backup(str(src), keep_last=0)

    assert backup_path is None
    assert not (tmp_path / "backups").exists()


def test_create_backup_cleans_temp_file_when_replace_fails(tmp_path):
    import backup

    src = tmp_path / "data.json"
    src.write_text('{"records": []}', encoding="utf-8")

    with patch.object(backup.os, "replace", side_effect=OSError("disk busy")):
        with pytest.raises(OSError, match="disk busy"):
            create_backup(str(src))

    backup_dir = tmp_path / "backups"
    assert backup_dir.exists()
    assert list(backup_dir.glob("data_backup_*.json")) == []
    assert list(backup_dir.glob(".data_backup_*.json")) == []
