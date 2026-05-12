import json
from pathlib import Path

import pytest

from domain.import_policy import ImportPolicy
from services import import_parser
from utils.backup_utils import BackupReadonlyError, compute_checksum


def test_parse_import_file_rejects_large_file(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "big.csv"
    csv_path.write_text("date,type\n2026-01-01,income\n", encoding="utf-8")
    monkeypatch.setattr(import_parser, "MAX_IMPORT_FILE_SIZE", 8)

    with pytest.raises(ValueError, match="too large"):
        import_parser.parse_import_file(str(csv_path))


def test_parse_import_file_rejects_csv_row_limit(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base\n"
        "2026-01-01,income,1,Salary,10,USD,500,5000\n"
        "2026-01-02,income,1,Salary,10,USD,500,5000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(import_parser, "MAX_IMPORT_ROWS", 1)

    with pytest.raises(ValueError, match="row limit"):
        import_parser.parse_import_file(str(csv_path))


def test_parse_import_file_rejects_readonly_snapshot_without_force(tmp_path: Path) -> None:
    data = {
        "wallets": [],
        "records": [],
        "mandatory_expenses": [],
        "transfers": [],
    }
    payload = {
        "meta": {
            "created_at": "2026-03-05T00:00:00Z",
            "app_version": "0.0.0",
            "storage": "json",
            "readonly": True,
            "checksum": compute_checksum(data),
        },
        "data": data,
    }
    json_path = tmp_path / "snapshot.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BackupReadonlyError):
        import_parser.parse_import_file(str(json_path))


def test_parse_import_file_accepts_readonly_snapshot_with_force(tmp_path: Path) -> None:
    data = {
        "wallets": [],
        "records": [],
        "mandatory_expenses": [],
        "transfers": [],
    }
    payload = {
        "meta": {
            "created_at": "2026-03-05T00:00:00Z",
            "app_version": "0.0.0",
            "storage": "json",
            "readonly": True,
            "checksum": compute_checksum(data),
        },
        "data": data,
    }
    json_path = tmp_path / "snapshot.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = import_parser.parse_import_file(str(json_path), force=True)
    assert parsed.file_type == "json"
    assert parsed.rows == []


def test_parse_import_file_keeps_fractional_transfer_aggregate_id_verbatim(tmp_path: Path) -> None:
    payload = {
        "wallets": [
            {
                "id": 1,
                "name": "Main",
                "currency": "KZT",
                "initial_balance": 0.0,
                "system": True,
            }
        ],
        "records": [],
        "mandatory_expenses": [],
        "transfers": [
            {
                "id": "1.5",
                "from_wallet_id": 1,
                "to_wallet_id": 2,
                "date": "2026-03-05",
                "amount_original": 10,
                "currency": "KZT",
                "rate_at_operation": 1,
                "amount_base": 10,
            }
        ],
    }
    json_path = tmp_path / "payload.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = import_parser.parse_import_file(str(json_path))

    assert parsed.rows[0]["transfer_id"] == "1.5"


def test_parse_import_file_reads_distribution_snapshots_from_json(tmp_path: Path) -> None:
    payload = {
        "wallets": [],
        "records": [],
        "mandatory_expenses": [],
        "distribution_snapshots": [
            {
                "month": "2026-03",
                "is_negative": False,
                "column_order": ["month", "fixed", "net_income", "item_1"],
                "headings_by_column": {
                    "month": "Month",
                    "fixed": "Fixed",
                    "net_income": "Net income",
                    "item_1": "Investments",
                },
                "values_by_column": {
                    "month": "2026-03",
                    "fixed": "Yes",
                    "net_income": "100,000",
                    "item_1": "100,000",
                },
            }
        ],
        "transfers": [],
    }
    json_path = tmp_path / "payload.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = import_parser.parse_import_file(str(json_path))

    assert len(parsed.distribution_snapshots) == 1
    assert parsed.distribution_snapshots[0]["month"] == "2026-03"


def test_parse_import_file_reads_distribution_structure_from_json(tmp_path: Path) -> None:
    payload = {
        "wallets": [],
        "records": [],
        "mandatory_expenses": [],
        "distribution_items": [
            {
                "id": 1,
                "name": "Investments",
                "group_name": "",
                "sort_order": 0,
                "pct": 100.0,
                "pct_minor": 10000,
                "is_active": True,
            }
        ],
        "distribution_subitems": [
            {
                "id": 10,
                "item_id": 1,
                "name": "BTC",
                "sort_order": 0,
                "pct": 100.0,
                "pct_minor": 10000,
                "is_active": True,
            }
        ],
        "transfers": [],
    }
    json_path = tmp_path / "payload.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = import_parser.parse_import_file(str(json_path))

    assert len(parsed.distribution_items) == 1
    assert parsed.distribution_items[0]["name"] == "Investments"
    assert len(parsed.distribution_subitems) == 1
    assert parsed.distribution_subitems[0]["name"] == "BTC"


def test_parse_import_file_reads_budgets_from_json(tmp_path: Path) -> None:
    payload = {
        "wallets": [],
        "records": [],
        "mandatory_expenses": [],
        "budgets": [
            {
                "id": 1,
                "category": "Food",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "limit_base": 1500.0,
                "limit_base_minor": 150000,
                "include_mandatory": True,
            }
        ],
        "transfers": [],
    }
    json_path = tmp_path / "payload.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = import_parser.parse_import_file(str(json_path))

    assert len(parsed.budgets) == 1
    assert parsed.budgets[0]["category"] == "Food"
    assert parsed.budgets[0]["include_mandatory"] is True


def test_parse_transfer_row_accepts_legacy_amount_kzt_for_full_backup() -> None:
    rows, transfer, next_transfer_id, error = import_parser.parse_transfer_row(
        {
            "date": "2026-03-05",
            "from_wallet_id": "1",
            "to_wallet_id": "2",
            "amount_original": "10",
            "currency": "USD",
            "rate_at_operation": "500",
            "amount_kzt": "5000",
        },
        row_label="row 1",
        policy=ImportPolicy.FULL_BACKUP,
        get_rate=None,
        next_transfer_id=1,
        wallet_ids={1, 2},
    )

    assert error is None
    assert rows is not None
    assert transfer is not None
    assert transfer.amount_base == pytest.approx(5000.0)
    assert next_transfer_id == 2


def test_parse_import_file_reads_debts_from_json(tmp_path: Path) -> None:
    payload = {
        "wallets": [],
        "records": [
            {
                "id": 10,
                "date": "2026-03-01",
                "type": "expense",
                "wallet_id": 1,
                "related_debt_id": 1,
                "category": "Debt payment",
                "amount_original": 25.0,
                "currency": "KZT",
                "rate_at_operation": 1.0,
                "amount_base": 25.0,
            }
        ],
        "mandatory_expenses": [],
        "debts": [
            {
                "id": 1,
                "contact_name": "Alex",
                "kind": "debt",
                "total_amount_minor": 10000,
                "remaining_amount_minor": 7500,
                "currency": "KZT",
                "interest_rate": 0.0,
                "status": "open",
                "created_at": "2026-03-01",
                "closed_at": None,
            }
        ],
        "debt_payments": [
            {
                "id": 3,
                "debt_id": 1,
                "record_id": 10,
                "operation_type": "debt_repay",
                "principal_paid_minor": 2500,
                "is_write_off": False,
                "payment_date": "2026-03-02",
            }
        ],
        "transfers": [],
    }
    json_path = tmp_path / "payload.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = import_parser.parse_import_file(str(json_path))

    assert parsed.rows[0]["related_debt_id"] == 1
    assert len(parsed.debts) == 1
    assert parsed.debts[0]["contact_name"] == "Alex"
    assert len(parsed.debt_payments) == 1
    assert parsed.debt_payments[0]["operation_type"] == "debt_repay"


def test_parse_transfer_row_supports_legacy_policy() -> None:
    records, transfer, next_transfer_id, error = import_parser.parse_transfer_row(
        {
            "date": "2026-03-24",
            "from_wallet_id": "1",
            "to_wallet_id": "2",
            "amount": "1500",
        },
        row_label="row 2",
        policy=ImportPolicy.LEGACY,
        get_rate=None,
        next_transfer_id=1,
        wallet_ids={1, 2},
    )

    assert error is None
    assert transfer is not None
    assert records is not None
    assert transfer.currency == "KZT"
    assert transfer.amount_original == 1500.0
    assert transfer.amount_base == 1500.0
    assert next_transfer_id == 2
