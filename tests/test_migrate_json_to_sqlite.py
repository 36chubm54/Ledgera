from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from domain.asset import Asset, AssetCategory, AssetSnapshot
from domain.budget import Budget
from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment, DebtStatus
from domain.distribution import FrozenDistributionRow
from domain.goal import Goal
from domain.records import ExpenseRecord, IncomeRecord, MandatoryExpenseRecord
from domain.tags import Tag
from domain.transfers import Transfer
from domain.wallets import Wallet
from infrastructure.repositories import JsonFileRecordRepository
from migrate_json_to_sqlite import run_dry_run, run_migration
from storage.sqlite_storage import SQLiteStorage
from utils.backup_utils import export_full_backup_to_json


def _query_one(storage: SQLiteStorage, sql: str):
    row = storage.query_one(sql)
    assert row is not None
    return row


def _build_json_fixture(json_path: str) -> None:
    repo = JsonFileRecordRepository(json_path)
    wallets = [
        Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1000.0, system=True),
        Wallet(id=2, name="Card", currency="KZT", initial_balance=500.0),
    ]
    transfer = Transfer(
        id=1,
        from_wallet_id=1,
        to_wallet_id=2,
        date="2026-02-01",
        amount_original=100.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=100.0,
        description="move",
    )
    records = [
        ExpenseRecord(
            id=1,
            date="2026-02-01",
            wallet_id=1,
            transfer_id=1,
            amount_original=100.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=100.0,
            category="Transfer",
        ),
        IncomeRecord(
            id=2,
            date="2026-02-01",
            wallet_id=2,
            transfer_id=1,
            amount_original=100.0,
            currency="KZT",
            rate_at_operation=1.0,
            amount_base=100.0,
            category="Transfer",
        ),
    ]
    mandatory_expenses = [
        MandatoryExpenseRecord(
            id=1,
            date="2026-03-15",
            wallet_id=1,
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
    repo.replace_all_data(
        initial_balance=0.0,
        wallets=wallets,
        records=records,
        mandatory_expenses=mandatory_expenses,
        transfers=[transfer],
    )


def test_dry_run_does_not_insert(tmp_path) -> None:
    json_path = tmp_path / "data.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    _build_json_fixture(str(json_path))

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=True,
    )

    code = run_dry_run(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM wallets")[0] == 0
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM transfers")[0] == 0
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM records")[0] == 0
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM mandatory_expenses")[0] == 0
    sqlite_storage.close()


def test_migration_moves_all_data_and_preserves_ids(tmp_path) -> None:
    json_path = tmp_path / "data.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    _build_json_fixture(str(json_path))

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM wallets")[0] == 2
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM transfers")[0] == 1
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM records")[0] == 2
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM mandatory_expenses")[0] == 1
    row = _query_one(
        sqlite_storage,
        """
        SELECT date, auto_pay, amount_original_minor, amount_base_minor, rate_at_operation_text
        FROM mandatory_expenses
        ORDER BY id
        LIMIT 1
        """,
    )
    assert row[0] == "2026-03-15"
    assert row[1] == 1
    assert row[2] == 5000
    assert row[3] == 5000
    assert row[4] == "1.000000"

    wallet_row = _query_one(
        sqlite_storage, "SELECT initial_balance_minor FROM wallets WHERE id = 1"
    )
    assert wallet_row[0] == 100000

    transfer_row = _query_one(
        sqlite_storage,
        """
        SELECT amount_original_minor, amount_base_minor, rate_at_operation_text
        FROM transfers
        WHERE id = 1
        """,
    )
    assert transfer_row[0] == 10000
    assert transfer_row[1] == 10000
    assert transfer_row[2] == "1.000000"

    wallet_ids = [row[0] for row in sqlite_storage.query_all("SELECT id FROM wallets ORDER BY id")]
    transfer_ids = [
        row[0] for row in sqlite_storage.query_all("SELECT id FROM transfers ORDER BY id")
    ]
    record_ids = [row[0] for row in sqlite_storage.query_all("SELECT id FROM records ORDER BY id")]
    mandatory_ids = [
        row[0] for row in sqlite_storage.query_all("SELECT id FROM mandatory_expenses ORDER BY id")
    ]

    assert wallet_ids == [1, 2]
    assert transfer_ids == [1]
    assert record_ids == [1, 2]
    assert mandatory_ids == [1]
    sqlite_storage.close()


def test_migration_accepts_empty_mandatory_dates_as_equivalent(tmp_path) -> None:
    json_path = tmp_path / "data_empty_mandatory_date.json"
    sqlite_path = tmp_path / "records_empty_mandatory_date.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    repo = JsonFileRecordRepository(str(json_path))
    repo.replace_all_data(
        initial_balance=0.0,
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
        ],
        records=[],
        mandatory_expenses=[
            MandatoryExpenseRecord(
                id=1,
                date="",
                wallet_id=1,
                amount_original=50.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=50.0,
                category="Mandatory",
                description="No date",
                period="monthly",
                auto_pay=False,
            )
        ],
        transfers=[],
    )

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0


def test_migration_is_safe_to_rerun_on_equivalent_dataset(tmp_path) -> None:
    json_path = tmp_path / "records.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    _build_json_fixture(str(json_path))

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    first_code = run_migration(args)
    second_code = run_migration(args)

    assert first_code == 0
    assert second_code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM wallets")[0] == 2
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM transfers")[0] == 1
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM records")[0] == 2
    assert _query_one(sqlite_storage, "SELECT COUNT(*) FROM mandatory_expenses")[0] == 1
    assert (
        _query_one(
            sqlite_storage,
            "SELECT COUNT(*) FROM sqlite_sequence WHERE name = 'wallets'",
        )[0]
        == 1
    )
    assert (
        _query_one(
            sqlite_storage,
            "SELECT COUNT(*) FROM sqlite_sequence WHERE name = 'transfers'",
        )[0]
        == 1
    )
    assert (
        _query_one(
            sqlite_storage,
            "SELECT COUNT(*) FROM sqlite_sequence WHERE name = 'records'",
        )[0]
        == 1
    )
    assert (
        _query_one(
            sqlite_storage,
            "SELECT COUNT(*) FROM sqlite_sequence WHERE name = 'mandatory_expenses'",
        )[0]
        == 1
    )
    sqlite_storage.close()


def test_migration_preserves_tag_metadata_from_full_backup_json(tmp_path) -> None:
    json_path = tmp_path / "backup_tags.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    export_full_backup_to_json(
        str(json_path),
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=0.0, system=True)
        ],
        records=[
            ExpenseRecord(
                id=1,
                wallet_id=1,
                date="2026-05-01",
                amount_original=250.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=250.0,
                category="General",
                tags=("coursework",),
            )
        ],
        tags=[
            Tag(
                id=7,
                name="coursework",
                color="#9B51E0",
                usage_count=1,
                last_used_at="2026-05-01",
            )
        ],
        mandatory_expenses=[],
        transfers=[],
        readonly=False,
        storage_mode="sqlite",
    )

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    tag_row = _query_one(
        sqlite_storage,
        "SELECT name, color, usage_count, last_used_at FROM tags ORDER BY id",
    )
    assert tuple(tag_row) == ("coursework", "#9B51E0", 1, "2026-05-01")
    record_tag_row = _query_one(
        sqlite_storage,
        """
        SELECT rt.record_id, t.name
        FROM record_tags AS rt
        JOIN tags AS t ON t.id = rt.tag_id
        """,
    )
    assert tuple(record_tag_row) == (1, "coursework")
    sqlite_storage.close()


def test_migration_rerun_rejects_payload_mismatch_in_existing_sqlite(tmp_path) -> None:
    json_path = tmp_path / "records.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    _build_json_fixture(str(json_path))

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    first_code = run_migration(args)
    assert first_code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    try:
        sqlite_storage.execute("UPDATE records SET category = 'Broken category' WHERE id = 1")
        sqlite_storage.commit()
    finally:
        sqlite_storage.close()

    second_code = run_migration(args)
    assert second_code == 1


def test_migration_moves_distribution_snapshots_from_full_backup_json(tmp_path) -> None:
    json_path = tmp_path / "backup.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    snapshot = FrozenDistributionRow(
        month="2026-02",
        column_order=("month", "fixed", "net_income", "item_1"),
        headings_by_column={
            "month": "Month",
            "fixed": "Fixed",
            "net_income": "Net income",
            "item_1": "Investments",
        },
        values_by_column={
            "month": "2026-02",
            "fixed": "Yes",
            "net_income": "100",
            "item_1": "100",
        },
        is_negative=False,
        auto_fixed=True,
    )

    export_full_backup_to_json(
        str(json_path),
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1000.0, system=True),
            Wallet(id=2, name="Card", currency="KZT", initial_balance=500.0),
        ],
        records=[],
        mandatory_expenses=[],
        distribution_snapshots=[snapshot],
        transfers=[],
        readonly=False,
    )

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    snapshot_row = _query_one(
        sqlite_storage,
        "SELECT month, auto_fixed FROM distribution_snapshots ORDER BY month LIMIT 1",
    )
    assert snapshot_row[0] == "2026-02"
    assert snapshot_row[1] == 1
    value_row = _query_one(
        sqlite_storage,
        """
        SELECT column_key, value_text
        FROM distribution_snapshot_values
        WHERE snapshot_month = '2026-02' AND column_key = 'item_1'
        """,
    )
    assert value_row[0] == "item_1"
    assert value_row[1] == "100"
    sqlite_storage.close()


def test_migration_moves_budgets_from_full_backup_json(tmp_path) -> None:
    json_path = tmp_path / "backup_with_budgets.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    export_full_backup_to_json(
        str(json_path),
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1000.0, system=True),
        ],
        records=[],
        mandatory_expenses=[],
        budgets=[
            Budget(
                id=1,
                category="Food",
                start_date="2026-03-01",
                end_date="2026-03-31",
                limit_base=1500.0,
                limit_base_minor=150000,
                include_mandatory=True,
            )
        ],
        transfers=[],
        readonly=False,
    )

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    budget_row = _query_one(
        sqlite_storage,
        """
        SELECT category, start_date, end_date, limit_base_minor, include_mandatory
        FROM budgets
        ORDER BY id
        LIMIT 1
        """,
    )
    assert budget_row[0] == "Food"
    assert budget_row[1] == "2026-03-01"
    assert budget_row[2] == "2026-03-31"
    assert budget_row[3] == 150000
    assert budget_row[4] == 1
    sqlite_storage.close()


def test_migration_moves_legacy_budget_limit_kzt_from_full_backup_json(tmp_path) -> None:
    json_path = tmp_path / "backup_with_legacy_budgets.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    payload = {
        "wallets": [
            {
                "id": 1,
                "name": "Main wallet",
                "currency": "KZT",
                "initial_balance": 1000.0,
                "system": True,
                "allow_negative": False,
                "is_active": True,
            }
        ],
        "records": [],
        "mandatory_expenses": [],
        "budgets": [
            {
                "id": 1,
                "category": "Food",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "limit_kzt": 1500.0,
                "limit_kzt_minor": 150000,
                "include_mandatory": True,
            }
        ],
        "transfers": [],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    budget_row = _query_one(
        sqlite_storage,
        """
        SELECT category, start_date, end_date, limit_base_minor, include_mandatory
        FROM budgets
        ORDER BY id
        LIMIT 1
        """,
    )
    assert budget_row[0] == "Food"
    assert budget_row[1] == "2026-03-01"
    assert budget_row[2] == "2026-03-31"
    assert budget_row[3] == 150000
    assert budget_row[4] == 1
    sqlite_storage.close()


def test_migration_rejects_invalid_distribution_structure_in_backup(tmp_path) -> None:
    json_path = tmp_path / "backup_invalid_distribution.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    export_full_backup_to_json(
        str(json_path),
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1000.0, system=True),
        ],
        records=[],
        mandatory_expenses=[],
        distribution_snapshots=[],
        transfers=[],
        readonly=False,
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["distribution_items"] = [
        {
            "id": 1,
            "name": "Investments",
            "group_name": "Goals",
            "sort_order": 0,
            "pct": 100.0,
            "pct_minor": 10000,
            "is_active": True,
        }
    ]
    payload["distribution_subitems"] = [
        {
            "id": 10,
            "item_id": 999,
            "name": "BTC",
            "sort_order": 0,
            "pct": 100.0,
            "pct_minor": 10000,
            "is_active": True,
        }
    ]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 1


def test_migration_moves_debts_and_debt_payments_from_full_backup_json(tmp_path) -> None:
    json_path = tmp_path / "backup_with_debts.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    debt = Debt(
        id=1,
        contact_name="Alex",
        kind=DebtKind.DEBT,
        total_amount_minor=10000,
        remaining_amount_minor=7500,
        currency="KZT",
        interest_rate=0.0,
        status=DebtStatus.OPEN,
        created_at="2026-03-01",
        closed_at=None,
    )
    record = ExpenseRecord(
        id=10,
        date="2026-03-02",
        wallet_id=1,
        related_debt_id=1,
        amount_original=25.0,
        currency="KZT",
        rate_at_operation=1.0,
        amount_base=25.0,
        category="Debt payment",
    )
    debt_payment = DebtPayment(
        id=5,
        debt_id=1,
        record_id=10,
        operation_type=DebtOperationType.DEBT_REPAY,
        principal_paid_minor=2500,
        is_write_off=False,
        payment_date="2026-03-02",
    )

    export_full_backup_to_json(
        str(json_path),
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1000.0, system=True),
        ],
        records=[record],
        mandatory_expenses=[],
        debts=[debt],
        debt_payments=[debt_payment],
        transfers=[],
        readonly=False,
    )

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    debt_row = _query_one(
        sqlite_storage,
        "SELECT contact_name, total_amount_minor, remaining_amount_minor FROM debts WHERE id = 1",
    )
    assert debt_row[0] == "Alex"
    assert debt_row[1] == 10000
    assert debt_row[2] == 7500
    payment_row = _query_one(
        sqlite_storage,
        """
        SELECT debt_id, record_id, operation_type, principal_paid_minor
        FROM debt_payments
        WHERE id = 5
        """,
    )
    assert payment_row[0] == 1
    assert payment_row[1] == 10
    assert payment_row[2] == "debt_repay"
    assert payment_row[3] == 2500
    record_row = _query_one(sqlite_storage, "SELECT related_debt_id FROM records WHERE id = 10")
    assert record_row[0] == 1
    sqlite_storage.close()


def test_migration_moves_assets_snapshots_and_goals_from_full_backup_json(tmp_path) -> None:
    json_path = tmp_path / "backup_with_assets_goals.json"
    sqlite_path = tmp_path / "records.db"
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

    asset = Asset(
        id=1,
        name="Deposit",
        category=AssetCategory.BANK,
        currency="KZT",
        is_active=True,
        created_at="2026-04-05",
        description="Reserve",
    )
    snapshot = AssetSnapshot(
        id=2,
        asset_id=1,
        snapshot_date="2026-04-06",
        value_minor=500000,
        currency="KZT",
        note="Initial",
    )
    goal = Goal(
        id=3,
        title="Emergency Fund",
        target_amount_minor=1000000,
        currency="KZT",
        created_at="2026-04-05",
        target_date="2026-12-31",
        description="Safety cushion",
    )

    export_full_backup_to_json(
        str(json_path),
        wallets=[
            Wallet(id=1, name="Main wallet", currency="KZT", initial_balance=1000.0, system=True),
        ],
        records=[],
        mandatory_expenses=[],
        assets=[asset],
        asset_snapshots=[snapshot],
        goals=[goal],
        transfers=[],
        readonly=False,
    )

    args = Namespace(
        json_path=str(json_path),
        sqlite_path=str(sqlite_path),
        schema_path=str(schema_path),
        dry_run=False,
    )

    code = run_migration(args)
    assert code == 0

    sqlite_storage = SQLiteStorage(str(sqlite_path))
    sqlite_storage.initialize_schema(str(schema_path))
    asset_row = _query_one(
        sqlite_storage,
        "SELECT name, category, currency, is_active FROM assets WHERE id = 1",
    )
    assert asset_row[0] == "Deposit"
    assert asset_row[1] == "bank"
    assert asset_row[2] == "KZT"
    assert asset_row[3] == 1
    snapshot_row = _query_one(
        sqlite_storage,
        "SELECT asset_id, snapshot_date, value_minor, note FROM asset_snapshots WHERE id = 2",
    )
    assert snapshot_row[0] == 1
    assert snapshot_row[1] == "2026-04-06"
    assert snapshot_row[2] == 500000
    assert snapshot_row[3] == "Initial"
    goal_row = _query_one(
        sqlite_storage,
        """
        SELECT title, target_amount_minor, currency, target_date, is_completed
        FROM goals
        WHERE id = 3
        """,
    )
    assert goal_row[0] == "Emergency Fund"
    assert goal_row[1] == 1000000
    assert goal_row[2] == "KZT"
    assert goal_row[3] == "2026-12-31"
    assert goal_row[4] == 0
    sqlite_storage.close()
