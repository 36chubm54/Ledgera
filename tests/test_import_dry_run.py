from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.services import CurrencyService
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from gui.controllers import FinancialController
from infrastructure.sqlite_repository import SQLiteRecordRepository
from utils.backup_utils import BackupReadonlyError, export_full_backup_to_json
from utils.csv_utils import DATA_HEADERS


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def _make_controller(db_path: Path) -> tuple[SQLiteRecordRepository, FinancialController, int, int]:
    repo = SQLiteRecordRepository(str(db_path), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService(use_online=False))
    controller.set_system_initial_balance(1000.0)
    cash = controller.create_wallet(
        name="Cash",
        currency="KZT",
        initial_balance=500.0,
        allow_negative=False,
    )
    card = controller.create_wallet(
        name="Card",
        currency="KZT",
        initial_balance=200.0,
        allow_negative=False,
    )
    return repo, controller, int(cash.id), int(card.id)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DATA_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_dry_run_valid_csv_returns_preview_without_writing(tmp_path: Path) -> None:
    repo, controller, cash_id, _ = _make_controller(tmp_path / "dry_run_valid.db")
    csv_path = tmp_path / "valid.csv"
    _write_csv(
        csv_path,
        [
            {
                "date": "2026-03-01",
                "type": "income",
                "wallet_id": cash_id,
                "category": "Salary",
                "amount_original": 100,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 100,
                "description": "Payroll",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            }
        ],
    )
    try:
        result = controller.import_records(
            "CSV",
            str(csv_path),
            ImportPolicy.FULL_BACKUP,
            dry_run=True,
        )
        assert result == ImportResult(imported=1, skipped=0, errors=(), dry_run=True)
        assert repo.load_all() == []
    finally:
        repo.close()


def test_dry_run_invalid_rows_returns_errors_without_writing(tmp_path: Path) -> None:
    repo, controller, cash_id, _ = _make_controller(tmp_path / "dry_run_invalid.db")
    csv_path = tmp_path / "invalid.csv"
    _write_csv(
        csv_path,
        [
            {
                "date": "2026-13-01",
                "type": "income",
                "wallet_id": cash_id,
                "category": "Salary",
                "amount_original": 100,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 100,
                "description": "Broken",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            }
        ],
    )
    try:
        result = controller.import_records(
            "CSV",
            str(csv_path),
            ImportPolicy.FULL_BACKUP,
            dry_run=True,
        )
        assert result.imported == 0
        assert result.skipped == 1
        assert result.errors
        assert repo.load_all() == []
    finally:
        repo.close()


def test_regular_import_writes_records_to_database(tmp_path: Path) -> None:
    repo, controller, cash_id, _ = _make_controller(tmp_path / "real_import.db")
    csv_path = tmp_path / "real.csv"
    _write_csv(
        csv_path,
        [
            {
                "date": "2026-03-01",
                "type": "income",
                "wallet_id": cash_id,
                "category": "Salary",
                "amount_original": 100,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 100,
                "description": "Payroll",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            }
        ],
    )
    try:
        result = controller.import_records("CSV", str(csv_path), ImportPolicy.FULL_BACKUP)
        assert result == ImportResult(imported=1, skipped=0, errors=())
        assert len(repo.load_all()) == 1
    finally:
        repo.close()


def test_dry_run_followed_by_real_import_keeps_database_unchanged_until_commit(
    tmp_path: Path,
) -> None:
    repo, controller, cash_id, card_id = _make_controller(tmp_path / "two_step.db")
    csv_path = tmp_path / "two_step.csv"
    _write_csv(
        csv_path,
        [
            {
                "date": "2026-03-01",
                "type": "income",
                "wallet_id": cash_id,
                "category": "Salary",
                "amount_original": 100,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 100,
                "description": "Payroll",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            },
            {
                "date": "2026-03-02",
                "type": "expense",
                "wallet_id": card_id,
                "category": "Food",
                "amount_original": 50,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 50,
                "description": "Lunch",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            },
        ],
    )
    try:
        preview = controller.import_records(
            "CSV",
            str(csv_path),
            ImportPolicy.FULL_BACKUP,
            dry_run=True,
        )
        assert preview == ImportResult(imported=2, skipped=0, errors=(), dry_run=True)
        assert repo.load_all() == []

        result = controller.import_records("CSV", str(csv_path), ImportPolicy.FULL_BACKUP)
        assert result == ImportResult(imported=2, skipped=0, errors=())
        records = repo.load_all()
        assert len(records) == 2
        assert {record.category for record in records} == {"Salary", "Food"}
    finally:
        repo.close()


def test_real_csv_import_preserves_source_row_order_after_id_normalization(
    tmp_path: Path,
) -> None:
    repo, controller, cash_id, card_id = _make_controller(tmp_path / "order_preserved.db")
    csv_path = tmp_path / "order_preserved.csv"
    _write_csv(
        csv_path,
        [
            {
                "date": "2026-03-05",
                "type": "expense",
                "wallet_id": cash_id,
                "category": "Food",
                "amount_original": 50,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 50,
                "description": "Lunch",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            },
            {
                "date": "2026-03-01",
                "type": "transfer",
                "wallet_id": "",
                "category": "Transfer",
                "amount_original": 25,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 25,
                "description": "Move",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": cash_id,
                "to_wallet_id": card_id,
            },
            {
                "date": "2026-03-10",
                "type": "income",
                "wallet_id": card_id,
                "category": "Salary",
                "amount_original": 100,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 100,
                "description": "Payroll",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            },
        ],
    )
    try:
        result = controller.import_records("CSV", str(csv_path), ImportPolicy.FULL_BACKUP)
        assert result == ImportResult(imported=3, skipped=0, errors=())
        records = repo.load_all()
        assert [record.category for record in records] == ["Food", "Transfer", "Transfer", "Salary"]
        assert [record.transfer_id for record in records] == [None, 1, 1, None]
        assert [str(record.date) for record in records] == [
            "2026-03-05",
            "2026-03-01",
            "2026-03-01",
            "2026-03-10",
        ]
        items = controller.build_record_list_items()
        assert [item.type_label for item in items] == ["Expense", "Transfer", "Income"]
        assert [item.invariant_id for item in items] == [1, 2, 3]
        assert [item.repository_index for item in items] == [0, 1, 3]
    finally:
        repo.close()


def test_readonly_snapshot_dry_run_without_force_raises_and_does_not_write(
    tmp_path: Path,
) -> None:
    repo, controller, _, _ = _make_controller(tmp_path / "readonly.db")
    backup_path = tmp_path / "readonly.json"
    export_full_backup_to_json(
        str(backup_path),
        wallets=repo.load_wallets(),
        records=[],
        mandatory_expenses=[],
        transfers=[],
        readonly=True,
    )
    try:
        with pytest.raises(BackupReadonlyError):
            controller.import_records(
                "JSON",
                str(backup_path),
                ImportPolicy.FULL_BACKUP,
                dry_run=True,
            )
        assert repo.load_all() == []
    finally:
        repo.close()


def test_dry_run_with_zero_imported_records_returns_zero_and_does_not_write(
    tmp_path: Path,
) -> None:
    repo, controller, _, _ = _make_controller(tmp_path / "zero_import.db")
    csv_path = tmp_path / "zero.csv"
    _write_csv(
        csv_path,
        [
            {
                "date": "2026-03-01",
                "type": "income",
                "wallet_id": 999,
                "category": "Salary",
                "amount_original": 100,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 100,
                "description": "Missing wallet",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            }
        ],
    )
    try:
        result = controller.import_records(
            "CSV",
            str(csv_path),
            ImportPolicy.FULL_BACKUP,
            dry_run=True,
        )
        assert result.imported == 0
        assert result.skipped == 1
        assert repo.load_all() == []
    finally:
        repo.close()


def test_import_result_summary_has_dry_run_prefix() -> None:
    result = ImportResult(imported=2, skipped=1, errors=("row 2",), dry_run=True)
    assert result.summary().startswith("[DRY-RUN]")


def test_import_result_summary_regular_mode_has_no_dry_run_prefix() -> None:
    result = ImportResult(imported=2, skipped=1, errors=("row 2",), dry_run=False)
    assert "[DRY-RUN]" not in result.summary()
