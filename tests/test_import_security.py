from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services import CurrencyService
from domain.import_policy import ImportPolicy
from gui.controllers import FinancialController
from infrastructure.sqlite_repository import SQLiteRecordRepository
from utils import csv_utils, excel_utils
from utils.csv_utils import DATA_HEADERS, import_records_from_csv
from utils.excel_utils import import_records_from_xlsx


def _write_csv(path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=DATA_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def test_import_csv_rejects_transfer_with_invalid_currency() -> None:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        path = tmp.name
    try:
        _write_csv(
            path,
            [
                {
                    "date": "2025-01-10",
                    "type": "transfer",
                    "wallet_id": "",
                    "category": "Transfer",
                    "amount_original": 100,
                    "currency": "USDTT",
                    "rate_at_operation": 1,
                    "amount_base": 100,
                    "description": "",
                    "period": "",
                    "transfer_id": 1,
                    "from_wallet_id": 1,
                    "to_wallet_id": 2,
                }
            ],
        )

        records, _, summary = import_records_from_csv(
            str(path), policy=ImportPolicy.FULL_BACKUP, wallet_ids={1, 2}
        )
        assert records == []
        assert summary[0] == 0
        assert summary[1] == 1
        assert "invalid currency" in summary[2][0]
    finally:
        try:
            os.unlink(path)
        except PermissionError:
            pass


def test_import_csv_detects_duplicate_initial_balance_rows() -> None:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        path = tmp.name
    try:
        _write_csv(
            path,
            [
                {"date": "", "type": "initial_balance", "amount_original": 10.0},
                {"date": "", "type": "initial_balance", "amount_original": 20.0},
            ],
        )

        _, initial_balance, summary = import_records_from_csv(
            str(path), policy=ImportPolicy.FULL_BACKUP
        )
        assert initial_balance == 10.0
        assert summary[1] == 1
        assert "duplicate initial_balance" in summary[2][0]
    finally:
        try:
            os.unlink(path)
        except PermissionError:
            pass


def test_import_csv_detects_transfer_pair_amount_mismatch() -> None:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        path = tmp.name
    try:
        _write_csv(
            path,
            [
                {
                    "date": "2025-02-01",
                    "type": "expense",
                    "wallet_id": 1,
                    "category": "Transfer",
                    "amount_original": 100,
                    "currency": "USD",
                    "rate_at_operation": 500,
                    "amount_base": 50000,
                    "description": "",
                    "period": "",
                    "transfer_id": 10,
                    "from_wallet_id": "",
                    "to_wallet_id": "",
                },
                {
                    "date": "2025-02-01",
                    "type": "income",
                    "wallet_id": 2,
                    "category": "Transfer",
                    "amount_original": 90,
                    "currency": "USD",
                    "rate_at_operation": 500,
                    "amount_base": 45000,
                    "description": "",
                    "period": "",
                    "transfer_id": 10,
                    "from_wallet_id": "",
                    "to_wallet_id": "",
                },
            ],
        )

        records, _, summary = import_records_from_csv(
            str(path), policy=ImportPolicy.FULL_BACKUP, wallet_ids={1, 2}
        )
        assert len(records) == 2
        assert summary[1] > 0
        assert any("linked records amount_original mismatch" in e for e in summary[2])
    finally:
        try:
            os.unlink(path)
        except PermissionError:
            pass


def test_import_csv_enforces_row_limit(monkeypatch) -> None:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        path = tmp.name
    try:
        _write_csv(
            path,
            [
                {
                    "date": "2025-01-01",
                    "type": "income",
                    "wallet_id": 1,
                    "category": "Salary",
                    "amount_original": 1,
                    "currency": "KZT",
                    "rate_at_operation": 1,
                    "amount_base": 1,
                    "description": "",
                    "period": "",
                    "transfer_id": "",
                    "from_wallet_id": "",
                    "to_wallet_id": "",
                },
                {
                    "date": "2025-01-02",
                    "type": "income",
                    "wallet_id": 1,
                    "category": "Salary",
                    "amount_original": 1,
                    "currency": "KZT",
                    "rate_at_operation": 1,
                    "amount_base": 1,
                    "description": "",
                    "period": "",
                    "transfer_id": "",
                    "from_wallet_id": "",
                    "to_wallet_id": "",
                },
            ],
        )
        monkeypatch.setattr(csv_utils, "MAX_IMPORT_ROWS", 1)

        with pytest.raises(ValueError, match="row limit"):
            import_records_from_csv(str(path), policy=ImportPolicy.FULL_BACKUP, wallet_ids={1})
    finally:
        try:
            os.unlink(path)
        except PermissionError:
            pass


def test_import_xlsx_enforces_row_limit(monkeypatch) -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        path = tmp.name
    try:
        wb = Workbook()
        ws = wb.active
        if ws is not None:
            ws.title = "Data"
            ws.append(excel_utils.DATA_HEADERS)
            ws.append(
                [
                    "2025-01-01",
                    "income",
                    1,
                    "Salary",
                    1,
                    "KZT",
                    1,
                    1,
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            ws.append(
                [
                    "2025-01-02",
                    "income",
                    1,
                    "Salary",
                    1,
                    "KZT",
                    1,
                    1,
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
        wb.save(path)
        wb.close()

        monkeypatch.setattr(excel_utils, "MAX_IMPORT_ROWS", 1)
        with pytest.raises(ValueError, match="row limit"):
            import_records_from_xlsx(str(path), policy=ImportPolicy.FULL_BACKUP, wallet_ids={1})
    finally:
        try:
            os.unlink(path)
        except PermissionError:
            pass


def test_import_controller_dry_run_enforces_parser_row_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "security.db"), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService(use_online=False))
    controller.set_system_initial_balance(0.0)
    wallet = controller.create_wallet(
        name="Cash",
        currency="KZT",
        initial_balance=0.0,
        allow_negative=False,
    )
    path = tmp_path / "security.csv"
    _write_csv(
        path,
        [
            {
                "date": "2025-01-01",
                "type": "income",
                "wallet_id": wallet.id,
                "category": "Salary",
                "amount_original": 1,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 1,
                "description": "",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            },
            {
                "date": "2025-01-02",
                "type": "income",
                "wallet_id": wallet.id,
                "category": "Salary",
                "amount_original": 1,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 1,
                "description": "",
                "period": "",
                "transfer_id": "",
                "from_wallet_id": "",
                "to_wallet_id": "",
            },
        ],
    )
    monkeypatch.setattr("services.importing.parser.MAX_IMPORT_ROWS", 1)

    try:
        with pytest.raises(ValueError, match="row limit"):
            controller.import_records(
                "CSV",
                str(path),
                ImportPolicy.FULL_BACKUP,
                dry_run=True,
            )
        assert repo.load_all() == []
    finally:
        repo.close()
