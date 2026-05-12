import json
import os
import tempfile

import pytest

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.budget import Budget
from domain.distribution import DistributionItem, DistributionSubitem, FrozenDistributionRow
from domain.goal import Goal
from domain.import_policy import ImportPolicy
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord
from domain.tags import Tag
from domain.wallets import Wallet
from utils import backup_utils as backup_utils_module
from utils.backup_utils import (
    BackupFormatError,
    BackupIntegrityError,
    BackupReadonlyError,
    ImportedBackupData,
    export_full_backup_to_json,
    import_backup,
    import_full_backup_from_json,
)
from utils.csv_utils import import_records_from_csv
from version import __version__


class DummyCurrency:
    def get_rate(self, currency: str) -> float:
        rates = {"USD": 500.0, "EUR": 600.0, "KZT": 1.0}
        return rates[currency]


def test_current_rate_policy_fills_missing_fx_fields():
    csv_content = """
date,type,wallet_id,category,amount_original,currency
2025-01-01,income,1,Salary,100,USD
"""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".csv", encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        records, initial_balance, summary = import_records_from_csv(
            path,
            policy=ImportPolicy.CURRENT_RATE,
            currency_service=DummyCurrency(),
        )
        assert initial_balance == 0.0
        assert summary[0] == 1
        assert summary[1] == 0
        assert len(records) == 1
        assert records[0].rate_at_operation == 500.0
        assert records[0].amount_base == 50000.0
    finally:
        os.unlink(path)


def test_current_rate_policy_overrides_existing_fx_fields():
    csv_content = """
date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base
2025-01-01,income,1,Salary,100,USD,450,45000
"""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".csv", encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        records, _, summary = import_records_from_csv(
            path,
            policy=ImportPolicy.CURRENT_RATE,
            currency_service=DummyCurrency(),
        )
        assert summary[0] == 1
        assert records[0].rate_at_operation == 500.0
        assert records[0].amount_base == 50000.0
    finally:
        os.unlink(path)


def test_legacy_policy_imports_old_amount_column():
    csv_content = """date,type,category,amount
2025-01-02,expense,Food,2500
"""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".csv", encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        records, _, summary = import_records_from_csv(path, policy=ImportPolicy.LEGACY)
        assert summary[0] == 1
        assert isinstance(records[0], ExpenseRecord)
        assert records[0].currency == "KZT"
        assert records[0].rate_at_operation == 1.0
        assert records[0].amount_base == 2500.0
    finally:
        os.unlink(path)


def test_import_validation_skips_invalid_rows():
    csv_content = """
date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base
bad-date,income,1,Salary,10,USD,500,5000
2025-01-02,expense,1,Food,-5,KZT,1,5
2025-01-03,income,1,Salary,10,USDX,500,5000
2025-01-04,income,1,Salary,10,USD,500,5000
"""
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".csv", encoding="utf-8"
    ) as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        records, _, summary = import_records_from_csv(path, policy=ImportPolicy.FULL_BACKUP)
        assert len(records) == 1
        assert isinstance(records[0], IncomeRecord)
        assert summary[0] == 1
        assert summary[1] == 3
        assert len(summary[2]) == 3
    finally:
        os.unlink(path)


def test_full_backup_roundtrip():
    records = [
        IncomeRecord(
            date="2025-01-01",
            amount_original=100.0,
            currency="USD",
            rate_at_operation=500.0,
            amount_base=50000.0,
            category="Salary",
        )
    ]
    mandatory = [
        MandatoryExpenseRecord(
            date="2026-03-11",
            amount_original=50.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=50.0,
            category="Mandatory",
            description="Rent",
            period="monthly",
            auto_pay=True,
        )
    ]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(
                    id=1,
                    name="Main wallet",
                    currency="KZT",
                    initial_balance=123.0,
                    system=True,
                )
            ],
            records=records,
            mandatory_expenses=mandatory,
        )
        result: ImportedBackupData = import_full_backup_from_json(path, force=True)
        wallets = result.wallets
        imported_records = result.records
        imported_mandatory = result.mandatory_expenses
        transfers = result.transfers
        summary = result.summary
        assert wallets[0].initial_balance == 123.0
        assert len(imported_records) == 1
        assert len(imported_mandatory) == 1
        assert str(imported_mandatory[0].date) == "2026-03-11"
        assert imported_mandatory[0].auto_pay is True
        assert transfers == []
        assert summary[1] == 0
    finally:
        os.unlink(path)


def test_full_backup_export_preserves_persisted_tag_colors() -> None:
    records = [
        ExpenseRecord(
            id=1,
            wallet_id=1,
            date="2025-01-02",
            amount_original=30.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=30.0,
            category="Food",
            tags=("food",),
        )
    ]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=records,
            tags=[Tag(id=7, name="food", color="#123ABC")],
            mandatory_expenses=[],
        )
        with open(path, encoding="utf-8") as fp:
            payload = json.load(fp)
        assert payload["data"]["tags"] == [
            {
                "id": 7,
                "name": "food",
                "color": "#123ABC",
                "usage_count": 0,
                "last_used_at": "",
            }
        ]
    finally:
        os.unlink(path)


def test_technical_backup_preserves_mandatory_date() -> None:
    mandatory = [
        MandatoryExpenseRecord(
            date="2026-03-14",
            wallet_id=1,
            amount_original=75.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=75.0,
            category="Mandatory",
            description="Phone",
            period="monthly",
            auto_pay=True,
        )
    ]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=[],
            mandatory_expenses=mandatory,
            transfers=[],
            readonly=False,
            storage_mode="sqlite",
        )
        result: ImportedBackupData = import_full_backup_from_json(path)
        wallets = result.wallets
        records = result.records
        imported_mandatory = result.mandatory_expenses
        transfers = result.transfers
        summary = result.summary
        assert len(wallets) == 1
        assert records == []
        assert transfers == []
        assert len(imported_mandatory) == 1
        assert str(imported_mandatory[0].date) == "2026-03-14"
        assert imported_mandatory[0].auto_pay is True
        assert summary[1] == 0
    finally:
        os.unlink(path)


def test_snapshot_checksum_mismatch_raises_integrity_error() -> None:
    records = [
        IncomeRecord(
            date="2025-01-01",
            wallet_id=1,
            amount_original=10.0,
            currency="USD",
            rate_at_operation=500.0,
            amount_base=5000.0,
            category="Salary",
        )
    ]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=records,
            mandatory_expenses=[],
            transfers=[],
            readonly=True,
        )
        with open(path, encoding="utf-8") as fp:
            payload = json.load(fp)
        payload["data"]["records"][0]["amount_original"] = 999.0
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

        with pytest.raises(BackupIntegrityError):
            import_full_backup_from_json(path, force=True)
    finally:
        os.unlink(path)


def test_snapshot_readonly_requires_force() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            transfers=[],
            readonly=True,
        )
        with pytest.raises(BackupReadonlyError):
            import_full_backup_from_json(path)
    finally:
        os.unlink(path)


def test_snapshot_readonly_force_import_succeeds() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=42.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            transfers=[],
            readonly=True,
        )
        result: ImportedBackupData = import_full_backup_from_json(path, force=True)
        wallets = result.wallets
        records = result.records
        mandatory = result.mandatory_expenses
        transfers = result.transfers
        summary = result.summary
        assert len(wallets) == 1
        assert wallets[0].initial_balance == 42.0
        assert records == []
        assert mandatory == []
        assert transfers == []
        assert summary[1] == 0
    finally:
        os.unlink(path)


def test_import_backup_warns_and_delegates_to_full_backup_helper() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=42.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            transfers=[],
            readonly=False,
        )

        with pytest.deprecated_call(match="import_backup\\(\\.\\.\\.\\) is deprecated"):
            imported = import_backup(path, force=True)

        wallets, records, mandatory, transfers, summary = imported
        assert len(wallets) == 1
        assert records == []
        assert mandatory == []
        assert transfers == []
        assert summary[1] == 0
    finally:
        os.unlink(path)


def test_snapshot_export_writes_precise_metadata() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(
                    id=1,
                    name="Main wallet",
                    currency="KZT",
                    initial_balance=42.0,
                    system=True,
                )
            ],
            records=[],
            mandatory_expenses=[],
            transfers=[],
            readonly=True,
            storage_mode="json",
        )
        with open(path, encoding="utf-8") as fp:
            payload = json.load(fp)
        assert payload["meta"]["app_version"] == __version__
        assert payload["meta"]["storage"] == "json"
    finally:
        os.unlink(path)


def test_full_backup_export_includes_distribution_snapshots() -> None:
    snapshot = FrozenDistributionRow(
        month="2026-03",
        column_order=("month", "fixed", "net_income", "item_1"),
        headings_by_column={
            "month": "Month",
            "fixed": "Fixed",
            "net_income": "Net income",
            "item_1": "Investments",
        },
        values_by_column={
            "month": "2026-03",
            "fixed": "Yes",
            "net_income": "100,000",
            "item_1": "100,000",
        },
        is_negative=False,
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            distribution_snapshots=[snapshot],
            transfers=[],
            readonly=False,
        )
        with open(path, encoding="utf-8") as fp:
            payload = json.load(fp)
        assert "distribution_snapshots" in payload
        assert payload["distribution_snapshots"][0]["month"] == "2026-03"
        assert payload["distribution_snapshots"][0]["auto_fixed"] is False
        assert payload["distribution_snapshots"][0]["values_by_column"]["item_1"] == "100,000"
    finally:
        os.unlink(path)


def test_full_backup_export_includes_distribution_structure() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            distribution_items=[
                DistributionItem(
                    id=1,
                    name="Investments",
                    group_name="Goals",
                    sort_order=0,
                    pct=100.0,
                    pct_minor=10000,
                    is_active=True,
                )
            ],
            distribution_subitems=[
                DistributionSubitem(
                    id=10,
                    item_id=1,
                    name="BTC",
                    sort_order=0,
                    pct=100.0,
                    pct_minor=10000,
                    is_active=True,
                )
            ],
            readonly=False,
        )
        with open(path, encoding="utf-8") as fp:
            payload = json.load(fp)
        assert payload["distribution_items"][0]["name"] == "Investments"
        assert payload["distribution_items"][0]["group_name"] == "Goals"
        assert payload["distribution_subitems"][0]["name"] == "BTC"
        assert payload["distribution_subitems"][0]["item_id"] == 1
    finally:
        os.unlink(path)


def test_full_backup_export_includes_budgets() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            budgets=[
                Budget(
                    id=1,
                    category="Food",
                    start_date="2026-03-01",
                    end_date="2026-03-31",
                    limit_base=150000.0,
                    limit_base_minor=15000000,
                    include_mandatory=True,
                )
            ],
            readonly=False,
        )
        with open(path, encoding="utf-8") as fp:
            payload = json.load(fp)
        assert payload["budgets"][0]["category"] == "Food"
        assert payload["budgets"][0]["limit_base_minor"] == 15000000
        assert payload["budgets"][0]["include_mandatory"] is True
    finally:
        os.unlink(path)


def test_full_backup_export_and_import_include_assets_snapshots_and_goals() -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
    try:
        export_full_backup_to_json(
            path,
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            assets=[
                Asset(
                    id=1,
                    name="Deposit",
                    category=AssetCategory.BANK,
                    currency="KZT",
                    is_active=True,
                    created_at="2026-04-05",
                )
            ],
            asset_snapshots=[
                AssetSnapshot(
                    id=1,
                    asset_id=1,
                    snapshot_date="2026-04-05",
                    value_minor=500000,
                    currency="KZT",
                    note="Initial",
                )
            ],
            goals=[
                Goal(
                    id=1,
                    title="Emergency Fund",
                    target_amount_minor=1000000,
                    currency="KZT",
                    created_at="2026-04-05",
                    target_date="2026-12-31",
                )
            ],
            readonly=False,
        )
        result: ImportedBackupData = import_full_backup_from_json(path)
        assert len(result.assets) == 1
        assert result.assets[0].name == "Deposit"
        assert len(result.asset_snapshots) == 1
        assert result.asset_snapshots[0].asset_id == 1
        assert len(result.goals) == 1
        assert result.goals[0].title == "Emergency Fund"
    finally:
        os.unlink(path)


def test_full_backup_export_writes_json_atomically_on_failure(monkeypatch, tmp_path) -> None:
    path = tmp_path / "data.json"
    original_content = '{"safe": true}'
    path.write_text(original_content, encoding="utf-8")

    real_json_dump = backup_utils_module.json.dump

    def _broken_dump(payload, fp, **kwargs):
        real_json_dump(payload, fp, **kwargs)
        fp.write("\nPARTIAL")
        raise RuntimeError("boom")

    monkeypatch.setattr(backup_utils_module.json, "dump", _broken_dump)

    with pytest.raises(RuntimeError, match="boom"):
        export_full_backup_to_json(
            str(path),
            wallets=[
                Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
            ],
            records=[],
            mandatory_expenses=[],
            transfers=[],
            readonly=False,
        )

    assert path.read_text(encoding="utf-8") == original_content


def test_legacy_json_without_meta_imports_normally() -> None:
    payload = {
        "wallets": [
            {
                "id": 1,
                "name": "Main wallet",
                "currency": "KZT",
                "initial_balance": 5.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        "records": [],
        "mandatory_expenses": [],
        "transfers": [],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json", encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        path = tmp.name
    try:
        result: ImportedBackupData = import_full_backup_from_json(path)
        wallets = result.wallets
        summary = result.summary
        assert wallets[0].initial_balance == 5.0
        assert summary[1] == 0
    finally:
        os.unlink(path)


def test_snapshot_invalid_structure_raises_backup_format_error() -> None:
    payload = {"meta": {"readonly": True, "checksum": "abc"}, "data": []}
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json", encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        path = tmp.name
    try:
        with pytest.raises(BackupFormatError):
            import_full_backup_from_json(path, force=True)
    finally:
        os.unlink(path)
